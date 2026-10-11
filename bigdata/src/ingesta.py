"""Etapa 1 - Ingesta: fuente (CSV exportado de SQL Server o JDBC directo) -> capa bronce (Parquet).

La capa bronce guarda los datos tal como llegan, más columnas de auditoría:
  _fecha_ingesta  (timestamp de la carga)
  _origen         (archivo CSV o tabla JDBC)
"""
from pyspark.sql import functions as F

from comun import env_password, ruta


def leer_csv(spark, cfg, tabla):
    archivo = ruta(cfg, "raw", f"{tabla}.csv")
    df = (spark.read
          .option("header", True)
          .option("multiLine", True)      # observaciones con saltos de línea
          .option("quote", '"')
          .option("escape", '"')
          .option("encoding", "UTF-8")
          .option("inferSchema", False)   # en bronce todo llega como texto; los tipos se fijan en plata
          .csv(archivo))
    return df, archivo


def leer_jdbc(spark, cfg, tabla):
    j = cfg["ingesta"]["jdbc"]
    df = (spark.read.format("jdbc")
          .option("url", j["url"])
          .option("dbtable", f"dbo.{tabla}")
          .option("user", j["usuario"])
          .option("password", env_password(cfg))
          .option("driver", j["driver"])
          .option("fetchsize", 10000)
          .load())
    return df, f"jdbc:dbo.{tabla}"


def ejecutar(spark, cfg, logger, metricas, modo=None):
    modo = modo or cfg["ingesta"]["modo"]
    logger.info("INGESTA (modo=%s) -> %s", modo, cfg["rutas"]["bronze"])
    resumen = {}
    for tabla in cfg["ingesta"]["tablas"]:
        with metricas.etapa("ingesta", tabla=tabla, modo=modo) as m:
            df, origen = (leer_jdbc if modo == "jdbc" else leer_csv)(spark, cfg, tabla)
            df = (df.withColumn("_fecha_ingesta", F.current_timestamp())
                    .withColumn("_origen", F.lit(origen)))
            df.write.mode("overwrite").parquet(ruta(cfg, "bronze", tabla))
            m["filas"] = spark.read.parquet(ruta(cfg, "bronze", tabla)).count()
            resumen[tabla] = m["filas"]
    return resumen
