# 📊 Yaseer Operations Big Data Analytics Platform
**Enterprise-Grade Data Analytics & Engineering Solution for LIS (Laboratory Information Systems)**

---

## 🚀 Overview
The **Yaseer Data Analytics Platform** is a specialized Big Data solution designed to process, clean, and analyze operational data from the Yaseer Laboratory Management System. It leverages a modern **Medallion Architecture** to transform raw operational logs into actionable business insights.

### 🏗️ Architecture Stack
*   **Ingestion**: Debezium (CDC) -> RabbitMQ
*   **Storage**: MariaDB (Source), ClickHouse (Data Warehouse), MinIO (Data Lake)
*   **Processing**: Python ELT Loaders, dbt (Data Build Tool), Apache Spark (Planned)
*   **Orchestration**: Apache Airflow
*   **Visualization**: Metabase, Apache Superset

---

## 📚 Documentation
Detailed documentation for specific components can be found in the `docs/` directory:

| Document | Description |
| :--- | :--- |
| [**DATABASE.md**](docs/DATABASE.md) | 🧬 Detailed LIS database schema, ERD, and table dictionary. |
| [**CLEANING.md**](docs/CLEANING.md) | 🧹 Data cleaning logic, transformation rules, and medallion architecture. |
| [**METABASE_GUIDE.md**](docs/METABASE_GUIDE.md) | 📊 Guide to building dashboards and visualizations in Metabase. |
| [**Project Documentation.pdf**](docs/Project%20Documentation.pdf) | 📄 Original comprehensive project documentation. |

---

## ⚡ Quick Start

### Prerequisites
*   Docker & Docker Compose

### 1. Start the Platform
Boot up the entire stack, including the LIS Simulation, Data Warehouse, and Airflow.
```bash
docker-compose -f docker-compose-platform.yml up -d
```

### 2. Access Services
Once the containers are running, access the following interfaces:

| Service | URL | Credentials | Description |
| :--- | :--- | :--- | :--- |
| **Apache Airflow** | [http://localhost:8080](http://localhost:8080) | `admin` / `admin` | Workflow Orchestration & Scheduling |
| **Apache Superset** | [http://localhost:8088](http://localhost:8088) | `admin` / `admin` | Modern Data Exploration & Visualization Platform |
| **Metabase** | [http://localhost:3000](http://localhost:3000) | Setup on first run | BI Dashboards & Reporting |
| **ClickHouse** | [http://localhost:8123](http://localhost:8123) | `default` / (none) | OLAP Database (HTTP) |
| **RabbitMQ** | [http://localhost:15672](http://localhost:15672) | `user` / `password` | Message Broker Management |
| **MinIO** | [http://localhost:9001](http://localhost:9001) | `minioadmin` / `minio123` | Object Storage Console |
| **PhpMyAdmin** | [http://localhost:8082](http://localhost:8082) | `dbuser` / `dbpassword` | LIS Database Admin (MariaDB) |

### 3. Superset Initialization
Initialize Superset and create an admin user:
```bash
docker exec -it superset bash

superset fab create-admin \
  --username admin \
  --firstname Superset \
  --lastname Admin \
  --email admin@superset.com \
  --password admin

superset init
```

---

## 📂 Project Structure

```
.
├── config/                 # Service configurations (RabbitMQ, Debezium, etc.)
├── dags/                   # Apache Airflow DAGs (Python workflows)
├── data/                   # Persistent data storage for containers
├── docs/                   # ✨ Project documentation
├── logs/                   # Application and service logs
├── macros/                 # dbt macros
├── models/                 # dbt data models (Medallion layers)
├── plugins/                # Apache Airflow plugins
├── docker-compose-*.yml    # Docker orchestration files
├── rabbitmq_to_clickhouse.py # Python ELT Loader
└── README.md               # You are here
```

---

## 🔄 ELT Workflow (The "Data Journey")
1.  **Change Capture**: `Debezium` listens to `MariaDB` binlogs for any changes (Inserts/Updates).
2.  **Streaming**: Changes are pushed to `RabbitMQ` topics.
3.  **Ingestion**: `rabbitmq_to_clickhouse.py` consumes messages and writes raw JSON to `ClickHouse`.
4.  **Transformation**: `dbt` (orchestrated by `Airflow`) cleans data and builds Star Schema tables.
5.  **Analysis**: `Metabase` and `Apache Superset` query the final Gold tables for dashboards.

---
© **Tarqeem Software & Information Systems**
