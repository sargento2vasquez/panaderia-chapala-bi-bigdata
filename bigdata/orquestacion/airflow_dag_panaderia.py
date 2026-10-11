"""DAG de Apache Airflow para el pipeline Big Data de la Panadería Chapala.

Copie este archivo a la carpeta dags/ de Airflow y defina la variable PANADERIA_REPO
con la ruta del repositorio (Admin -> Variables). Se ejecuta todos los días a las 02:00
(hora de Lima), después del cierre de caja.

ingesta -> transformacion -> calidad -> consultas        (diario)
experimento                                               (manual, disparado a pedido)
"""
from datetime import datetime, timedelta

import pendulum
from airflow import DAG
from airflow.models import Variable
from airflow.operators.bash import BashOperator

REPO = Variable.get("PANADERIA_REPO", default_var="/opt/panaderia-chapala-bi-bigdata")
CMD = f"cd {REPO} && python bigdata/run_pipeline.py --etapas {{etapa}}"

default_args = {
    "owner": "grupo-panaderia-chapala",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=1),
}

with DAG(
    dag_id="panaderia_chapala_bigdata",
    description="Ingesta CSV/JDBC -> Parquet (bronce/plata/oro) -> calidad -> consultas Spark SQL",
    start_date=pendulum.datetime(2026, 10, 1, tz="America/Lima"),
    schedule="0 2 * * *",
    catchup=False,
    default_args=default_args,
    tags=["panaderia", "spark", "bigdata"],
) as dag:
    ingesta = BashOperator(task_id="ingesta", bash_command=CMD.format(etapa="ingesta"))
    transformacion = BashOperator(task_id="transformacion", bash_command=CMD.format(etapa="transformacion"))
    calidad = BashOperator(task_id="calidad", bash_command=CMD.format(etapa="calidad"))
    consultas = BashOperator(task_id="consultas", bash_command=CMD.format(etapa="consultas"))

    ingesta >> transformacion >> calidad >> consultas

with DAG(
    dag_id="panaderia_chapala_experimento",
    description="Experimento de tiempos de consulta Spark (x1, x10, x50)",
    start_date=pendulum.datetime(2026, 10, 1, tz="America/Lima"),
    schedule=None,
    catchup=False,
    default_args=default_args,
    tags=["panaderia", "experimento"],
) as dag_exp:
    BashOperator(task_id="experimento", bash_command=CMD.format(etapa="experimento"))
