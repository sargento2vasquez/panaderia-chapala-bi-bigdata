"""Etapas 2 y 3 - Transformación.

  bronce -> plata : tipos de datos, limpieza de textos, nulos y duplicados.
  plata  -> oro   : modelo estrella (mismas dimensiones y hechos que el DW de SQL Server),
                    con los hechos particionados por año/mes en Parquet.
"""
from pyspark.sql import functions as F
from pyspark.sql import Window

from comun import ruta

# Esquema de la capa plata: columna -> tipo Spark SQL
ESQUEMA_PLATA = {
    "ventas": {"id": "int", "cliente_id": "int", "fecha": "timestamp", "total": "decimal(12,2)",
               "metodo_pago_id": "int", "estado": "string", "tipo_comprobante": "string",
               "numero_comprobante": "string"},
    "items_venta": {"id": "int", "venta_id": "int", "variante_id": "int", "cantidad": "decimal(12,3)",
                    "precio_unitario": "decimal(12,2)", "descuento": "decimal(12,2)"},
    "variantes_producto": {"id": "int", "producto_id": "int", "sku": "string", "nombre": "string",
                           "precio_venta": "decimal(12,2)", "stock": "decimal(12,3)",
                           "stock_minimo": "decimal(12,3)", "activo": "int"},
    "productos": {"id": "int", "nombre": "string", "tipo": "string", "categoria_id": "int",
                  "unidad_id": "int", "activo": "int"},
    "categorias": {"id": "int", "nombre": "string"},
    "unidades": {"id": "int", "nombre": "string"},
    "clientes": {"id": "int", "nombre": "string", "documento": "string"},
    "metodos_pago": {"id": "int", "nombre": "string"},
    "proveedores": {"id": "int", "nombre": "string", "documento": "string"},
    "compras": {"id": "int", "proveedor_id": "int", "numero_comprobante": "string", "fecha": "timestamp",
                "total": "decimal(12,2)", "estado": "string"},
    "items_compra": {"id": "int", "compra_id": "int", "variante_id": "int", "cantidad": "decimal(12,3)",
                     "costo_unitario": "decimal(12,2)", "total": "decimal(12,2)"},
    "producciones": {"id": "int", "referencia": "string", "variante_salida_id": "int",
                     "cantidad_programada": "decimal(12,3)", "cantidad_obtenida": "decimal(12,3)",
                     "merma_cantidad": "decimal(12,3)", "merma_motivo": "string", "fecha": "timestamp",
                     "estado": "string"},
    "consumo_insumos": {"id": "int", "produccion_id": "int", "variante_id": "int",
                        "cantidad": "decimal(12,3)", "fecha": "timestamp"},
}

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]
DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


# ------------------------------------------------------------------ PLATA
def a_plata(spark, cfg, logger, metricas):
    logger.info("PLATA: tipado y limpieza -> %s", cfg["rutas"]["silver"])
    for tabla, esquema in ESQUEMA_PLATA.items():
        with metricas.etapa("plata", tabla=tabla) as m:
            df = spark.read.parquet(ruta(cfg, "bronze", tabla))
            cols = []
            for c, t in esquema.items():
                col = F.col(c).cast("string")
                if t == "string":
                    col = F.when(F.trim(col) == "", None).otherwise(F.trim(col))
                else:
                    col = F.trim(col).cast(t)
                cols.append(col.alias(c))
            limpio = df.select(*cols).dropDuplicates(["id"]).filter(F.col("id").isNotNull())
            limpio.write.mode("overwrite").parquet(ruta(cfg, "silver", tabla))
            m["filas"] = spark.read.parquet(ruta(cfg, "silver", tabla)).count()


def _plata(spark, cfg, tabla):
    return spark.read.parquet(ruta(cfg, "silver", tabla))


def _escribir(df, cfg, nombre, metricas):
    part = cfg["particionamiento"].get(nombre)
    destino = ruta(cfg, "gold", nombre)
    with metricas.etapa("oro", tabla=nombre, particiones=",".join(part or [])) as m:
        if part:
            # repartir por la clave de partición evita muchos archivos pequeños por carpeta
            df.repartition(*part).write.mode("overwrite").partitionBy(*part).parquet(destino)
        else:
            df.coalesce(1).write.mode("overwrite").parquet(destino)
        m["filas"] = df.sparkSession.read.parquet(destino).count()


def _fecha_key(col):
    return F.date_format(col, "yyyyMMdd").cast("int")


