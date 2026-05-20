# 🛠️ Setup Guide — Yaseer Operations Data Analytics Platform

> Complete step-by-step instructions to deploy, configure, and visualize the entire analytics stack.

---

## 📋 Prerequisites

- **Docker & Docker Compose** installed and running
- **Python 3.9+** (only needed for running the Metabase dashboard setup script locally)
- Network access to the MariaDB source database (Debezium reads binlogs from it)

---

## Step 1: Configure Environment Files

Copy the example templates and fill in your credentials:

```bash
cp .env.example .env
cp docker-compose.example.yml docker-compose.yml
cp config/debezium/application.example.properties config/debezium/application.properties
cp profiles.example.yml profiles.yml
```

### `.env` — Service Credentials

| Variable | Default | Description |
|---|---|---|
| `RABBITMQ_DEFAULT_USER` | `user` | RabbitMQ broker username |
| `RABBITMQ_DEFAULT_PASS` | `password` | RabbitMQ broker password |
| `CLICKHOUSE_USER` | `default` | ClickHouse database username |
| `CLICKHOUSE_PASSWORD` | `default` | ClickHouse database password |
| `MINIO_ROOT_USER` | `minioadmin` | MinIO object storage username |
| `MINIO_ROOT_PASSWORD` | `minio123` | MinIO object storage password |
| `AIRFLOW_POSTGRES_USER` | `airflow` | Airflow metadata DB username |
| `AIRFLOW_POSTGRES_PASSWORD` | `airflow` | Airflow metadata DB password |

### `config/debezium/application.properties` — CDC Source

Update these fields to point to your MariaDB source database:

```properties
debezium.source.database.hostname=YOUR_MARIADB_HOST
debezium.source.database.port=YOUR_PORT
debezium.source.database.user=YOUR_DB_USER
debezium.source.database.password=YOUR_DB_PASSWORD
```

The `table.include.list` is pre-configured to capture only the **13 tables** required by the dbt models:

```properties
debezium.source.table.include.list=lis_tarqeem.patients,lis_tarqeem.reg,lis_tarqeem.reg_lines,lis_tarqeem.tests,lis_tarqeem.profiles,lis_tarqeem.installment,lis_tarqeem.users,lis_tarqeem.expenses,lis_tarqeem.expenses_categories,lis_tarqeem.test_entry_lines,lis_tarqeem.profile_details,lis_tarqeem.referral,lis_tarqeem.branches
```

### `profiles.yml` — dbt Connection

Default configuration (no changes needed if using Docker):

```yaml
clickhouse:
  target: dev
  outputs:
    dev:
      type: clickhouse
      host: clickhouse
      port: 8123
      user: default
      password: default
      schema: default
```

---

## Step 2: Start the Docker Stack

Boot all 15 services:

```bash
docker compose up -d --build
```

### Services Started

| Service | Container | Port | Purpose |
|---|---|---|---|
| ClickHouse | `clickhouse` | `8123` (HTTP), `9009` (TCP) | OLAP Data Warehouse |
| RabbitMQ | `rabbitmq` | `5672` (AMQP), `15672` (UI) | Message Broker |
| Debezium | `debezium` | — | CDC from MariaDB |
| CDC Consumer | `rabbitmq-consumer` | — | RabbitMQ → ClickHouse loader |
| dbt | `dbt-transform` | — | Data transformation engine |
| Airflow Webserver | `airflow-webserver` | `8080` | Workflow orchestration UI |
| Airflow Scheduler | `airflow-scheduler` | — | DAG execution scheduler |
| Airflow DAG Processor | `airflow-dag-processor` | — | DAG file parsing |
| PostgreSQL | `postgres-airflow` | — | Airflow metadata database |
| Metabase | `metabase2` | `3000` | BI Dashboards & Reporting |
| MinIO | `minio` | `9000` (API), `9001` (Console) | Object Storage / Data Lake |

---

## Step 3: Verify Data Pipeline

### 3.1 Check CDC Consumer

```bash
docker logs rabbitmq-consumer --tail 100
```

Look for:
```
Connected. Waiting for messages in 'analytics_queue'...
Connected to ClickHouse successfully.
```

### 3.2 Verify Tables in ClickHouse

The consumer **dynamically creates** tables as CDC events arrive. Check:

```bash
docker exec -it clickhouse clickhouse-client --query "SHOW TABLES"
```

You should see the 13 source tables (e.g., `patients`, `reg`, `reg_lines`, `tests`, etc.) appear as data flows in from MariaDB.

> ⚠️ **If tables are empty:** Debezium needs time to perform the initial snapshot of the MariaDB database. This can take a few minutes depending on database size. Check Debezium logs with `docker logs debezium --tail 100`.

---

## Step 4: Run dbt Transformations

dbt transforms the raw Bronze (source) tables into cleaned Silver and aggregated Gold models.

### Option A: Run Manually

```bash
docker exec -it dbt-transform dbt run
```

### Option B: Via Airflow (Automated)

