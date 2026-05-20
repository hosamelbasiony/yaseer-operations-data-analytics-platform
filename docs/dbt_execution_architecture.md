# 🏗️ Execution & Architecture: "dbt run" in Docker

This document provides an extensive, component-by-component explanation of what happens behind the scenes when you run the command:
```bash
docker exec -it dbt-transform dbt run
```

---

## 🗺️ Architectural Data Flow

```
                      +-----------------------------------------+
                      |               Your Host OS              |
                      |  Terminal: Runs docker exec command     |
                      +--------------------+--------------------+
                                           | (REST API / Named Pipe)
                                           ▼
                      +-----------------------------------------+
                      |         Docker Engine (dockerd)         |
                      +--------------------+--------------------+
                                           | (Executes in Container Namespace)
                                           ▼
+------------------------------------------+------------------------------------------+
| Container: dbt-transform                                                            |
|                                                                                     |
|   1. Mounts:                                                                        |
|      - Host Project Root (.:/usr/app)                                               |
|      - Connection Profile (./profiles.yml:/root/.dbt/profiles.yml)                  |
|                                                                                     |
|   2. Engine Steps:                                                                  |
|      [ Jinja Compilation ] ---> [ DAG Dependencies ] ---> [ SQL Pushdown Dispatch ]  |
+------------------------------------------+------------------------------------------+
                                           | (ClickHouse SQL Dialect over HTTP 8123)
                                           ▼
+------------------------------------------+------------------------------------------+
| Container: clickhouse                                                               |
|                                                                                     |
|   1. Receives DDls / DMLs (e.g., CREATE TABLE AS SELECT ...)                        |
|   2. Executes transformations directly in-database (No memory copying to dbt)       |
|   3. Uses Vectorized Query Execution (SIMD) & Column-Oriented Storage engine         |
+-------------------------------------------------------------------------------------+
```

---

## 🐳 1. The Container Execution Layer (Docker)

At the container level, Docker manages namespaces, resources, and filesystem bindings to run the command in an isolated environment.

### Command Dissection

*   **`docker exec`**: Instructs the Docker daemon to spawn a new process inside an *already-running* container. It does not spin up a new container instance, keeping execution fast.
*   **`-i` (interactive)**: Keeps standard input (`stdin`) open. This allows you to interact with the command (e.g., keyboard interrupts like `Ctrl+C`).
*   **`-t` (TTY)**: Allocates a pseudo-TTY (teletypewriter), which emulates a physical terminal screen. This enables dbt to output rich text, ANSI colors, progress bars, and formatted tables directly to your terminal.
*   **`dbt-transform`**: The target container identifier as specified in your `docker-compose.yml` service.
*   **`dbt run`**: The executable command spawned within the container working directory (`/usr/app`).

### Shared Filesystem States (Bind Mounts)
Inside `docker-compose.yml`, the `dbt-transform` service exposes the local project structure to the container using bind mounts:
```yaml
volumes:
  - .:/usr/app
  - ./profiles.yml:/root/.dbt/profiles.yml
```
1.  **Code Synchronicity (`.:/usr/app`)**: Your local files on the host OS are mapped directly to `/usr/app`. Whenever you save a model locally, the container is immediately updated with the changes.
2.  **Connection Configuration (`profiles.yml`)**: Contains credentials (host, port, user, schema) for ClickHouse. Mapping it to `/root/.dbt/profiles.yml` puts it in dbt's default search directory.

---

## ⚡ 2. The Transformation Layer: dbt Engine

When the command `dbt run` is fired inside the container, the dbt core engine follows a strict sequence of execution steps:

### A. Initialization & Code Compilation
1.  **Project Parsing**: dbt reads `dbt_project.yml` to load project variables, model directories, and default configurations.
2.  **Jinja Resolution**: dbt parses SQL models written with Jinja markup. For example:
    ```sql
    -- Source Code
    select * from {{ source('yaseer', 'patients') }}
    ```
    Is compiled into the database target schema name:
    ```sql
    -- Compiled Code
    select * from default.patients
    ```
3.  **Directed Acyclic Graph (DAG) Resolution**: dbt reviews `{{ ref(...) }}` and `{{ source(...) }}` references in your project to compile a topological execution map. If Model B depends on Model A, dbt guarantees Model A is successfully run and created before starting Model B.

### B. Push-Down Query Dispatch (ELT vs. ETL)
Traditional ETL tools load data into memory, run logic, and write it back. **dbt works on the ELT (Extract, Load, Transform) paradigm**:
*   dbt does **not** process your rows inside the `dbt-transform` container.
*   Instead, for each model, dbt wraps the SELECT query in a target DDL statement:
    ```sql
    CREATE TABLE default.stg_patients_new AS SELECT ...
    ```
*   This statement is sent over port `8123` to the ClickHouse server. The actual raw data is transformed *directly inside ClickHouse*.
*   Once ClickHouse returns a success code, dbt reports the runtime metric and triggers the next model in the DAG.

---

## 📊 3. The Computational Warehouse: ClickHouse

The physical transformation of billions of rows is completed inside ClickHouse utilizing two key technologies:

### A. Column-Oriented Storage Engine
Traditional relational databases (MySQL, PostgreSQL) use **row-oriented storage** (ideal for transactions where you edit/fetch whole rows). 

ClickHouse uses **column-oriented storage**. If a query only pulls two columns (`branch_name` and `SUM(gross_revenue)`), ClickHouse only reads those specific columns from the physical disk, completely ignoring patient IDs, dates, notes, and other columns. This minimizes disk I/O overhead.

### B. Vectorized Query Execution (SIMD)
ClickHouse does not process rows one-by-one. Instead, it aggregates data in chunks or "vectors" of values. 

It feeds these vectors directly to CPU registers, leveraging **SIMD (Single Instruction Multiple Data)** instructions. This allows modern microprocessors to execute calculations on multiple values in parallel, enabling ClickHouse to scan billions of rows per second.
