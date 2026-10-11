"""Etapa 6 - Experimento: tiempos de consulta en Spark con volúmenes crecientes.

Para cada factor de escala (x1, x10, x50 por defecto):
  1. Replica fact_ventas N veces (cada réplica con venta_id distinto) y la escribe en
     datalake/experimento/sf=N, particionada por anio/mes.
  2. Ejecuta Q1..Q5 una vez de calentamiento y luego R veces medidas.
  3. Guarda cada medición en experimento/resultados/spark_resultados.csv
     (mismas columnas que dw.exp_resultados de SQL Server).
"""
import csv
import time
from pathlib import Path

from pyspark.sql import functions as F

from comun import ruta
from consultas import CONSULTAS_EXPERIMENTO, guardar_csv
from transformacion import registrar_vistas_oro

COLUMNAS = ["plataforma", "factor_escala", "filas_hecho", "consulta", "repeticion", "ms", "filas_result"]


def construir_hechos_escalados(spark, cfg, sf):
    base = spark.read.parquet(ruta(cfg, "gold", "fact_ventas"))
    reps = spark.range(sf).withColumnRenamed("id", "rep")
    escalado = (base.crossJoin(reps)
                .select((F.col("venta_id").cast("bigint") + F.col("rep") * 1000000).alias("venta_id"),
                        "fecha_key", "hora", "producto_key", "cliente_key", "metodo_pago_key",
                        "estado", "cantidad", "importe", "anio", "mes"))
    destino = ruta(cfg, "experimento", f"sf={sf}")
    escalado.repartition("anio", "mes").write.mode("overwrite").partitionBy("anio", "mes").parquet(destino)
    df = spark.read.parquet(destino)
    df.createOrReplaceTempView("fact_ventas_exp")
    return df.count()


def ejecutar(spark, cfg, logger, metricas, factores=None, repeticiones=None):
    registrar_vistas_oro(spark, cfg)
    factores = factores or cfg["experimento"]["factores_escala"]
    repeticiones = repeticiones or cfg["experimento"]["repeticiones"]
    salida = Path(ruta(cfg, "resultados_experimento", "spark_resultados.csv"))
    salida.parent.mkdir(parents=True, exist_ok=True)

    filas_csv = []
    for sf in factores:
        with metricas.etapa("experimento_preparar", factor_escala=sf) as m:
            n = construir_hechos_escalados(spark, cfg, sf)
            m["filas"] = n
        for qid, plantilla in CONSULTAS_EXPERIMENTO.items():
            sql = plantilla.format(hechos="fact_ventas_exp")
            for rep in range(repeticiones + 1):            # rep 0 = calentamiento
                t0 = time.perf_counter()
                res = spark.sql(sql).collect()             # fuerza la ejecución completa
                ms = int(round((time.perf_counter() - t0) * 1000))
                filas_csv.append(["spark", sf, n, qid, rep, ms, len(res)])
                logger.info("  sf=%-3s %s rep=%s  %6d ms  (%d filas)", sf, qid, rep, ms, len(res))
            if sf == 1:   # resultado de referencia para comparar con SQL Server
                guardar_csv(spark.sql(sql), ruta(cfg, "salidas", f"experimento_sf1_{qid}.csv"))

    with open(salida, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNAS)
        w.writerows(filas_csv)
    logger.info("Resultados del experimento: %s", salida)
    return salida
