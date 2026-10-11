"""Orquestador del pipeline Big Data de la Panadería Chapala.

Uso:
  python bigdata/run_pipeline.py                       # todas las etapas
  python bigdata/run_pipeline.py --etapas ingesta,transformacion
  python bigdata/run_pipeline.py --etapas experimento --factores 1,10,50,100
  python bigdata/run_pipeline.py --modo jdbc           # ingesta directa desde SQL Server

Etapas, en orden: ingesta -> transformacion -> calidad -> consultas -> experimento
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import calidad          # noqa: E402
import consultas        # noqa: E402
import experimento      # noqa: E402
import ingesta          # noqa: E402
import transformacion   # noqa: E402
from comun import Metricas, cargar_config, crear_logger, crear_spark  # noqa: E402

ETAPAS = ["ingesta", "transformacion", "calidad", "consultas", "experimento"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--etapas", default="all", help="lista separada por comas o 'all'")
    ap.add_argument("--config", default=None, help="ruta a pipeline.json")
    ap.add_argument("--modo", choices=["csv", "jdbc"], default=None, help="origen de la ingesta")
    ap.add_argument("--factores", default=None, help="factores de escala del experimento, ej. 1,10,50")
    ap.add_argument("--repeticiones", type=int, default=None)
    args = ap.parse_args()

    etapas = ETAPAS if args.etapas == "all" else [e.strip() for e in args.etapas.split(",")]
    desconocidas = set(etapas) - set(ETAPAS)
    if desconocidas:
        ap.error(f"etapas desconocidas: {', '.join(sorted(desconocidas))}")

    cfg = cargar_config(args.config)
    logger = crear_logger(cfg)
    modo = args.modo or cfg["ingesta"]["modo"]
    spark = crear_spark(cfg, con_jdbc=("ingesta" in etapas and modo == "jdbc"))
    metricas = Metricas(cfg, logger)
    logger.info("Spark %s | master=%s | UI: %s", spark.version, spark.sparkContext.master,
                spark.sparkContext.uiWebUrl)
    logger.info("Ejecución %s | etapas: %s", metricas.ejecucion_id, ", ".join(etapas))

    t0 = time.perf_counter()
    try:
        for etapa in ETAPAS:
            if etapa not in etapas:
                continue
            logger.info("=" * 70)
            logger.info("ETAPA: %s", etapa.upper())
            if etapa == "ingesta":
                ingesta.ejecutar(spark, cfg, logger, metricas, modo=modo)
            elif etapa == "transformacion":
                transformacion.ejecutar(spark, cfg, logger, metricas)
            elif etapa == "calidad":
                calidad.ejecutar(spark, cfg, logger, metricas)
            elif etapa == "consultas":
                consultas.ejecutar(spark, cfg, logger, metricas)
            elif etapa == "experimento":
                factores = [int(x) for x in args.factores.split(",")] if args.factores else None
                experimento.ejecutar(spark, cfg, logger, metricas, factores, args.repeticiones)
        logger.info("Pipeline terminado en %.1f s", time.perf_counter() - t0)
        return 0
    except Exception:
        logger.exception("El pipeline falló")
        return 1
    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
