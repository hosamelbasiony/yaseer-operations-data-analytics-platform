# 🧹 Data Cleaning Recommendations: Yaseer Analytics Platform

This document outlines the essential data cleaning and transformation steps required to turn raw LIS operational data into high-quality analytical insights for the **Yaseer Platform**.

---

## 1. 👥 Patient Demographics (Identity & Contact)
*The goal is to move from "Registration Records" to "Unique Patients".*

- **Identity Deduplication**:
    - Use fuzzy matching (Levenshtein distance) on `patients.name` + `patients.phone`.
    - Prioritize `national_id` (if available) as a unique key.
    - Create a `master_patient_id` in the analytical layer to link multiple visit records to one person.
- **Phone Normalization**:
    - Standardize all phone numbers to international format (e.g., `9665XXXXXXXX`).
    - Remove spaces, dashes, and leading zeros.
- **Age Demographic Data**:
    - Filter out impossible `dob` (e.g., age > 120 or future dates).
    - Calculate a `calculated_age_at_visit` for `fact_visits`.

---

## 2. 🔬 Medical & Technical Results (`test_entry_lines`)
*The goal is to ensure clinical data is comparable across branches and time.*

- **Unit Normalization**:
    - Build a mapping table to convert different units (e.g., `mg/dL` to `umol/L`) to a single standard for each `test_id`.
- **Biological Outlier Filtering**:
    - Define "Panic/Impossible" ranges for each test.
    - Flag values that are physically impossible (e.g., Hemoglobin of 500) as "Data Entry Error" instead of including them in averages.
- **Result Type Casting**:
    - Convert qualitative results (e.g., "+ve", "Positive", "Reactive") into standardized categorical values (0/1 or Low/High).
- **Operator Logic Mapping**:
    - Handle the `operator` codes (0-5) in `test_entry_lines`.
    - Create a `numerical_result` field that extracts the number from strings like "> 10.5".

---

## 3. 💰 Financial Data (`reg`, `installment`)
*The goal is to ensure "one source of truth" for revenue and debt.*

- **Refund & Discount Handling**:
    - In `installment`, properly handle operation codes where negative values indicate refunds or cancelled discounts.
- **Financial Integrity Check**:
    - Create a flag for records where `total_price != (paid + debt)`. These should be audited rather than displayed in dashboards.
- **Payer Category Mapping**:
    - Map `contract_id` (0, 1) to "Cash/Walk-in".
    - Map all other `contract_id` values to their corporate names (Insurance, Companies, etc.) from `dim_contract`.

---

## ⏱️ 4. Workflow & Temporal Cleaning
*The goal is to measure efficiency (TAT) accurately.*

- **Timezone Standardization**:
    - Ensure all `stamp` and `cdc_timestamp` fields are converted to a single standard timezone (e.g., `UTC` or `Asia/Riyadh`).
- **Status Normalization**:
    - Map the `reg_lines.status` integers to descriptive strings (e.g., `1 -> Pending`, `Verified -> 4`).
- **TAT Anomaly Detection**:
    - If a test takes 500 hours but the average is 2 hours, flag it as a workflow anomaly (missing timestamp) rather than a performance failure.

---

## 📂 5. Recommended Architecture (Medallion)

To implement these steps efficiently, use a **Medallion Architecture** within ClickHouse (orchestrated by **dbt**):

1.  **🥉 Bronze (Raw)**: Mirror of MySQL binlogs (Ingested by `rabbitmq_to_clickhouse.py`).
2.  **🥈 Silver (Cleaned)**:
    - Normalization rules applied.
    - Types casted (String to Decimal).
    - Invalid data filtered out.
3.  **🥇 Gold (Analytical)**:
    - Final `fact_` and `dim_` tables.
    - Pre-aggregated KPIs (Daily revenue, AVG TAT per branch).

---
*Created on: 2026-01-30*
