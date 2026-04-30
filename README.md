# 📊 Yaseer Operations Big Data Analytics Platform
**Enterprise-Grade Data Analytics & Engineering Solution for LIS (Laboratory Information Systems)**

> 📖 **Full project documentation is available in the [`docs/`](docs/) folder.**

---

## 🚀 Overview
The **Yaseer Data Analytics Platform** is a specialized Big Data solution designed to process, clean, and analyze operational data from the Yaseer Laboratory Management System. It leverages a modern **Medallion Architecture** to transform raw operational data into actionable business insights.

### 🏗️ Architecture Stack
*   **Ingestion**: Debezium (CDC) → RabbitMQ
*   **Storage**: MariaDB (Source), ClickHouse (Data Warehouse), MinIO (Data Lake)
*   **Processing**: Python ELT Loaders, dbt (Data Build Tool)
*   **Orchestration**: Apache Airflow
*   **Visualization**: Metabase

---

## 📚 Documentation

The [`docs/`](docs/) directory contains the full project documentation:

| Document | Description |
| :--- | :--- |
| [**1. Project Planning & Management**](docs/1.%20Project%20Planning%20%26%20Management.md) | 📅 Team structure, timeline, methodology, scope, and risk management. |
| [**2. Literature Review**](docs/2.%20Literature%20Review.md) | 📚 Big Data concepts, ETL vs ELT, data warehousing, and Medallion Architecture. |
| [**3. Requirements Gathering**](docs/3.%20Requirements%20Gathering.md) | 📋 Functional & non-functional requirements, user roles, and use cases. |
| [**4. System Analysis & Design**](docs/4.%20System%20Analysis%20%26%20Design.md) | 🏗️ System architecture, data flow, ERD, and design decisions. |

---

## ⚡ Quick Start

### Prerequisites
*   Docker & Docker Compose

### 1. Configure Environment
Copy the example files and fill in your credentials:
```bash
cp .env.example .env
cp docker-compose.example.yml docker-compose.yml
cp config/debezium/application.example.properties config/debezium/application.properties
cp profiles.example.yml profiles.yml
```

### 2. Start the Platform
Boot up the entire stack, including the Data Warehouse, CDC pipeline, and Airflow.
```bash
docker-compose up -d
```

### 3. Access Services
Once the containers are running, access the following interfaces:

| Service | URL | Credentials (`.env` variables) | Description |
| :--- | :--- | :--- | :--- |
| **Apache Airflow** | [http://localhost:8080](http://localhost:8080) | `AIRFLOW_POSTGRES_USER` / `AIRFLOW_POSTGRES_PASSWORD` | Workflow Orchestration & Scheduling |
| **Metabase** | [http://localhost:3000](http://localhost:3000) | Setup on first run | BI Dashboards & Reporting |
| **ClickHouse** | [http://localhost:8123](http://localhost:8123) | `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD` | OLAP Database (HTTP Interface) |
| **RabbitMQ** | [http://localhost:15672](http://localhost:15672) | `RABBITMQ_DEFAULT_USER` / `RABBITMQ_DEFAULT_PASS` | Message Broker Management |
| **MinIO** | [http://localhost:9001](http://localhost:9001) | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | Object Storage Console |

> **Note:** All credentials are configured in the `.env` file. Copy `.env.example` to `.env` and update the values before starting the platform.

---

## 📂 Project Structure

```
.
├── config/                       # Service configurations (RabbitMQ, Debezium)
│   ├── debezium/                 # Debezium CDC connector config
│   └── rabbitmq/                 # RabbitMQ broker config
├── dags/                         # Apache Airflow DAGs (Python workflows)
├── docs/                         # 📖 Project documentation
├── macros/                       # dbt macros
├── models/                       # dbt data models (Medallion layers)
├── plugins/                      # Apache Airflow plugins
├── scripts/                      # Utility scripts
├── docker-compose.example.yml    # Docker Compose template (copy to docker-compose.yml)
├── dbt_project.yml               # dbt project configuration
├── profiles.example.yml          # dbt profile template (copy to profiles.yml)
├── rabbitmq_to_clickhouse.py     # Python CDC consumer (RabbitMQ → ClickHouse)
├── test_consumer.py              # Consumer unit tests
└── README.md                     # You are here
```

---

## 🔄 ELT Workflow

```
MariaDB (LIS)  →  Debezium (CDC)  →  RabbitMQ  →  Python Consumer  →  ClickHouse  →  dbt  →  Metabase
```

1.  **Change Capture**: Debezium listens to MariaDB binlogs for data changes (Inserts, Updates, Deletes).
2.  **Streaming**: CDC events are published to RabbitMQ queues.
3.  **Ingestion**: `rabbitmq_to_clickhouse.py` consumes messages and writes raw data to ClickHouse (Bronze layer).
4.  **Transformation**: dbt (orchestrated by Airflow) cleans and models data through Silver → Gold layers.
5.  **Visualization**: Metabase queries the final Gold tables for dashboards and reports.

---

## 👥 Team

| Role | Name |
| :--- | :--- |
| Member | Omar Hamdan Abdelaziz |
| Member | Ahmad Mostafa Hosni |
| Member | Ahmad Mohammad Abdelsalam |
| Member | Ahmad Mohammad Abdelkhalik |
| Member | Mennat-Allah Abdellatif Ahmad |
| **Team Leader** | Hosam Mohammad Ali |

---
