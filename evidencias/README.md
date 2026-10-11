# Evidencias

Guardar aquí las capturas y archivos que prueban cada componente. Los nombres permiten citarlos en el informe.

| # | Archivo | Qué debe mostrar | Cómo obtenerlo |
|---|---|---|---|
| BI-01 | `bi/01_oltp_conteo.png` | 27 tablas con su número de filas (todas en `ok = 1`) | `04_pruebas_oltp.sql`, bloque 1.1 |
| BI-02 | `bi/02_dw_etl_log.png` | Bitácora del ETL con filas y ms por paso, estado OK | Final de `03_dw_etl.sql` |
| BI-03 | `bi/03_dw_conciliacion.png` | OLTP 190 761.92 vs DW 190 289.42 | `05_consultas_dw.sql`, bloque B |
| BI-04 | `bi/04_dw_diagrama.png` | Diagrama del esquema `dw` (5 dimensiones, 4 hechos) | SSMS → Diagramas de base de datos |
| BI-05 | `bi/05_pbi_modelo.png` | Vista de modelo de Power BI con las 11 relaciones | Power BI → Vista de modelo |
| BI-06 | `bi/06_pbi_ventas.png` | Página Ventas con S/ 190 289.42 y 7 813 ventas | Power BI, sin filtros |
| BI-07 | `bi/07_pbi_produccion.png` | Página Producción y merma (12.5 %) | Power BI |
| BI-08 | `bi/08_pbi_inventario.png` | Página Inventario y compras (S/ 55 263.06) | Power BI |
| BI-09 | `bi/09_pbi_filtro.png` | Un filtro aplicado (ej. Mes = Set) y las cifras cambiando | Power BI |
| BD-01 | `bigdata/01_pipeline_log.png` | Consola de `run_pipeline.py` con las etapas OK | Colab / terminal |
| BD-02 | `bigdata/02_particiones.png` | Carpetas `anio=2026/mes=…` de `fact_ventas` | Celda 3 del cuaderno |
| BD-03 | `bigdata/03_metricas.png` | Tabla de `logs/metricas.jsonl` (filas y segundos) | Celda 3 del cuaderno |
| BD-04 | `bigdata/04_calidad.json` | Reporte de calidad (0 críticos, 3 avisos) | Copiar de `logs/` |
| BD-05 | `bigdata/05_consultas.png` | Resultado de Q1, Q2 y Q4 en Spark SQL | Celda 4 del cuaderno |
| BD-06 | `bigdata/06_plan_ejecucion.png` | `explain` con BroadcastHashJoin y filtros | Celda 5 del cuaderno |
| BD-07 | `bigdata/07_spark_ui.png` | Spark UI (Jobs/Stages) durante la ejecución | http://localhost:4040 |
| BD-08 | `bigdata/08_airflow.png` | DAG `panaderia_chapala_bigdata` en verde (si se usa Airflow) | Airflow UI |
| EX-01 | `experimento/sqlserver_resultados.csv` | Tiempos de SQL Server | `06_experimento_sqlserver.sql` |
| EX-02 | `experimento/spark_resultados.csv` | Tiempos de Spark | Etapa `experimento` |
| EX-03 | `experimento/tiempos_por_consulta.png` | Gráfico comparativo | `analizar_resultados.py` |
