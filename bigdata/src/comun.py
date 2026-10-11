"""Utilidades comunes del pipeline Big Data: configuración, sesión Spark, logging y métricas."""
import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]          # raíz del repositorio
CONFIG_POR_DEFECTO = RAIZ / "bigdata" / "config" / "pipeline.json"


def cargar_config(ruta=None):
    with open(ruta or CONFIG_POR_DEFECTO, encoding="utf-8") as f:
        cfg = json.load(f)
    # rutas relativas -> absolutas desde la raíz del repo
    cfg["rutas"] = {k: str((RAIZ / v).resolve()) for k, v in cfg["rutas"].items()}
    return cfg


def ruta(cfg, clave, *partes):
    return str(Path(cfg["rutas"][clave], *partes))


def crear_logger(cfg, nombre="pipeline"):
    Path(cfg["rutas"]["logs"]).mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(nombre)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    archivo = Path(cfg["rutas"]["logs"]) / f"{nombre}_{datetime.now():%Y%m%d_%H%M%S}.log"
    for h in (logging.StreamHandler(), logging.FileHandler(archivo, encoding="utf-8")):
        h.setFormatter(fmt)
        logger.addHandler(h)
    logger.info("Log en %s", archivo)
    return logger


def crear_spark(cfg, con_jdbc=False):
    from pyspark.sql import SparkSession

    sc = cfg["spark"]
    builder = SparkSession.builder.appName(sc["app_name"]).master(sc["master"])
    for k, v in sc["config"].items():
        if k == "spark.eventLog.dir":
            destino = (RAIZ / v).resolve()
            destino.mkdir(parents=True, exist_ok=True)
            v = destino.as_uri()
        builder = builder.config(k, v)
    if con_jdbc:
        builder = builder.config("spark.jars.packages", cfg["ingesta"]["jdbc"]["paquete_maven"])
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark


class Metricas:
    """Registra duración y filas de cada etapa en logs/metricas.jsonl (una línea JSON por evento)."""

    def __init__(self, cfg, logger, ejecucion_id=None):
        self.archivo = Path(cfg["rutas"]["logs"]) / "metricas.jsonl"
        self.logger = logger
        self.ejecucion_id = ejecucion_id or datetime.now().strftime("%Y%m%d_%H%M%S")

    @contextmanager
    def etapa(self, etapa, **extra):
        datos = {"ejecucion_id": self.ejecucion_id, "etapa": etapa, **extra}
        t0 = time.perf_counter()
        estado = "OK"
        try:
            yield datos
        except Exception as e:  # se registra y se vuelve a lanzar
            estado = "ERROR"
            datos["error"] = str(e)[:500]
            raise
        finally:
            datos["segundos"] = round(time.perf_counter() - t0, 3)
            datos["estado"] = estado
            datos["fecha_hora"] = datetime.now().isoformat(timespec="seconds")
            with open(self.archivo, "a", encoding="utf-8") as f:
                f.write(json.dumps(datos, ensure_ascii=False) + "\n")
            self.logger.info("%-28s %-6s %8.2f s  %s", etapa, estado, datos["segundos"],
                             {k: v for k, v in extra.items()} | ({"filas": datos["filas"]} if "filas" in datos else {}))


def env_password(cfg):
    var = cfg["ingesta"]["jdbc"]["password_env"]
    pwd = os.environ.get(var)
    if not pwd:
        raise RuntimeError(f"Defina la variable de entorno {var} con la contraseña de SQL Server")
    return pwd
