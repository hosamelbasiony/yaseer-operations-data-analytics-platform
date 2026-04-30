# 📊 Metabase Dashboard Guide — Yaseer LIS Analytics

## 📋 Overview

This guide documents all **preconfigured dashboards** for the Yaseer LIS analytics platform. Dashboards are organized by audience and use case. They are built on dbt models running in ClickHouse.

> 💡 **Automated Setup:** Run the script below to create all dashboards automatically via the Metabase API:
>
> ```bash
> python scripts/setup_metabase_dashboards.py \
>     --metabase-url http://localhost:3000 \
>     --metabase-user admin@lab.com \
>     --metabase-pass YOUR_PASSWORD
> ```
>
> See [Preconfigured Setup](#-preconfigured-setup-api-script) below for details.

---

## 🏗️ Architecture

```
MySQL (LIS) → Debezium → RabbitMQ → Consumer → ClickHouse → dbt models → Metabase
```

### Data Models Available

| Model | Type | Best For |
|-------|------|----------|
| `fact_registrations` | Fact | Revenue, orders, patient visits |
| `fact_payments` | Fact | Cash flow, payment mix |
| `fact_order_lines` | Fact | Test volume, profile popularity |
| `fact_test_results` | Fact | Clinical results, abnormal rates |
| `fact_expenses` | Fact | Expense tracking |
| `fact_samples` | Fact | Sample collection tracking |
| `fact_closures` | Fact | Cash drawer reconciliation |
| `tat_analysis` | Fact | Turnaround time |
| `daily_revenue_summary` | Agg | Pre-aggregated daily KPIs |
| `daily_cashflow_summary` | Agg | Daily cash position |
| `profile_popularity` | Agg | Monthly test rankings |
| `dim_patients` | Dim | Patient lookup |
| `dim_branches` | Dim | Branch names |
| `dim_referrals` | Dim | Doctor lookup |
| `dim_profiles` | Dim | Test profile catalog |

---

## 🎯 Dashboard Catalog

### Dashboard 1: 🏢 Executive Overview

**Audience:** Lab owner, management
**Refresh:** Every 5 minutes
**Default filter:** Last 30 days

#### KPI Cards (Top Row)

| Card | Metric | Source | Visualization |
|------|--------|--------|---------------|
| Total Revenue | `SUM(gross_revenue)` | `daily_revenue_summary` | Number (💰) |
| Total Orders | `SUM(total_registrations)` | `daily_revenue_summary` | Number |
| Unique Patients | `SUM(unique_patients)` | `daily_revenue_summary` | Number |
| Avg Order Value | `AVG(avg_order_value)` | `daily_revenue_summary` | Number |
| Outstanding Debt | `SUM(total_outstanding_debt)` | `daily_revenue_summary` | Number (🔴) |

#### Charts

| Card | Query | Visualization |
|------|-------|---------------|
| Revenue Trend | `SELECT report_date, SUM(gross_revenue) FROM daily_revenue_summary GROUP BY report_date ORDER BY report_date` | Area chart |
| Revenue by Branch | `SELECT branch_name, SUM(gross_revenue) FROM daily_revenue_summary GROUP BY branch_name ORDER BY 2 DESC` | Bar chart |
| Revenue by Payer | `SELECT payer_category, SUM(gross_revenue) FROM daily_revenue_summary GROUP BY payer_category` | Donut chart |
| Daily Orders Trend | `SELECT report_date, SUM(total_registrations) FROM daily_revenue_summary GROUP BY report_date` | Line chart |
| New vs Returning | `SELECT CASE WHEN is_new_patient=1 THEN 'New' ELSE 'Returning' END, COUNT(*) FROM fact_registrations GROUP BY 1` | Donut chart |

#### Filters
- **Date Range** → `report_date` (default: Last 30 days)
- **Branch** → `branch_name`

---

### Dashboard 2: 💰 Financial & Cashflow

**Audience:** Finance team, accountant
**Refresh:** Every 5 minutes

#### KPI Cards

| Card | Metric | Source |
|------|--------|--------|
| Net Cash Today | `cash_in - refunds_out - expenses_out WHERE report_date = today()` | `daily_cashflow_summary` |
| Total Cash In | `SUM(cash_in)` | `daily_cashflow_summary` |
| Total Refunds | `SUM(refunds_out)` | `daily_cashflow_summary` |
| Total Expenses | `SUM(expenses_out)` | `daily_cashflow_summary` |
| Debt Collection Rate | `SUM(total_collected) / SUM(gross_revenue) * 100` | `daily_revenue_summary` |

#### Charts

| Card | Query | Visualization |
|------|-------|---------------|
| Daily Net Cash | `SELECT report_date, net_cash FROM daily_cashflow_summary ORDER BY report_date` | Area chart |
| Cash In vs Out | `SELECT report_date, cash_in, (refunds_out + expenses_out) as cash_out FROM daily_cashflow_summary` | Stacked bar |
| Payment Type Mix | `SELECT transaction_type, SUM(abs_amount) FROM fact_payments GROUP BY transaction_type` | Donut chart |
| Expenses by Category | `SELECT category_name, SUM(amount) FROM fact_expenses GROUP BY category_name ORDER BY 2 DESC` | Bar chart |
| Expenses by Branch | `SELECT branch_name, SUM(amount) FROM fact_expenses GROUP BY branch_name` | Bar chart |
| Top Debtors | `SELECT patient_name, SUM(debt) FROM fact_registrations WHERE debt > 0 GROUP BY patient_name ORDER BY 2 DESC LIMIT 20` | Table |

#### Filters
- **Date Range** → `report_date`
- **Branch** → `branch_name`

---

### Dashboard 3: 🧪 Lab Operations

**Audience:** Lab manager, quality team
**Refresh:** Every 2 minutes

#### KPI Cards

| Card | Metric | Source |
|------|--------|--------|
| Tests Today | `COUNT(*) WHERE report_date = today()` | `fact_order_lines` |
| Verification Rate | `COUNT(is_verified=1) / COUNT(*) * 100` | `fact_order_lines` |
| Collection Rate | `COUNT(is_sample_collected=1) / COUNT(*) * 100` | `fact_order_lines` |
| Avg TAT (Verified) | `AVG(total_tat_min)` | `tat_analysis` |

#### Charts

| Card | Query | Visualization |
|------|-------|---------------|
| Test Volume Trend | `SELECT report_date, COUNT(*) FROM fact_order_lines GROUP BY report_date` | Line chart |
| Top 15 Profiles | `SELECT profile_name, COUNT(*) FROM fact_order_lines GROUP BY profile_name ORDER BY 2 DESC LIMIT 15` | Horizontal bar |
| TAT Distribution | `SELECT tat_category, COUNT(*) FROM tat_analysis WHERE verified=1 GROUP BY tat_category` | Donut chart |
| TAT by Profile | `SELECT profile_name, AVG(total_tat_min) as avg_tat FROM tat_analysis WHERE verified=1 GROUP BY profile_name ORDER BY avg_tat DESC LIMIT 15` | Bar chart |
| Pending Verification | `SELECT profile_name, COUNT(*) FROM fact_order_lines WHERE is_verified=0 GROUP BY profile_name ORDER BY 2 DESC LIMIT 10` | Table |
| Sample Collection Status | `SELECT is_collected, COUNT(*) FROM fact_samples GROUP BY is_collected` | Donut chart |
| Hourly Volume | `SELECT toHour(registration_date) as hour, COUNT(*) FROM fact_order_lines GROUP BY hour ORDER BY hour` | Bar chart |

#### Filters
- **Date Range** → `report_date`
- **Branch** → `branch_name`
- **Profile** → `profile_name`

---

### Dashboard 4: 🔬 Clinical Quality

**Audience:** Quality assurance, medical director
**Refresh:** Every 5 minutes

#### KPI Cards

| Card | Metric | Source |
|------|--------|--------|
| Total Results | `COUNT(*)` | `fact_test_results` |
| Abnormal Rate | `COUNT(abnormal_flag IN ('low','high')) / COUNT(*) * 100` | `fact_test_results` |
| Panic Results | `SUM(is_panic)` | `fact_test_results` |
| Verified Rate | `SUM(verified) / COUNT(*) * 100` | `fact_test_results` |

#### Charts

| Card | Query | Visualization |
|------|-------|---------------|
| Abnormal Distribution | `SELECT abnormal_flag, COUNT(*) FROM fact_test_results WHERE abnormal_flag NOT IN ('profile_header','disabled','no_result') GROUP BY abnormal_flag` | Donut chart |
| Most Abnormal Tests | `SELECT test_name, COUNT(*) FROM fact_test_results WHERE abnormal_flag IN ('low','high') GROUP BY test_name ORDER BY 2 DESC LIMIT 15` | Horizontal bar |
| Panic Results List | `SELECT result_date, patient_name, test_name, result, unit_code, normal_from, normal_to FROM fact_test_results WHERE is_panic=1 ORDER BY result_date DESC LIMIT 50` | Table (🚨) |
| Daily Abnormal Rate | `SELECT report_date, countIf(abnormal_flag IN ('low','high')) * 100.0 / count(*) as abnormal_pct FROM fact_test_results GROUP BY report_date` | Line chart |
| Results by Technician | `SELECT resulted_by, COUNT(*) FROM fact_test_results GROUP BY resulted_by ORDER BY 2 DESC` | Bar chart |

#### Filters
- **Date Range** → `report_date`
- **Test Name** → `test_name`
- **Branch** → `branch_name`

---

### Dashboard 5: 👨‍⚕️ Referral & Contract Analysis

**Audience:** Marketing, business development
**Refresh:** Every 15 minutes

#### Charts

| Card | Query | Visualization |
|------|-------|---------------|
| Top Referring Doctors | `SELECT doctor_name, total_referrals, total_revenue FROM dim_referrals ORDER BY total_referrals DESC LIMIT 20` | Table |
| Doctor Revenue Ranking | `SELECT doctor_name, total_revenue FROM dim_referrals WHERE total_revenue > 0 ORDER BY total_revenue DESC LIMIT 15` | Horizontal bar |
| Revenue by Contract | `SELECT contract_name, SUM(total_price) FROM fact_registrations WHERE contract_name != '' GROUP BY contract_name ORDER BY 2 DESC LIMIT 15` | Bar chart |
| Contract vs Cash | `SELECT payer_category, COUNT(*), SUM(total_price) FROM fact_registrations GROUP BY payer_category` | Grouped bar |
| New Referral Trend | `SELECT toStartOfMonth(first_referral_date) as month, COUNT(*) FROM dim_referrals GROUP BY month` | Line chart |

#### Filters
- **Date Range** → `report_date`
- **Doctor** → `doctor_name`

---

### Dashboard 6: 👤 Patient Analytics

**Audience:** Marketing, management
**Refresh:** Every 15 minutes

#### KPI Cards

| Card | Metric | Source |
|------|--------|--------|
| Total Patients | `COUNT(DISTINCT patient_id)` | `dim_patients` |
| New Patients (This Month) | `COUNT(*) WHERE is_new_patient=1 AND report_date >= toStartOfMonth(today())` | `fact_registrations` |
| Avg Lifetime Visits | `AVG(lifetime_visits)` | `dim_patients` |

#### Charts

| Card | Query | Visualization |
|------|-------|---------------|
| New Patient Trend | `SELECT report_date, countIf(is_new_patient=1) FROM fact_registrations GROUP BY report_date` | Line chart |
| Patient Retention | `SELECT visit_order_sequential, COUNT(*) FROM fact_registrations GROUP BY visit_order_sequential ORDER BY 1` | Bar chart |
| Gender Distribution | `SELECT gender, COUNT(*) FROM dim_patients GROUP BY gender` | Donut chart |
| Top Patients by Visits | `SELECT patient_name, lifetime_visits, first_visit_date FROM dim_patients ORDER BY lifetime_visits DESC LIMIT 20` | Table |
| Patient Age Distribution | `SELECT CASE WHEN parsed_dob IS NULL THEN 'Unknown' WHEN dateDiff('year', parsed_dob, today()) < 18 THEN '0-17' WHEN dateDiff('year', parsed_dob, today()) < 30 THEN '18-29' WHEN dateDiff('year', parsed_dob, today()) < 45 THEN '30-44' WHEN dateDiff('year', parsed_dob, today()) < 60 THEN '45-59' ELSE '60+' END as age_group, COUNT(*) FROM dim_patients GROUP BY age_group` | Bar chart |

#### Filters
- **Date Range** → `first_visit_date`
- **Branch** → (via fact_registrations join)

---

### Dashboard 7: 📊 Profile Performance

**Audience:** Lab technical director
**Refresh:** Every 15 minutes

#### Charts

| Card | Query | Visualization |
|------|-------|---------------|
| Monthly Profile Ranking | `SELECT month, profile_name, order_count FROM profile_popularity ORDER BY month DESC, order_count DESC` | Pivot table (month × profile) |
| Collection Rate by Profile | `SELECT profile_name, collection_rate_pct FROM profile_popularity WHERE month = toStartOfMonth(today()) ORDER BY collection_rate_pct ASC LIMIT 15` | Horizontal bar (🟡 worst first) |
| Verification Rate | `SELECT profile_name, verification_rate_pct FROM profile_popularity WHERE month = toStartOfMonth(today()) ORDER BY verification_rate_pct ASC LIMIT 15` | Horizontal bar |
| Revenue per Profile | `SELECT profile_name, SUM(price) FROM fact_order_lines GROUP BY profile_name ORDER BY 2 DESC LIMIT 20` | Bar chart |
| Profile by Branch Heatmap | `SELECT branch_name, profile_name, COUNT(*) FROM fact_order_lines GROUP BY branch_name, profile_name` | Pivot table |

#### Filters
- **Month** → `month`
- **Branch** → `branch_name`

---

## ⚡ Preconfigured Setup (API Script)

Metabase open-source **does not** support file-based dashboard config. However, you can automate dashboard creation using the **Metabase REST API**.

### How It Works

1. The script authenticates with the Metabase API
2. Creates a database connection to ClickHouse (if not exists)
3. Creates collections (folders) for organizing dashboards
4. Creates saved questions (cards) with the correct SQL
5. Creates dashboards and adds cards to them
6. Adds filters and connects them to cards

### Running the Setup Script

```bash
# From the project root
python scripts/setup_metabase_dashboards.py 
    --metabase-url http://localhost:3000 \
    --metabase-user hosam@home.com \
    --metabase-pass ASDasd@123 \
    --clickhouse-host clickhouse \
    --clickhouse-port 8123 \
    --clickhouse-db default
```

```bash
# From the project root
python ../scripts/setup_metabase_dashboards.py --metabase-url http://localhost:3000 --metabase-user hosam@home.com --metabase-pass ASDasd@123 --clickhouse-host clickhouse --clickhouse-port 8123 --clickhouse-db default

```

Or set environment variables:
```bash
export METABASE_URL=http://localhost:3000
export METABASE_USER=hosam@home.com
export METABASE_PASS=ASDasd@123
python scripts/setup_metabase_dashboards.py
```

### What Gets Created

```
📁 Yaseer LIS Analytics/
├── 📊 Executive Overview
├── 💰 Financial & Cashflow
├── 🧪 Lab Operations
├── 🔬 Clinical Quality
├── 👨‍⚕️ Referral & Contract Analysis
├── 👤 Patient Analytics
└── 📊 Profile Performance
```

> ⚠️ **First time only:** You still need to set up Metabase initially (create admin account, connect to ClickHouse database) through the web UI. The script handles everything after that.

---

## 🔧 Metabase Tips

### Connecting to ClickHouse

1. Go to **Admin → Databases → Add Database**
2. Database type: **ClickHouse**
3. Host: `clickhouse` (Docker) or your ClickHouse host
4. Port: `8123`
5. Database name: `default`
6. Username: `default` (or your ClickHouse user)

> 📦 You may need the ClickHouse driver plugin. Download from [Metabase ClickHouse Driver](https://github.com/ClickHouse/metabase-clickhouse-driver/releases) and place in `/plugins/` directory.

### Performance Tips

- Use **pre-aggregated models** (`daily_revenue_summary`, `daily_cashflow_summary`, `profile_popularity`) for KPI cards — they're much faster than raw fact tables
- Set **cache TTL** in Admin → Settings → Caching to reduce query load
- For large fact tables, always add a date filter (Metabase will pass it to ClickHouse)
- Use the `report_date` column (Date type) for all date filters — it's indexed and faster than filtering on DateTime

### Dashboard Filters Best Practice

1. Add a **Date Range** filter mapped to `report_date` on every dashboard
2. Add a **Branch** filter mapped to `branch_name` (shows readable names)
3. Connect filters to **all cards** on the dashboard
4. Set default values: Date = "Last 30 days", Branch = "All"

### Auto-Refresh for Live Ops

- Click the **clock icon** (🕒) on any dashboard
- Set refresh interval: **1 minute** for ops dashboards, **5 minutes** for executive, **15 minutes** for analysis
- Metabase will auto-refresh all cards on the dashboard

### Embedding Dashboards

Metabase supports iframe embedding for external display (e.g., TV screens):
1. Go to **Admin → Settings → Embedding**
2. Enable **Static Embedding**
3. Copy the iframe URL for any dashboard
4. Display on wall-mounted screens for real-time ops monitoring