1. Open **Airflow** at [http://localhost:8080](http://localhost:8080)
2. Find the DAG named **`yaseer_dbt_pipeline`**
3. **Toggle it ON** (unpause) using the switch on the right side
4. The DAG is configured to run automatically every **1 minute** (`*/1 * * * *`)

The DAG executes two tasks in sequence:
1. `dbt_debug` — Validates the dbt connection to ClickHouse
2. `dbt_run --full-refresh` — Builds all staging, intermediate, and final models

### dbt Models Created

| Layer | Model | Type |
|---|---|---|
| **Staging** | `stg_patients`, `stg_reg`, `stg_reg_lines`, `stg_tests`, `stg_profiles`, `stg_installment`, `stg_users`, `stg_expenses`, `stg_expenses_categories`, `stg_test_entry_lines`, `stg_profile_details`, `stg_referral`, `stg_branches` | Cleaned source data |
| **Dimensions** | `dim_patients`, `dim_branches`, `dim_profiles`, `dim_referrals` | Lookup/reference tables |
| **Facts** | `fact_registrations`, `fact_order_lines`, `fact_payments`, `fact_test_results`, `fact_expenses`, `fact_samples`, `fact_user_performance` | Transactional event tables |
| **Aggregates** | `daily_revenue_summary`, `daily_cashflow_summary`, `profile_popularity`, `tat_analysis` | Pre-computed KPI tables |

---

## Step 5: Set Up Metabase

### 5.1 First-Time Web Setup

1. Open [http://localhost:3000](http://localhost:3000) in your browser
2. Complete the setup wizard:
   - **Create Admin Account:**
     - Email: `hosam@home.com` (recommended — matches the setup script defaults)
     - Password: `ASDasd@123` (recommended — matches the setup script defaults)
   - **Connect Database:**
     - Database type: **ClickHouse** *(bundled natively in Metabase 54+)*
     - Display name: `clickhouse`
     - Host: `clickhouse`
     - Port: `8123`
     - Database name: `default`
     - Username: `default`
     - Password: *(leave blank)*

> 💡 **Note:** If you use the recommended credentials above, the dashboard setup script will work with zero arguments.

### 5.2 Auto-Generate Dashboards

Once the ClickHouse database is connected in Metabase, run the automation script to create all **7 dashboards** with **80+ cards** instantly:

```bash
# If you used the recommended credentials above:
python scripts/setup_metabase_dashboards.py

# If you used custom credentials:
python scripts/setup_metabase_dashboards.py \
    --metabase-url http://localhost:3000 \
    --metabase-user YOUR_EMAIL \
    --metabase-pass YOUR_PASSWORD
```

> ⚠️ **Requires `requests` package:** `pip install requests`

### 5.3 Dashboards Created

The script creates a **"Yaseer LIS Analytics"** collection with these dashboards:

| Dashboard | Audience | Description |
|---|---|---|
| 🏢 **Executive Overview** | Management | Revenue, orders, patient KPIs, branch performance |
| 💰 **Financial & Cashflow** | Finance / Accountant | Cash in/out, expenses, debts, payment mix |
| 🧪 **Lab Operations** | Lab Manager | Test volumes, TAT analysis, verification rates |
| 🔬 **Clinical Quality** | QA / Medical Director | Abnormal rates, panic values, technician output |
| 👨‍⚕️ **Referral & Contract** | Marketing / BD | Doctor referrals, contract revenue |
| 👤 **Patient Analytics** | Marketing / Management | Demographics, retention, new vs returning |
| 📊 **Profile Performance** | Technical Director | Monthly test rankings, collection rates |

### 5.4 Dashboard Auto-Refresh

On any dashboard in Metabase:
- Click the **clock icon** (🕒) in the top-right corner
- Select a refresh interval (minimum: **1 minute**)
- For wall-mounted TV displays, append `#refresh=30` to the URL for 30-second refresh:
  ```
  http://localhost:3000/dashboard/1#refresh=30
  ```

---

## 🔧 Troubleshooting

### Network Error: `network analytics-net not found`

If you see this error during `docker compose up`, it means a stale external network reference. Fix:

```bash
docker compose down -v
docker compose up -d
```

### CDC Error: `Unrecognized column 'X' in table Y`

The consumer includes **automatic schema evolution**. If the MariaDB source adds a new column, the consumer will:
1. Detect the missing column in ClickHouse
2. Run `ALTER TABLE ADD COLUMN` automatically
3. Retry the insert

No manual action is needed.

### Metabase: ClickHouse Not in Database Type List

For Metabase versions **below 54**, you need to manually install the ClickHouse driver:
1. Download `clickhouse.metabase-driver.jar` from [GitHub Releases](https://github.com/ClickHouse/metabase-clickhouse-driver/releases)
2. Place it in `./data/metabase/plugins/`
3. Restart Metabase: `docker compose restart metabase`

For Metabase **54+**, ClickHouse is bundled as a core database type.

### ClickHouse: No Tables After Fresh Start

Tables are created **dynamically** when CDC events arrive. After a fresh `docker compose up -d`:
1. Wait for Debezium to connect to MariaDB and start the initial snapshot (~1-3 minutes)
2. Check consumer logs: `docker logs rabbitmq-consumer --tail 50`
3. Once you see `Inserted SNAPSHOT into 'patients'`, tables are being created

---

## 🔗 Quick Access URLs

| Service | URL |
|---|---|
| Metabase Dashboards | [http://localhost:3000](http://localhost:3000) |
| Airflow UI | [http://localhost:8080](http://localhost:8080) |
| ClickHouse HTTP | [http://localhost:8123](http://localhost:8123) |
| RabbitMQ Management | [http://localhost:15672](http://localhost:15672) |
| MinIO Console | [http://localhost:9001](http://localhost:9001) |