# ------------------------------------------------------------------ ORO (modelo estrella)
def a_oro(spark, cfg, logger, metricas):
    logger.info("ORO: modelo estrella -> %s", cfg["rutas"]["gold"])
    ventas, items = _plata(spark, cfg, "ventas"), _plata(spark, cfg, "items_venta")
    variantes, productos = _plata(spark, cfg, "variantes_producto"), _plata(spark, cfg, "productos")
    categorias, unidades = _plata(spark, cfg, "categorias"), _plata(spark, cfg, "unidades")
    clientes, metodos = _plata(spark, cfg, "clientes"), _plata(spark, cfg, "metodos_pago")
    proveedores, compras = _plata(spark, cfg, "proveedores"), _plata(spark, cfg, "compras")
    items_compra, producciones = _plata(spark, cfg, "items_compra"), _plata(spark, cfg, "producciones")
    consumo = _plata(spark, cfg, "consumo_insumos")

    # ---- dim_fecha: años completos que cubren todas las fechas de los hechos
    fechas = (ventas.select(F.to_date("fecha").alias("f"))
              .union(producciones.select(F.to_date("fecha")))
              .union(compras.select(F.to_date("fecha")))
              .union(consumo.select(F.to_date("fecha"))))
    lim = fechas.agg(F.min("f").alias("lo"), F.max("f").alias("hi")).first()
    rango = spark.sql(
        f"SELECT explode(sequence(to_date('{lim.lo.year}-01-01'), to_date('{lim.hi.year}-12-31'), "
        f"interval 1 day)) AS fecha")
    dsn = ((F.dayofweek("fecha") + 5) % 7) + 1                       # 1 = lunes ... 7 = domingo
    dim_fecha = rango.select(
        _fecha_key(F.col("fecha")).alias("fecha_key"), "fecha",
        F.year("fecha").alias("anio"), F.quarter("fecha").alias("trimestre"),
        F.month("fecha").alias("mes_num"),
        F.element_at(F.array(*[F.lit(m) for m in MESES]), F.month("fecha")).alias("mes"),
        F.dayofmonth("fecha").alias("dia"),
        dsn.alias("dia_semana_num"),
        F.element_at(F.array(*[F.lit(d) for d in DIAS]), dsn).alias("dia_semana"),
        (dsn >= 6).alias("es_fin_semana"))

    # ---- dim_producto (nivel variante)
    dim_producto = (variantes.alias("v")
        .join(productos.alias("p"), F.col("p.id") == F.col("v.producto_id"))
        .join(categorias.alias("c"), F.col("c.id") == F.col("p.categoria_id"), "left")
        .join(unidades.alias("u"), F.col("u.id") == F.col("p.unidad_id"), "left")
        .select(
            F.col("v.id").alias("variante_id"), F.col("v.sku").alias("sku"),
            F.col("p.nombre").alias("producto"), F.col("v.nombre").alias("variante"),
            F.when(F.col("v.nombre").isNull(), F.col("p.nombre"))
             .otherwise(F.concat_ws(" - ", F.col("p.nombre"), F.col("v.nombre"))).alias("articulo"),
            F.col("p.tipo").alias("tipo"),
            F.coalesce(F.col("c.nombre"), F.lit("Sin categoría")).alias("categoria"),
            F.coalesce(F.col("u.nombre"), F.lit("Sin unidad")).alias("unidad"),
            F.col("v.precio_venta").alias("precio_venta"), F.col("v.stock").alias("stock"),
            F.col("v.stock_minimo").alias("stock_minimo"),
            F.when(F.col("v.stock") < 0, "Negativo")
             .when(F.col("v.stock") < F.col("v.stock_minimo"), "Bajo mínimo")
             .otherwise("OK").alias("estado_stock"),
            (F.coalesce(F.col("v.activo"), F.lit(0)) == 1).alias("activo"))
        .withColumn("producto_key", F.row_number().over(Window.orderBy("variante_id"))))

    # ---- dim_cliente (+ 0 = consumidor final)
    final = spark.createDataFrame([(0, "Consumidor final", None)], "id int, nombre string, documento string")
    dim_cliente = (final.unionByName(clientes.select("id", "nombre", "documento"))
        .select(F.col("id").alias("cliente_id"), "nombre", "documento",
                F.when(F.col("id") == 0, "Consumidor final")
                 .when(F.col("documento").startswith("20") & (F.length("documento") == 11), "Empresa")
                 .when(F.col("documento").isNotNull(), "Persona")
                 .otherwise("Sin documento").alias("tipo_cliente"))
        .withColumn("cliente_key", F.row_number().over(Window.orderBy("cliente_id"))))

    # ---- dim_metodo_pago (+ 0 = sin especificar) y dim_proveedor
    sin = spark.createDataFrame([(0, "Sin especificar")], "id int, nombre string")
    dim_metodo_pago = (sin.unionByName(metodos.select("id", "nombre"))
        .select(F.col("id").alias("metodo_pago_id"), F.col("nombre").alias("metodo_pago"))
        .withColumn("metodo_pago_key", F.row_number().over(Window.orderBy("metodo_pago_id"))))
    dim_proveedor = (proveedores
        .select(F.col("id").alias("proveedor_id"), F.col("nombre").alias("proveedor"), "documento")
        .withColumn("proveedor_key", F.row_number().over(Window.orderBy("proveedor_id"))))

    # Las dimensiones son pequeñas: Spark las difunde (broadcast) a todos los ejecutores en los joins
    dp = F.broadcast(dim_producto.select("variante_id", "producto_key"))
    dc = F.broadcast(dim_cliente.select("cliente_id", "cliente_key"))
    dm = F.broadcast(dim_metodo_pago.select("metodo_pago_id", "metodo_pago_key"))
    dpr = F.broadcast(dim_proveedor.select("proveedor_id", "proveedor_key"))

    # ---- fact_ventas (grano: línea de venta)
    v = ventas.filter(F.col("fecha").isNotNull()).select(
        F.col("id").alias("venta_id"), "fecha", "estado", "tipo_comprobante",
        F.coalesce("cliente_id", F.lit(0)).alias("cliente_id"),
        F.coalesce("metodo_pago_id", F.lit(0)).alias("metodo_pago_id"))
    fact_ventas = (items.select(F.col("id").alias("item_venta_id"), "venta_id", "variante_id",
                                F.coalesce("cantidad", F.lit(0)).alias("cantidad"),
                                F.coalesce("precio_unitario", F.lit(0)).alias("precio_unitario"),
                                F.coalesce("descuento", F.lit(0)).alias("descuento"))
        .join(v, "venta_id").join(dp, "variante_id").join(dc, "cliente_id").join(dm, "metodo_pago_id")
        .select("item_venta_id", "venta_id",
                _fecha_key(F.col("fecha")).alias("fecha_key"),
                F.hour("fecha").alias("hora"),
                "producto_key", "cliente_key", "metodo_pago_key", "tipo_comprobante",
                F.coalesce("estado", F.lit("pendiente")).alias("estado"),
                "cantidad", "precio_unitario", "descuento",
                F.round(F.col("cantidad") * F.col("precio_unitario") - F.col("descuento"), 2)
                 .cast("decimal(14,2)").alias("importe"),
                F.year("fecha").alias("anio"), F.month("fecha").alias("mes")))

    # ---- fact_produccion (grano: orden de producción)
    fact_produccion = (producciones.filter(F.col("fecha").isNotNull())
        .withColumnRenamed("variante_salida_id", "variante_id").join(dp, "variante_id")
        .select(F.col("id").alias("produccion_id"), "referencia",
                _fecha_key(F.col("fecha")).alias("fecha_key"), "producto_key",
                F.coalesce("cantidad_programada", F.lit(0)).alias("cantidad_programada"),
                F.coalesce("cantidad_obtenida", F.lit(0)).alias("cantidad_obtenida"),
                F.coalesce("merma_cantidad", F.lit(0)).alias("merma_cantidad"),
                F.coalesce("merma_motivo", F.lit("Sin motivo")).alias("motivo_merma"),
                F.coalesce("estado", F.lit("pendiente")).alias("estado"),
                F.year("fecha").alias("anio"), F.month("fecha").alias("mes")))

    # ---- fact_compras (grano: línea de compra)
    c = compras.filter(F.col("fecha").isNotNull()).select(
        F.col("id").alias("compra_id"), "proveedor_id", "numero_comprobante", "fecha",
        F.coalesce("estado", F.lit("pendiente")).alias("estado"))
    fact_compras = (items_compra.select(F.col("id").alias("item_compra_id"), "compra_id", "variante_id",
                                        F.coalesce("cantidad", F.lit(0)).alias("cantidad"),
                                        F.coalesce("costo_unitario", F.lit(0)).alias("costo_unitario"),
                                        F.coalesce("total", F.lit(0)).alias("total"))
        .join(c, "compra_id").join(dpr, "proveedor_id").join(dp, "variante_id")
        .select("item_compra_id", "compra_id", "numero_comprobante",
                _fecha_key(F.col("fecha")).alias("fecha_key"), "proveedor_key", "producto_key", "estado",
                "cantidad", "costo_unitario", "total", F.year("fecha").alias("anio")))

    # ---- fact_consumo_insumos
    fact_consumo = (consumo.filter(F.col("fecha").isNotNull()).join(dp, "variante_id")
        .select(F.col("id").alias("consumo_id"), "produccion_id",
                _fecha_key(F.col("fecha")).alias("fecha_key"), "producto_key", "cantidad",
                F.year("fecha").alias("anio"), F.month("fecha").alias("mes")))

    for nombre, df in [("dim_fecha", dim_fecha), ("dim_producto", dim_producto), ("dim_cliente", dim_cliente),
                       ("dim_metodo_pago", dim_metodo_pago), ("dim_proveedor", dim_proveedor),
                       ("fact_ventas", fact_ventas), ("fact_produccion", fact_produccion),
                       ("fact_compras", fact_compras), ("fact_consumo_insumos", fact_consumo)]:
        _escribir(df, cfg, nombre, metricas)


TABLAS_ORO = ["dim_fecha", "dim_producto", "dim_cliente", "dim_metodo_pago", "dim_proveedor",
              "fact_ventas", "fact_produccion", "fact_compras", "fact_consumo_insumos"]


def registrar_vistas_oro(spark, cfg):
    """Registra las tablas de oro como vistas temporales para Spark SQL."""
    for t in TABLAS_ORO:
        spark.read.parquet(ruta(cfg, "gold", t)).createOrReplaceTempView(t)


def ejecutar(spark, cfg, logger, metricas):
    a_plata(spark, cfg, logger, metricas)
    a_oro(spark, cfg, logger, metricas)
