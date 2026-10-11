"""Etapa 4 - Controles de calidad de datos (monitoreo).

Cada control devuelve un valor y un nivel:
  CRITICO -> detiene el pipeline (código de salida 1)
  AVISO   -> se registra, el pipeline continúa (problemas de origen ya conocidos)
El reporte queda en logs/calidad_<fecha>.json.
"""
import json
from datetime import datetime
from pathlib import Path

from pyspark.sql import functions as F

from comun import ruta


def _plata(spark, cfg, t):
    return spark.read.parquet(ruta(cfg, "silver", t))


def _oro(spark, cfg, t):
    return spark.read.parquet(ruta(cfg, "gold", t))


def ejecutar(spark, cfg, logger, metricas):
    ventas, items = _plata(spark, cfg, "ventas"), _plata(spark, cfg, "items_venta")
    variantes = _plata(spark, cfg, "variantes_producto")
    fv = _oro(spark, cfg, "fact_ventas")

    lineas = items.groupBy("venta_id").agg(F.round(F.sum(F.col("cantidad") * F.col("precio_unitario")
                                                         - F.col("descuento")), 2).alias("suma"))
    controles = [
        # (nombre, valor, condición de éxito, nivel si falla)
        ("filas_items_bronce_vs_plata", items.count(),
         lambda v: v == spark.read.parquet(ruta(cfg, "bronze", "items_venta")).count(), "CRITICO"),
        ("lineas_sin_venta", items.join(ventas, items.venta_id == ventas.id, "left_anti").count(),
         lambda v: v == 0, "CRITICO"),
        ("fact_ventas_vs_items", fv.count(), lambda v: v == items.count(), "CRITICO"),
        ("ventas_fecha_nula", ventas.filter(F.col("fecha").isNull()).count(), lambda v: v == 0, "CRITICO"),
        ("importe_negativo", fv.filter(F.col("importe") < 0).count(), lambda v: v == 0, "AVISO"),
        ("ventas_total_distinto_lineas",
         ventas.join(lineas, ventas.id == lineas.venta_id, "left")
               .filter(F.abs(ventas.total - F.coalesce(lineas.suma, F.lit(0))) > 0.01).count(),
         lambda v: v == 0, "AVISO"),
        ("variantes_stock_negativo", variantes.filter(F.col("stock") < 0).count(), lambda v: v == 0, "AVISO"),
        ("comprobantes_duplicados",
         ventas.filter(F.col("numero_comprobante").isNotNull())
               .groupBy("numero_comprobante").count().filter(F.col("count") > 1).count(),
         lambda v: v == 0, "AVISO"),
        ("ventas_sin_comprobante", ventas.filter(F.col("numero_comprobante").isNull()).count(),
         lambda v: v == 0, "AVISO"),
    ]

    reporte, criticos = [], 0
    with metricas.etapa("calidad") as m:
        for nombre, valor, ok, nivel in controles:
            paso = bool(ok(valor))
            estado = "OK" if paso else nivel
            criticos += (estado == "CRITICO")
            reporte.append({"control": nombre, "valor": int(valor), "estado": estado})
            logger.info("  [%-7s] %-32s %s", estado, nombre, valor)
        m["controles"] = len(reporte)
        m["criticos"] = criticos

    destino = Path(cfg["rutas"]["logs"]) / f"calidad_{datetime.now():%Y%m%d_%H%M%S}.json"
    destino.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Reporte de calidad: %s", destino)
    if criticos:
        raise RuntimeError(f"{criticos} control(es) crítico(s) fallaron; ver {destino}")
    return reporte
