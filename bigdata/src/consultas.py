"""Etapa 5 - Consultas analíticas con Spark SQL sobre la capa oro.

Q1..Q5 son las consultas del experimento: mismo significado que en
bi/sql/06_experimento_sqlserver.sql. {hechos} se reemplaza por la tabla a consultar
(fact_ventas en el análisis normal, fact_ventas_exp en el experimento).
"""
import csv
from pathlib import Path

from comun import ruta
from transformacion import registrar_vistas_oro

CONSULTAS_EXPERIMENTO = {
    "Q1": """
        SELECT d.anio, d.mes_num, SUM(f.importe) AS ventas, COUNT(DISTINCT f.venta_id) AS tickets
        FROM {hechos} f JOIN dim_fecha d ON d.fecha_key = f.fecha_key
        WHERE f.estado = 'pagada'
        GROUP BY d.anio, d.mes_num
        ORDER BY d.anio, d.mes_num""",
    "Q2": """
        SELECT p.articulo, SUM(f.cantidad) AS unidades, SUM(f.importe) AS ventas
        FROM {hechos} f JOIN dim_producto p ON p.producto_key = f.producto_key
        WHERE f.estado = 'pagada'
        GROUP BY p.articulo
        ORDER BY ventas DESC
        LIMIT 10""",
    "Q3": """
        SELECT m.metodo_pago, d.dia_semana_num, COUNT(*) AS lineas, SUM(f.importe) AS ventas
        FROM {hechos} f
        JOIN dim_metodo_pago m ON m.metodo_pago_key = f.metodo_pago_key
        JOIN dim_fecha d ON d.fecha_key = f.fecha_key
        WHERE f.estado = 'pagada'
        GROUP BY m.metodo_pago, d.dia_semana_num
        ORDER BY m.metodo_pago, d.dia_semana_num""",
    "Q4": """
        WITH t AS (
            SELECT f.venta_id, c.tipo_cliente, SUM(f.importe) AS total
            FROM {hechos} f JOIN dim_cliente c ON c.cliente_key = f.cliente_key
            WHERE f.estado = 'pagada'
            GROUP BY f.venta_id, c.tipo_cliente)
        SELECT tipo_cliente, COUNT(*) AS tickets, ROUND(AVG(total), 2) AS ticket_promedio
        FROM t GROUP BY tipo_cliente
        ORDER BY tickets DESC""",
    "Q5": """
        WITH h AS (
            SELECT d.mes_num, f.hora, SUM(f.importe) AS ventas
            FROM {hechos} f JOIN dim_fecha d ON d.fecha_key = f.fecha_key
            WHERE f.estado = 'pagada'
            GROUP BY d.mes_num, f.hora)
        SELECT mes_num, hora, ventas, puesto
        FROM (SELECT *, RANK() OVER (PARTITION BY mes_num ORDER BY ventas DESC) AS puesto FROM h) x
        WHERE puesto <= 3
        ORDER BY mes_num, puesto""",
}

CONSULTAS_NEGOCIO = {
    "resumen_ventas": """
        SELECT COUNT(DISTINCT venta_id) AS tickets, SUM(importe) AS ventas,
               ROUND(SUM(importe) / COUNT(DISTINCT venta_id), 2) AS ticket_promedio,
               SUM(cantidad) AS unidades
        FROM fact_ventas WHERE estado = 'pagada'""",
    "merma_por_producto": """
        SELECT p.articulo, COUNT(*) AS ordenes, SUM(f.cantidad_programada) AS programado,
               SUM(f.merma_cantidad) AS merma,
               ROUND(100 * SUM(f.merma_cantidad) / SUM(f.cantidad_programada), 2) AS pct_merma
        FROM fact_produccion f JOIN dim_producto p ON p.producto_key = f.producto_key
        WHERE f.estado = 'finalizada'
        GROUP BY p.articulo ORDER BY pct_merma DESC""",
    "compras_por_proveedor": """
        SELECT pr.proveedor, COUNT(DISTINCT f.compra_id) AS compras, SUM(f.total) AS total
        FROM fact_compras f JOIN dim_proveedor pr ON pr.proveedor_key = f.proveedor_key
        WHERE f.estado <> 'anulada'
        GROUP BY pr.proveedor ORDER BY total DESC""",
    "stock_critico": """
        SELECT articulo, tipo, stock, stock_minimo, estado_stock
        FROM dim_producto WHERE estado_stock <> 'OK' ORDER BY stock""",
    "particiones_fact_ventas": """
        SELECT anio, mes, COUNT(*) AS filas FROM fact_ventas GROUP BY anio, mes ORDER BY anio, mes""",
}


def guardar_csv(df, destino):
    """Guarda un resultado pequeño como un único CSV legible (sin carpetas part-0000)."""
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    filas = df.collect()
    with open(destino, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(df.columns)
        for r in filas:
            w.writerow(list(r))
    return len(filas)


def ejecutar(spark, cfg, logger, metricas):
    registrar_vistas_oro(spark, cfg)
    todas = {**{k: v.format(hechos="fact_ventas") for k, v in CONSULTAS_EXPERIMENTO.items()},
             **CONSULTAS_NEGOCIO}
    for nombre, sql in todas.items():
        with metricas.etapa("consulta", consulta=nombre) as m:
            df = spark.sql(sql)
            m["filas"] = guardar_csv(df, ruta(cfg, "salidas", f"{nombre}.csv"))
        muestra = "\n".join("   " + str(tuple(r)) for r in df.limit(12).collect())
        logger.info("Resultado %s (primeras filas):\n%s", nombre, muestra)
