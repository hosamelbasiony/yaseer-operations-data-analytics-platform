"""
Metabase Dashboard Setup Script
================================
Creates rich Yaseer LIS analytics dashboards via the Metabase REST API.

Features:
  - Metabase {{template_tags}} with [[ optional clauses ]] for dynamic date filtering
  - Dashboard-level date filter parameters mapped to every dated card
  - Visualization settings for charts, pies, and tables
  - Idempotent: detects existing cards and dashboards to avoid duplicates
  - Correct 18-column grid layout

Usage:
    python scripts/setup_metabase_dashboards.py \\
        --metabase-url http://localhost:3000 \\
        --metabase-user admin@lab.com \\
        --metabase-pass YOUR_PASSWORD

Or set environment variables:
    METABASE_URL, METABASE_USER, METABASE_PASS
"""

import os
import sys
import uuid
import argparse
import requests
from time import sleep

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

COLLECTION_NAME = "Yaseer LIS Analytics"

# Optional date filter fragment appended to SQL for dated cards.
# Metabase removes [[ ]] blocks when the enclosed {{tag}} has no value,
# so queries still return data when the user hasn't set a date filter.
DF = " [[ AND report_date >= {{start_date}} ]] [[ AND report_date <= {{end_date}} ]]"

# Dashboard-level filter widgets (two date pickers)
DASHBOARD_PARAMS = [
    {
        "id": "start_date",
        "name": "Start Date",
        "slug": "start_date",
        "type": "date/single",
        "sectionId": "date",
    },
    {
        "id": "end_date",
        "name": "End Date",
        "slug": "end_date",
        "type": "date/single",
        "sectionId": "date",
    },
]


def make_date_tags():
    """Build Metabase template-tags dict for start_date / end_date."""
    return {
        "start_date": {
            "id": str(uuid.uuid4()),
            "name": "start_date",
            "display-name": "Start Date",
            "type": "date",
        },
        "end_date": {
            "id": str(uuid.uuid4()),
            "name": "end_date",
            "display-name": "End Date",
            "type": "date",
        },
    }


def date_param_mappings(card_id):
    """Parameter mappings that wire dashboard date filters to a card's template tags."""
    return [
        {
            "parameter_id": "start_date",
            "card_id": card_id,
            "target": ["variable", ["template-tag", "start_date"]],
        },
        {
            "parameter_id": "end_date",
            "card_id": card_id,
            "target": ["variable", ["template-tag", "end_date"]],
        },
    ]


# ---------------------------------------------------------------------------
# Dashboard Definitions
# ---------------------------------------------------------------------------
# Each card dict: name, sql, display, w, h, row, col, dated (bool), viz (dict)
#   - dated=True  -> SQL uses {{start_date}}/{{end_date}} template tags
#   - dated=False -> static query, not wired to dashboard date filters
#   - viz         -> Metabase visualization_settings (optional)
#
# Grid: 18 columns wide. KPI row = 6 x 3w x 3h. Charts = 6h. Tables = 8h.
# Column names with dots (from dbt aliases) must use backticks in ClickHouse.
# ---------------------------------------------------------------------------

