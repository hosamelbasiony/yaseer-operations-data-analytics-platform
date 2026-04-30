from airflow import DAG
from airflow.providers.standard.operators.bash import BashOperator
from datetime import datetime

with DAG(
    'yaseer_dbt_pipeline',
    start_date=datetime(2024, 1, 1),
    # schedule='@daily',
    schedule='*/10 * * * *',
    catchup=False
) as dag:

    dbt_debug = BashOperator(
        task_id='dbt_debug',
        bash_command='cd /opt/airflow/dbt_project && /home/airflow/.local/bin/dbt debug'
    )

    dbt_run = BashOperator(
        task_id='dbt_run',
        bash_command='cd /opt/airflow/dbt_project && /home/airflow/.local/bin/dbt run --full-refresh'
    )

    dbt_debug >> dbt_run