DASHBOARDS = [
    # ===================================================================
    # 1. EXECUTIVE OVERVIEW
    # ===================================================================
    {
        "name": "Executive Overview",
        "description": "Revenue, orders, patient KPIs, and branch-level performance for management",
        "cards": [
            # --- KPIs (row 0, h=3) ---
            {
                "name": "Total Revenue",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 0,
                "dated": True,
                "sql": "SELECT SUM(gross_revenue) AS total_revenue FROM daily_revenue_summary WHERE 1=1" + DF,
            },
            {
                "name": "Total Orders",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 3,
                "dated": True,
                "sql": "SELECT SUM(total_registrations) AS total_orders FROM daily_revenue_summary WHERE 1=1" + DF,
            },
            {
                "name": "Unique Patients",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 6,
                "dated": True,
                "sql": "SELECT SUM(unique_patients) AS unique_patients FROM daily_revenue_summary WHERE 1=1" + DF,
            },
            {
                "name": "Avg Order Value",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 9,
                "dated": True,
                "sql": "SELECT round(AVG(avg_order_value), 2) AS avg_order_value FROM daily_revenue_summary WHERE 1=1" + DF,
            },
            {
                "name": "Outstanding Debt",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 12,
                "dated": True,
                "sql": "SELECT SUM(total_outstanding_debt) AS debt FROM daily_revenue_summary WHERE 1=1" + DF,
            },
            {
                "name": "Collection Rate %",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 15,
                "dated": True,
                "sql": "SELECT round(SUM(total_collected) * 100.0 / nullIf(SUM(gross_revenue), 0), 1) AS collection_pct FROM daily_revenue_summary WHERE 1=1" + DF,
            },
            # --- Charts row 1 (row 3, h=6) ---
            {
                "name": "Revenue Trend",
                "display": "area",
                "w": 12, "h": 6, "row": 3, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT report_date, SUM(gross_revenue) AS revenue"
                    " FROM daily_revenue_summary WHERE 1=1" + DF +
                    " GROUP BY report_date ORDER BY report_date"
                ),
                "viz": {"graph.dimensions": ["report_date"], "graph.metrics": ["revenue"]},
            },
            {
                "name": "Revenue by Branch",
                "display": "bar",
                "w": 6, "h": 6, "row": 3, "col": 12,
                "dated": True,
                "sql": (
                    "SELECT `b.branch_name` AS branch, SUM(gross_revenue) AS revenue"
                    " FROM daily_revenue_summary WHERE 1=1" + DF +
                    " GROUP BY `b.branch_name` ORDER BY revenue DESC"
                ),
                "viz": {"graph.dimensions": ["branch"], "graph.metrics": ["revenue"]},
            },
            # --- Charts row 2 (row 9, h=6) ---
            {
                "name": "Revenue by Payer Type",
                "display": "pie",
                "w": 6, "h": 6, "row": 9, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT `r.payer_category` AS payer, SUM(gross_revenue) AS revenue"
                    " FROM daily_revenue_summary WHERE 1=1" + DF +
                    " GROUP BY `r.payer_category`"
                ),
                "viz": {"pie.percent_visibility": "inside"},
            },
            {
                "name": "Daily Order Volume",
                "display": "line",
                "w": 6, "h": 6, "row": 9, "col": 6,
                "dated": True,
                "sql": (
                    "SELECT report_date, SUM(total_registrations) AS orders"
                    " FROM daily_revenue_summary WHERE 1=1" + DF +
                    " GROUP BY report_date ORDER BY report_date"
                ),
                "viz": {"graph.dimensions": ["report_date"], "graph.metrics": ["orders"]},
            },
            {
                "name": "New vs Returning Patients",
                "display": "pie",
                "w": 6, "h": 6, "row": 9, "col": 12,
                "dated": True,
                "sql": (
                    "SELECT CASE WHEN is_new_patient = 1 THEN 'New' ELSE 'Returning' END AS type,"
                    " COUNT(*) AS count"
                    " FROM fact_registrations WHERE 1=1" + DF +
                    " GROUP BY type"
                ),
                "viz": {"pie.percent_visibility": "inside"},
            },
            # --- Charts row 3 (row 15, h=6) ---
            {
                "name": "Revenue by Contract (Top 15)",
                "display": "bar",
                "w": 9, "h": 6, "row": 15, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT contract_name, SUM(total_price) AS revenue"
                    " FROM fact_registrations"
                    " WHERE contract_name != '' AND contract_name != 'Cash'" + DF +
                    " GROUP BY contract_name ORDER BY revenue DESC LIMIT 15"
                ),
                "viz": {"graph.dimensions": ["contract_name"], "graph.metrics": ["revenue"]},
            },
            {
                "name": "Top Revenue Days",
                "display": "table",
                "w": 9, "h": 6, "row": 15, "col": 9,
                "dated": True,
                "sql": (
                    "SELECT report_date, SUM(gross_revenue) AS revenue,"
                    " SUM(total_registrations) AS orders, SUM(unique_patients) AS patients"
                    " FROM daily_revenue_summary WHERE 1=1" + DF +
                    " GROUP BY report_date ORDER BY revenue DESC LIMIT 20"
                ),
            },
            # --- Full-width table (row 21, h=8) ---
            {
                "name": "Branch Performance Summary",
                "display": "table",
                "w": 18, "h": 8, "row": 21, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT `b.branch_name` AS branch,"
                    " SUM(gross_revenue) AS revenue, SUM(total_collected) AS collected,"
                    " SUM(total_outstanding_debt) AS debt, SUM(total_registrations) AS orders,"
                    " SUM(unique_patients) AS patients,"
                    " round(SUM(total_collected) * 100.0 / nullIf(SUM(gross_revenue), 0), 1) AS collection_pct"
                    " FROM daily_revenue_summary WHERE 1=1" + DF +
                    " GROUP BY `b.branch_name` ORDER BY revenue DESC"
                ),
            },
        ],
    },

    # ===================================================================
    # 2. FINANCIAL & CASHFLOW
    # ===================================================================
    {
        "name": "Financial & Cashflow",
        "description": "Cash inflows, outflows, expenses, debt tracking, and payment analysis",
        "cards": [
            # --- KPIs (row 0, h=3) ---
            {
                "name": "Net Cash Today",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 0,
                "dated": False,
                "sql": "SELECT SUM(net_cash) AS net_cash FROM daily_cashflow_summary WHERE report_date = today()",
            },
            {
                "name": "Total Cash In",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 3,
                "dated": True,
                "sql": "SELECT SUM(cash_in) AS cash_in FROM daily_cashflow_summary WHERE 1=1" + DF,
            },
            {
                "name": "Total Refunds",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 6,
                "dated": True,
                "sql": "SELECT SUM(refunds_out) AS refunds FROM daily_cashflow_summary WHERE 1=1" + DF,
            },
            {
                "name": "Total Expenses",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 9,
                "dated": True,
                "sql": "SELECT SUM(expenses_out) AS expenses FROM daily_cashflow_summary WHERE 1=1" + DF,
            },
            {
                "name": "Total Discounts",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 12,
                "dated": True,
                "sql": "SELECT SUM(discounts_given) AS discounts FROM daily_cashflow_summary WHERE 1=1" + DF,
            },
            {
                "name": "Net Position",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 15,
                "dated": True,
                "sql": (
                    "SELECT SUM(cash_in) - SUM(refunds_out) - SUM(expenses_out) AS net_position"
                    " FROM daily_cashflow_summary WHERE 1=1" + DF
                ),
            },
            # --- Charts row 1 (row 3, h=6) ---
            {
                "name": "Daily Cash Flow Trend",
                "display": "area",
                "w": 12, "h": 6, "row": 3, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT report_date,"
                    " SUM(cash_in) AS cash_in, SUM(refunds_out) AS refunds,"
                    " SUM(expenses_out) AS expenses, SUM(net_cash) AS net"
                    " FROM daily_cashflow_summary WHERE 1=1" + DF +
                    " GROUP BY report_date ORDER BY report_date"
                ),
                "viz": {
                    "graph.dimensions": ["report_date"],
                    "graph.metrics": ["cash_in", "refunds", "expenses", "net"],
                },
            },
            {
                "name": "Payment Method Mix",
                "display": "pie",
                "w": 6, "h": 6, "row": 3, "col": 12,
                "dated": True,
                "sql": (
                    "SELECT transaction_type, SUM(abs_amount) AS total"
                    " FROM fact_payments WHERE 1=1" + DF +
                    " GROUP BY transaction_type"
                ),
                "viz": {"pie.percent_visibility": "inside"},
            },
            # --- Charts row 2 (row 9, h=6) ---
            {
                "name": "Expenses by Category",
                "display": "bar",
                "w": 9, "h": 6, "row": 9, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT category_name, SUM(amount) AS total"
                    " FROM fact_expenses WHERE 1=1" + DF +
                    " GROUP BY category_name ORDER BY total DESC"
                ),
                "viz": {"graph.dimensions": ["category_name"], "graph.metrics": ["total"]},
            },
            {
                "name": "Expenses by Branch",
                "display": "bar",
                "w": 9, "h": 6, "row": 9, "col": 9,
                "dated": True,
                "sql": (
                    "SELECT branch_name, SUM(amount) AS total"
                    " FROM fact_expenses WHERE 1=1" + DF +
                    " GROUP BY branch_name ORDER BY total DESC"
                ),
                "viz": {"graph.dimensions": ["branch_name"], "graph.metrics": ["total"]},
            },
            # --- Charts row 3 (row 15, h=6) ---
            {
                "name": "Cash In vs Refunds Trend",
                "display": "line",
                "w": 9, "h": 6, "row": 15, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT report_date, SUM(cash_in) AS cash_in, SUM(refunds_out) AS refunds"
                    " FROM daily_cashflow_summary WHERE 1=1" + DF +
                    " GROUP BY report_date ORDER BY report_date"
                ),
                "viz": {
                    "graph.dimensions": ["report_date"],
                    "graph.metrics": ["cash_in", "refunds"],
                },
            },
            {
                "name": "Monthly Revenue Trend",
                "display": "bar",
                "w": 9, "h": 6, "row": 15, "col": 9,
                "dated": True,
                "sql": (
                    "SELECT toStartOfMonth(report_date) AS month, SUM(gross_revenue) AS revenue"
                    " FROM daily_revenue_summary WHERE 1=1" + DF +
                    " GROUP BY month ORDER BY month"
                ),
                "viz": {"graph.dimensions": ["month"], "graph.metrics": ["revenue"]},
            },
            # --- Table (row 21, h=8) ---
            {
                "name": "Top Outstanding Debts",
                "display": "table",
                "w": 18, "h": 8, "row": 21, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT patient_name, contract_name, branch_name,"
                    " COUNT(*) AS visits, SUM(total_price) AS total_billed,"
                    " SUM(paid) AS total_paid, SUM(debt) AS outstanding"
                    " FROM fact_registrations WHERE debt > 0" + DF +
                    " GROUP BY patient_name, contract_name, branch_name"
                    " ORDER BY outstanding DESC LIMIT 30"
                ),
            },
        ],
    },

    # ===================================================================
    # 3. LAB OPERATIONS
    # ===================================================================
    {
        "name": "Lab Operations",
        "description": "Test volumes, verification/collection rates, TAT analysis, and sample tracking",
        "cards": [
            # --- KPIs (row 0, h=3) ---
            {
                "name": "Tests Today",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 0,
                "dated": False,
                "sql": "SELECT COUNT(*) AS tests FROM fact_order_lines WHERE report_date = today()",
            },
            {
                "name": "Total Tests",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 3,
                "dated": True,
                "sql": "SELECT COUNT(*) AS total_tests FROM fact_order_lines WHERE 1=1" + DF,
            },
            {
                "name": "Verification Rate %",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 6,
                "dated": True,
                "sql": (
                    "SELECT round(countIf(is_verified = 1) * 100.0 / count(*), 1) AS pct"
                    " FROM fact_order_lines WHERE 1=1" + DF
                ),
            },
            {
                "name": "Collection Rate %",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 9,
                "dated": True,
                "sql": (
                    "SELECT round(countIf(is_sample_collected = 1) * 100.0 / count(*), 1) AS pct"
                    " FROM fact_order_lines WHERE 1=1" + DF
                ),
            },
            {
                "name": "Avg TAT (min)",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 12,
                "dated": True,
                "sql": (
                    "SELECT round(AVG(total_tat_min), 0) AS avg_tat"
                    " FROM tat_analysis WHERE verified = 1" + DF
                ),
            },
            {
                "name": "Pending Verification",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 15,
                "dated": False,
                "sql": (
                    "SELECT COUNT(*) AS pending"
                    " FROM fact_order_lines WHERE is_verified = 0 AND report_date >= today() - 7"
                ),
            },
            # --- Charts row 1 (row 3, h=6) ---
            {
                "name": "Daily Test Volume",
                "display": "line",
                "w": 12, "h": 6, "row": 3, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT report_date, COUNT(*) AS tests"
                    " FROM fact_order_lines WHERE 1=1" + DF +
                    " GROUP BY report_date ORDER BY report_date"
                ),
                "viz": {"graph.dimensions": ["report_date"], "graph.metrics": ["tests"]},
            },
            {
                "name": "Top 15 Profiles Ordered",
                "display": "bar",
                "w": 6, "h": 6, "row": 3, "col": 12,
                "dated": True,
                "sql": (
                    "SELECT profile_name, COUNT(*) AS orders"
                    " FROM fact_order_lines WHERE 1=1" + DF +
                    " GROUP BY profile_name ORDER BY orders DESC LIMIT 15"
                ),
                "viz": {"graph.dimensions": ["profile_name"], "graph.metrics": ["orders"]},
            },
            # --- Charts row 2 (row 9, h=6) ---
            {
                "name": "TAT Distribution",
                "display": "pie",
                "w": 6, "h": 6, "row": 9, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT tat_category, COUNT(*) AS count"
                    " FROM tat_analysis WHERE verified = 1" + DF +
                    " GROUP BY tat_category"
                ),
                "viz": {"pie.percent_visibility": "inside"},
            },
            {
                "name": "Avg TAT by Profile (Top 15)",
                "display": "bar",
                "w": 6, "h": 6, "row": 9, "col": 6,
                "dated": True,
                "sql": (
                    "SELECT profile_name, round(AVG(total_tat_min), 0) AS avg_tat"
                    " FROM tat_analysis WHERE verified = 1" + DF +
                    " GROUP BY profile_name ORDER BY avg_tat DESC LIMIT 15"
                ),
                "viz": {"graph.dimensions": ["profile_name"], "graph.metrics": ["avg_tat"]},
            },
            {
                "name": "Hourly Registration Volume",
                "display": "bar",
                "w": 6, "h": 6, "row": 9, "col": 12,
                "dated": True,
                "sql": (
                    "SELECT toHour(registration_date) AS hour, COUNT(*) AS tests"
                    " FROM fact_order_lines WHERE 1=1" + DF +
                    " GROUP BY hour ORDER BY hour"
                ),
                "viz": {"graph.dimensions": ["hour"], "graph.metrics": ["tests"]},
            },
            # --- Charts row 3 (row 15, h=6) ---
            {
                "name": "Sample Collection Status",
                "display": "pie",
                "w": 6, "h": 6, "row": 15, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT CASE WHEN is_collected = 1 THEN 'Collected' ELSE 'Pending' END AS status,"
                    " COUNT(*) AS count"
                    " FROM fact_samples WHERE 1=1" + DF +
                    " GROUP BY status"
                ),
                "viz": {"pie.percent_visibility": "inside"},
            },
            {
                "name": "Tests by Branch",
                "display": "bar",
                "w": 6, "h": 6, "row": 15, "col": 6,
                "dated": True,
                "sql": (
                    "SELECT branch_name, COUNT(*) AS tests"
                    " FROM fact_order_lines WHERE 1=1" + DF +
                    " GROUP BY branch_name ORDER BY tests DESC"
                ),
                "viz": {"graph.dimensions": ["branch_name"], "graph.metrics": ["tests"]},
            },
            {
                "name": "Order Status Breakdown",
                "display": "pie",
                "w": 6, "h": 6, "row": 15, "col": 12,
                "dated": True,
                "sql": (
                    "SELECT status_description, COUNT(*) AS count"
                    " FROM fact_order_lines WHERE 1=1" + DF +
                    " GROUP BY status_description"
                ),
                "viz": {"pie.percent_visibility": "inside"},
            },
            # --- Table (row 21, h=8) ---
            {
                "name": "Pending Verification Details",
                "display": "table",
                "w": 18, "h": 8, "row": 21, "col": 0,
                "dated": False,
                "sql": (
                    "SELECT report_date, patient_name, profile_name, branch_name,"
                    " receptionist, registration_date, status_description"
                    " FROM fact_order_lines"
                    " WHERE is_verified = 0 AND report_date >= today() - 7"
                    " ORDER BY registration_date DESC LIMIT 50"
                ),
            },
        ],
    },

    # ===================================================================
    # 4. CLINICAL QUALITY
    # ===================================================================
    {
        "name": "Clinical Quality",
        "description": "Abnormal rates, panic values, result quality metrics, and QA monitoring",
        "cards": [
            # --- KPIs (row 0, h=3) ---
            {
                "name": "Total Results",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 0,
                "dated": True,
                "sql": "SELECT COUNT(*) AS total FROM fact_test_results WHERE 1=1" + DF,
            },
            {
                "name": "Abnormal Rate %",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 3,
                "dated": True,
                "sql": (
                    "SELECT round(countIf(abnormal_flag IN ('low', 'high')) * 100.0 / count(*), 1) AS pct"
                    " FROM fact_test_results"
                    " WHERE abnormal_flag NOT IN ('profile_header', 'disabled', 'no_result')" + DF
                ),
            },
            {
                "name": "Panic Results",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 6,
                "dated": True,
                "sql": "SELECT SUM(is_panic) AS panic_count FROM fact_test_results WHERE 1=1" + DF,
            },
            {
                "name": "Normal Rate %",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 9,
                "dated": True,
                "sql": (
                    "SELECT round(countIf(abnormal_flag = 'normal') * 100.0 / count(*), 1) AS pct"
                    " FROM fact_test_results"
                    " WHERE abnormal_flag NOT IN ('profile_header', 'disabled', 'no_result')" + DF
                ),
            },
            {
                "name": "High Results",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 12,
                "dated": True,
                "sql": "SELECT countIf(abnormal_flag = 'high') AS high_count FROM fact_test_results WHERE 1=1" + DF,
            },
            {
                "name": "Low Results",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 15,
                "dated": True,
                "sql": "SELECT countIf(abnormal_flag = 'low') AS low_count FROM fact_test_results WHERE 1=1" + DF,
            },
            # --- Charts row 1 (row 3, h=6) ---
            {
                "name": "Abnormal Distribution",
                "display": "pie",
                "w": 6, "h": 6, "row": 3, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT abnormal_flag, COUNT(*) AS count"
                    " FROM fact_test_results"
                    " WHERE abnormal_flag NOT IN ('profile_header', 'disabled', 'no_result')" + DF +
                    " GROUP BY abnormal_flag"
                ),
                "viz": {"pie.percent_visibility": "inside"},
            },
            {
                "name": "Top Abnormal Tests",
                "display": "bar",
                "w": 6, "h": 6, "row": 3, "col": 6,
                "dated": True,
                "sql": (
                    "SELECT test_name, COUNT(*) AS count"
                    " FROM fact_test_results"
                    " WHERE abnormal_flag IN ('low', 'high')" + DF +
                    " GROUP BY test_name ORDER BY count DESC LIMIT 15"
                ),
                "viz": {"graph.dimensions": ["test_name"], "graph.metrics": ["count"]},
            },
            {
                "name": "Daily Abnormal Rate Trend",
                "display": "line",
                "w": 6, "h": 6, "row": 3, "col": 12,
                "dated": True,
                "sql": (
                    "SELECT report_date,"
                    " round(countIf(abnormal_flag IN ('low', 'high')) * 100.0 / count(*), 1) AS abnormal_pct"
                    " FROM fact_test_results"
                    " WHERE abnormal_flag NOT IN ('profile_header', 'disabled', 'no_result')" + DF +
                    " GROUP BY report_date ORDER BY report_date"
                ),
                "viz": {"graph.dimensions": ["report_date"], "graph.metrics": ["abnormal_pct"]},
            },
            # --- Charts row 2 (row 9, h=6) ---
            {
                "name": "Results by Technician",
                "display": "bar",
                "w": 9, "h": 6, "row": 9, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT resulted_by, COUNT(*) AS results,"
                    " countIf(abnormal_flag IN ('low', 'high')) AS abnormal"
                    " FROM fact_test_results WHERE resulted_by != ''" + DF +
                    " GROUP BY resulted_by ORDER BY results DESC LIMIT 15"
                ),
                "viz": {
                    "graph.dimensions": ["resulted_by"],
                    "graph.metrics": ["results", "abnormal"],
                },
            },
            {
                "name": "Abnormal by Branch",
                "display": "bar",
                "w": 9, "h": 6, "row": 9, "col": 9,
                "dated": True,
                "sql": (
                    "SELECT branch_name,"
                    " countIf(abnormal_flag IN ('low', 'high')) AS abnormal, COUNT(*) AS total"
                    " FROM fact_test_results"
                    " WHERE abnormal_flag NOT IN ('profile_header', 'disabled', 'no_result')" + DF +
                    " GROUP BY branch_name ORDER BY abnormal DESC"
                ),
                "viz": {
                    "graph.dimensions": ["branch_name"],
                    "graph.metrics": ["abnormal", "total"],
                },
            },
            # --- Table (row 15, h=8) ---
            {
                "name": "Panic Results Detail",
                "display": "table",
                "w": 18, "h": 8, "row": 15, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT result_date, patient_name, test_name, result,"
                    " `tel.unit_code` AS unit, normal_from, normal_to,"
                    " branch_name, resulted_by"
                    " FROM fact_test_results WHERE is_panic = 1" + DF +
                    " ORDER BY result_date DESC LIMIT 50"
                ),
            },
        ],
    },

    # ===================================================================
    # 5. REFERRAL & CONTRACT ANALYSIS
    # ===================================================================
    {
        "name": "Referral & Contract Analysis",
        "description": "Doctor referral volumes, contract revenue, and partnership analytics",
        "cards": [
            # --- KPIs (row 0, h=3) ---
            {
                "name": "Total Doctors",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 0,
                "dated": False,
                "sql": "SELECT COUNT(*) AS total FROM dim_referrals",
            },
            {
                "name": "Active Doctors",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 3,
                "dated": False,
                "sql": "SELECT COUNT(*) AS active FROM dim_referrals WHERE total_referrals > 0",
            },
            {
                "name": "Total Referrals",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 6,
                "dated": False,
                "sql": "SELECT SUM(total_referrals) AS total FROM dim_referrals",
            },
            {
                "name": "Referral Revenue",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 9,
                "dated": False,
                "sql": "SELECT SUM(total_revenue) AS revenue FROM dim_referrals",
            },
            {
                "name": "Avg Revenue / Doctor",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 12,
                "dated": False,
                "sql": "SELECT round(AVG(total_revenue), 0) AS avg FROM dim_referrals WHERE total_referrals > 0",
            },
            {
                "name": "Contracts Active",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 15,
                "dated": True,
                "sql": (
                    "SELECT COUNT(DISTINCT contract_name) AS contracts"
                    " FROM fact_registrations"
                    " WHERE contract_name != '' AND contract_name != 'Cash'" + DF
                ),
            },
            # --- Charts row 1 (row 3, h=6) ---
            {
                "name": "Doctor Revenue Ranking (Top 20)",
                "display": "bar",
                "w": 9, "h": 6, "row": 3, "col": 0,
                "dated": False,
                "sql": (
                    "SELECT doctor_name, total_revenue"
                    " FROM dim_referrals WHERE total_revenue > 0"
                    " ORDER BY total_revenue DESC LIMIT 20"
                ),
                "viz": {"graph.dimensions": ["doctor_name"], "graph.metrics": ["total_revenue"]},
            },
            {
                "name": "Contract vs Cash Revenue",
                "display": "pie",
                "w": 9, "h": 6, "row": 3, "col": 9,
                "dated": True,
                "sql": (
                    "SELECT payer_category, SUM(total_price) AS revenue"
                    " FROM fact_registrations WHERE 1=1" + DF +
                    " GROUP BY payer_category"
                ),
                "viz": {"pie.percent_visibility": "inside"},
            },
            # --- Charts row 2 (row 9, h=6) ---
            {
                "name": "Revenue by Contract (Top 15)",
                "display": "bar",
                "w": 9, "h": 6, "row": 9, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT contract_name, SUM(total_price) AS revenue"
                    " FROM fact_registrations"
                    " WHERE contract_name != '' AND contract_name != 'Cash'" + DF +
                    " GROUP BY contract_name ORDER BY revenue DESC LIMIT 15"
                ),
                "viz": {"graph.dimensions": ["contract_name"], "graph.metrics": ["revenue"]},
            },
            {
                "name": "Monthly Referral Trend",
                "display": "line",
                "w": 9, "h": 6, "row": 9, "col": 9,
                "dated": True,
                "sql": (
                    "SELECT toStartOfMonth(report_date) AS month, COUNT(*) AS referrals"
                    " FROM fact_registrations WHERE referral_id > 0" + DF +
                    " GROUP BY month ORDER BY month"
                ),
                "viz": {"graph.dimensions": ["month"], "graph.metrics": ["referrals"]},
            },
            # --- Table (row 15, h=8) ---
            {
                "name": "Full Referral Directory",
                "display": "table",
                "w": 18, "h": 8, "row": 15, "col": 0,
                "dated": False,
                "sql": (
                    "SELECT doctor_name, doctor_title, speciality,"
                    " total_referrals, unique_patients, total_revenue,"
                    " first_referral_date, last_referral_date"
                    " FROM dim_referrals WHERE total_referrals > 0"
                    " ORDER BY total_referrals DESC LIMIT 30"
                ),
            },
        ],
    },

    # ===================================================================
    # 6. PATIENT ANALYTICS
    # ===================================================================
    {
        "name": "Patient Analytics",
        "description": "Patient demographics, retention, lifecycle analysis, and population insights",
        "cards": [
            # --- KPIs (row 0, h=3) ---
            {
                "name": "Total Patients",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 0,
                "dated": False,
                "sql": "SELECT COUNT(*) AS total FROM dim_patients",
            },
            {
                "name": "New Patients (Period)",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 3,
                "dated": True,
                "sql": (
                    "SELECT countIf(is_new_patient = 1) AS new_patients"
                    " FROM fact_registrations WHERE 1=1" + DF
                ),
            },
            {
                "name": "Avg Lifetime Visits",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 6,
                "dated": False,
                "sql": "SELECT round(AVG(lifetime_visits), 1) AS avg FROM dim_patients WHERE lifetime_visits > 0",
            },
            {
                "name": "Male %",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 9,
                "dated": False,
                "sql": "SELECT round(countIf(gender = 1) * 100.0 / count(*), 1) AS male_pct FROM dim_patients",
            },
            {
                "name": "Female %",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 12,
                "dated": False,
                "sql": "SELECT round(countIf(gender = 2) * 100.0 / count(*), 1) AS female_pct FROM dim_patients",
            },
            {
                "name": "Nationalities",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 15,
                "dated": False,
                "sql": "SELECT COUNT(DISTINCT nationality) AS count FROM dim_patients WHERE nationality != ''",
            },
            # --- Charts row 1 (row 3, h=6) ---
            {
                "name": "New Patient Trend",
                "display": "line",
                "w": 9, "h": 6, "row": 3, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT report_date, countIf(is_new_patient = 1) AS new_patients"
                    " FROM fact_registrations WHERE 1=1" + DF +
                    " GROUP BY report_date ORDER BY report_date"
                ),
                "viz": {"graph.dimensions": ["report_date"], "graph.metrics": ["new_patients"]},
            },
            {
                "name": "Gender Distribution",
                "display": "pie",
                "w": 9, "h": 6, "row": 3, "col": 9,
                "dated": False,
                "sql": (
                    "SELECT CASE WHEN gender = 1 THEN 'Male'"
                    " WHEN gender = 2 THEN 'Female' ELSE 'Unknown' END AS gender,"
                    " COUNT(*) AS count FROM dim_patients GROUP BY gender"
                ),
                "viz": {"pie.percent_visibility": "inside"},
            },
            # --- Charts row 2 (row 9, h=6) ---
            {
                "name": "Visit Retention Funnel",
                "display": "bar",
                "w": 9, "h": 6, "row": 9, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT visit_order_sequential AS visit_number, COUNT(*) AS patients"
                    " FROM fact_registrations WHERE visit_order_sequential <= 10" + DF +
                    " GROUP BY visit_number ORDER BY visit_number"
                ),
                "viz": {"graph.dimensions": ["visit_number"], "graph.metrics": ["patients"]},
            },
            {
                "name": "Age Distribution",
                "display": "bar",
                "w": 9, "h": 6, "row": 9, "col": 9,
                "dated": False,
                "sql": (
                    "SELECT multiIf("
                    " age < 1, '0-1', age < 5, '1-4', age < 13, '5-12',"
                    " age < 18, '13-17', age < 30, '18-29', age < 45, '30-44',"
                    " age < 60, '45-59', '60+') AS age_group, COUNT(*) AS count"
                    " FROM (SELECT dateDiff('year', parsed_dob, today()) AS age"
                    " FROM dim_patients WHERE parsed_dob > '1900-01-01')"
                    " GROUP BY age_group ORDER BY age_group"
                ),
                "viz": {"graph.dimensions": ["age_group"], "graph.metrics": ["count"]},
            },
            # --- Charts row 3 (row 15, h=6) ---
            {
                "name": "Top Nationalities",
                "display": "pie",
                "w": 9, "h": 6, "row": 15, "col": 0,
                "dated": False,
                "sql": (
                    "SELECT nationality, COUNT(*) AS count FROM dim_patients"
                    " WHERE nationality != ''"
                    " GROUP BY nationality ORDER BY count DESC LIMIT 10"
                ),
                "viz": {"pie.percent_visibility": "inside"},
            },
            {
                "name": "Top Patients by Visits",
                "display": "table",
                "w": 9, "h": 6, "row": 15, "col": 9,
                "dated": False,
                "sql": (
                    "SELECT patient_name, lifetime_visits, first_visit_date,"
                    " CASE WHEN gender = 1 THEN 'Male'"
                    " WHEN gender = 2 THEN 'Female' ELSE '-' END AS gender,"
                    " nationality"
                    " FROM dim_patients WHERE lifetime_visits > 0"
                    " ORDER BY lifetime_visits DESC LIMIT 25"
                ),
            },
        ],
    },

    # ===================================================================
    # 7. STAFF & PROFILE PERFORMANCE
    # ===================================================================
    {
        "name": "Staff & Profile Performance",
        "description": "Employee productivity, profile trends, collection rates, and workload analysis",
        "cards": [
            # --- KPIs (row 0, h=3) ---
            {
                "name": "Active Staff",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 0,
                "dated": True,
                "sql": "SELECT COUNT(DISTINCT username) AS staff FROM fact_user_performance WHERE 1=1" + DF,
            },
            {
                "name": "Total Profiles",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 3,
                "dated": False,
                "sql": "SELECT COUNT(*) AS total FROM dim_profiles WHERE total_orders > 0",
            },
            {
                "name": "Avg Staff Revenue",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 6,
                "dated": True,
                "sql": (
                    "SELECT round(AVG(total_income), 0) AS avg_revenue"
                    " FROM (SELECT username, SUM(gross_income) AS total_income"
                    " FROM fact_user_performance WHERE 1=1" + DF +
                    " GROUP BY username)"
                ),
            },
            {
                "name": "Top Staff Revenue",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 9,
                "dated": True,
                "sql": (
                    "SELECT MAX(total_income) AS top_revenue"
                    " FROM (SELECT username, SUM(gross_income) AS total_income"
                    " FROM fact_user_performance WHERE 1=1" + DF +
                    " GROUP BY username)"
                ),
            },
            {
                "name": "Total Visit Count",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 12,
                "dated": True,
                "sql": "SELECT SUM(visit_count) AS total FROM fact_user_performance WHERE 1=1" + DF,
            },
            {
                "name": "Total Outstanding",
                "display": "scalar",
                "w": 3, "h": 3, "row": 0, "col": 15,
                "dated": True,
                "sql": "SELECT SUM(outstanding_debt) AS total FROM fact_user_performance WHERE 1=1" + DF,
            },
            # --- Charts row 1 (row 3, h=6) ---
            {
                "name": "Staff Revenue Ranking",
                "display": "bar",
                "w": 9, "h": 6, "row": 3, "col": 0,
                "dated": True,
                "sql": (
                    "SELECT username, SUM(gross_income) AS revenue"
                    " FROM fact_user_performance WHERE 1=1" + DF +
                    " GROUP BY username ORDER BY revenue DESC LIMIT 15"
                ),
                "viz": {"graph.dimensions": ["username"], "graph.metrics": ["revenue"]},
            },
            {
                "name": "Staff Workload (Visits)",
                "display": "bar",
                "w": 9, "h": 6, "row": 3, "col": 9,
                "dated": True,
                "sql": (
                    "SELECT username, SUM(visit_count) AS visits"
                    " FROM fact_user_performance WHERE 1=1" + DF +
                    " GROUP BY username ORDER BY visits DESC LIMIT 15"
                ),
                "viz": {"graph.dimensions": ["username"], "graph.metrics": ["visits"]},
            },
            # --- Charts row 2 (row 9, h=6) ---
            {
                "name": "Worst Collection Rates",
                "display": "bar",
                "w": 9, "h": 6, "row": 9, "col": 0,
                "dated": False,
                "sql": (
                    "SELECT profile_name, collection_rate_pct"
                    " FROM profile_popularity"
                    " WHERE month = toStartOfMonth(today()) AND order_count > 5"
                    " ORDER BY collection_rate_pct ASC LIMIT 15"
                ),
                "viz": {"graph.dimensions": ["profile_name"], "graph.metrics": ["collection_rate_pct"]},
            },
            {
                "name": "Revenue per Profile (Top 20)",
                "display": "bar",
                "w": 9, "h": 6, "row": 9, "col": 9,
                "dated": True,
                "sql": (
                    "SELECT profile_name, SUM(price) AS revenue"
                    " FROM fact_order_lines WHERE 1=1" + DF +
                    " GROUP BY profile_name ORDER BY revenue DESC LIMIT 20"
                ),
                "viz": {"graph.dimensions": ["profile_name"], "graph.metrics": ["revenue"]},
            },
            # --- Table (row 15, h=8) ---
            {
                "name": "Monthly Profile Ranking",
                "display": "table",
                "w": 18, "h": 8, "row": 15, "col": 0,
                "dated": False,
                "sql": (
                    "SELECT month, profile_name, branch_name, payer_category,"
                    " order_count, unique_patients, collection_rate_pct, verification_rate_pct"
                    " FROM profile_popularity"
                    " WHERE month >= toStartOfMonth(today() - INTERVAL 6 MONTH)"
                    " ORDER BY month DESC, order_count DESC LIMIT 100"
                ),
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------

class MetabaseAPI:
    def __init__(self, base_url, username, password):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self._login(username, password)

    def _login(self, username, password):
        resp = self.session.post(
            f"{self.base_url}/api/session",
            json={"username": username, "password": password},
        )
        resp.raise_for_status()
        self.session.headers.update({"X-Metabase-Session": resp.json()["id"]})
        print(f"  Authenticated as {username}")

    def get(self, endpoint):
        resp = self.session.get(f"{self.base_url}/api{endpoint}")
        resp.raise_for_status()
        return resp.json()

    def post(self, endpoint, data):
        resp = self.session.post(f"{self.base_url}/api{endpoint}", json=data)
        resp.raise_for_status()
        return resp.json()

    def put(self, endpoint, data):
        resp = self.session.put(f"{self.base_url}/api{endpoint}", json=data)
        resp.raise_for_status()
        return resp.json()

    # -- High-level helpers ------------------------------------------------

    def find_database(self, name_contains="clickhouse"):
        dbs = self.get("/database")
        items = dbs.get("data", dbs) if isinstance(dbs, dict) else dbs
        for db in items:
            engine = db.get("engine", "")
            db_name = db.get("name", "")
            if name_contains.lower() in engine.lower() or name_contains.lower() in db_name.lower():
                print(f"  Found database: {db_name} (id={db['id']}, engine={engine})")
                return db["id"]
        for db in items:
            if not db.get("is_sample", False):
                print(f"  Using fallback database: {db['name']} (id={db['id']})")
                return db["id"]
        raise RuntimeError(
            "No ClickHouse database found in Metabase. Add it via Admin > Databases first."
        )

    def create_collection(self, name, description=""):
        for c in self.get("/collection"):
            if c["name"] == name:
                print(f"  Collection exists: {name} (id={c['id']})")
                return c["id"]
        result = self.post("/collection", {"name": name, "description": description})
        print(f"  Created collection: {name} (id={result['id']})")
        return result["id"]

    def _collection_items(self, collection_id, model=None):
        qs = f"?models={model}" if model else ""
        items = self.get(f"/collection/{collection_id}/items{qs}")
        return items.get("data", items) if isinstance(items, dict) else items

    def find_card_in_collection(self, collection_id, name):
        for item in self._collection_items(collection_id, model="card"):
            if item.get("name") == name:
                return item["id"]
        return None

    def create_native_card(self, name, sql, display, database_id, collection_id,
                           template_tags=None, viz=None):
        existing = self.find_card_in_collection(collection_id, name)
        if existing:
            print(f"    Card exists: {name} (id={existing})")
            return existing

        native = {"query": sql}
        if template_tags:
            native["template-tags"] = template_tags

        result = self.post("/card", {
            "name": name,
            "dataset_query": {
                "type": "native",
                "native": native,
                "database": database_id,
            },
            "display": display,
            "visualization_settings": viz or {},
            "collection_id": collection_id,
        })
        print(f"    Created card: {name} (id={result['id']})")
        return result["id"]

    def create_dashboard(self, name, description, collection_id, parameters=None):
        for item in self._collection_items(collection_id):
            if item.get("name") == name and item.get("model") == "dashboard":
                dash_id = item["id"]
                if parameters:
                    self.put(f"/dashboard/{dash_id}", {"parameters": parameters})
                print(f"  Dashboard exists: {name} (id={dash_id})")
                return dash_id

        payload = {
            "name": name,
            "description": description,
            "collection_id": collection_id,
        }
        if parameters:
            payload["parameters"] = parameters
        result = self.post("/dashboard", payload)
        print(f"  Created dashboard: {name} (id={result['id']})")
        return result["id"]

    def add_cards_to_dashboard(self, dashboard_id, card_specs):
        """
        Add cards to a dashboard.
        card_specs: list of (card_id, w, h, row, col, parameter_mappings)
        """
        dash = self.get(f"/dashboard/{dashboard_id}")
        existing = dash.get("dashcards", dash.get("ordered_cards", []))
        existing_card_ids = {dc.get("card_id") for dc in existing}

        new_dashcards = []
        for i, (card_id, w, h, row, col, mappings) in enumerate(card_specs):
            if card_id in existing_card_ids:
                continue
            dc = {
                "id": -(i + 1),
                "card_id": card_id,
                "size_x": w,
                "size_y": h,
                "row": row,
                "col": col,
            }
            if mappings:
                dc["parameter_mappings"] = mappings
            new_dashcards.append(dc)

        if new_dashcards:
            self.put(f"/dashboard/{dashboard_id}", {
                "dashcards": existing + new_dashcards,
            })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Setup Metabase dashboards for Yaseer LIS Analytics"
    )
    parser.add_argument(
        "--metabase-url",
        default=os.environ.get("METABASE_URL", "http://localhost:3000"),
    )
    parser.add_argument(
        "--metabase-user",
        default=os.environ.get("METABASE_USER", "hosam@home.com"),
    )
    parser.add_argument(
        "--metabase-pass",
        default=os.environ.get("METABASE_PASS", "ASDasd@123"),
    )
    args = parser.parse_args()

    if not args.metabase_pass:
        print("Error: Metabase password required. Use --metabase-pass or METABASE_PASS env var.")
        sys.exit(1)

    print("=" * 60)
    print("  Metabase Dashboard Setup - Yaseer LIS Analytics")
    print("=" * 60)
    print(f"  URL:  {args.metabase_url}")
    print(f"  User: {args.metabase_user}")
    print()

    api = MetabaseAPI(args.metabase_url, args.metabase_user, args.metabase_pass)
    db_id = api.find_database("clickhouse")
    collection_id = api.create_collection(COLLECTION_NAME, "Yaseer LIS Analytics Dashboards")

    total_cards = 0

    for dash_config in DASHBOARDS:
        print(f"\n{'─' * 55}")
        print(f"  Setting up: {dash_config['name']}")
        print(f"{'─' * 55}")

        dashboard_id = api.create_dashboard(
            dash_config["name"],
            dash_config.get("description", ""),
            collection_id,
            parameters=DASHBOARD_PARAMS,
        )

        card_specs = []
        for card in dash_config["cards"]:
            dated = card.get("dated", False)
            template_tags = make_date_tags() if dated else None

            card_id = api.create_native_card(
                name=card["name"],
                sql=card["sql"],
                display=card["display"],
                database_id=db_id,
                collection_id=collection_id,
                template_tags=template_tags,
                viz=card.get("viz"),
            )

            mappings = date_param_mappings(card_id) if dated else []

            card_specs.append((
                card_id,
                card.get("w", 6),
                card.get("h", 4),
                card.get("row", 0),
                card.get("col", 0),
                mappings,
            ))
            sleep(0.15)

        if card_specs:
            api.add_cards_to_dashboard(dashboard_id, card_specs)
            count = len(card_specs)
            total_cards += count
            print(f"  Added {count} cards to dashboard")

    print(f"\n{'=' * 60}")
    print(f"  Setup complete! {len(DASHBOARDS)} dashboards, {total_cards} cards created.")
    print(f"  Open: {args.metabase_url}/collection/{collection_id}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
