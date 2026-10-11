/* ==========================================================================
   03_dw_etl.sql  -  Procedimientos ETL: OLTP (dbo) -> data warehouse (dw)
   Ejecución completa:   EXEC dw.sp_etl_completo;
   Estrategia:
     - Dimensiones: MERGE por clave de negocio (SCD tipo 1: se sobrescribe).
     - Hechos: recarga completa (DELETE + INSERT) dentro de una transacción.
     - Cada paso registra filas, duración y errores en dw.etl_log.
   Requiere SQL Server 2016 SP1+ (CREATE OR ALTER).
   ========================================================================== */
USE panaderia_db;
GO

/* ---------------------------------------------------------------- utilidades */
CREATE OR ALTER PROCEDURE dw.sp_log
    @proceso NVARCHAR(100), @inicio DATETIME2(3), @filas INT, @estado NVARCHAR(20), @mensaje NVARCHAR(4000) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dw.etl_log (proceso, inicio, fin, filas, estado, mensaje)
    VALUES (@proceso, @inicio, SYSDATETIME(), @filas, @estado, @mensaje);
END;
GO

/* ---------------------------------------------------------------- dim_fecha */
CREATE OR ALTER PROCEDURE dw.sp_cargar_dim_fecha
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @ini DATETIME2(3) = SYSDATETIME(), @desde DATE, @hasta DATE;

    -- Rango: años completos que cubren todas las fechas de los hechos
    SELECT @desde = MIN(f), @hasta = MAX(f)
    FROM (SELECT CAST(fecha AS DATE) f FROM dbo.ventas
          UNION ALL SELECT CAST(fecha AS DATE) FROM dbo.producciones
          UNION ALL SELECT CAST(fecha AS DATE) FROM dbo.compras
          UNION ALL SELECT CAST(fecha AS DATE) FROM dbo.consumo_insumos) x;
    SET @desde = DATEFROMPARTS(YEAR(@desde), 1, 1);
    SET @hasta = DATEFROMPARTS(YEAR(@hasta), 12, 31);

    ;WITH n AS (
        SELECT TOP (DATEDIFF(DAY, @desde, @hasta) + 1)
               ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS i
        FROM sys.all_objects a CROSS JOIN sys.all_objects b
    ), d AS (
        SELECT DATEADD(DAY, i, @desde) AS fecha FROM n
    ), src AS (
        SELECT CONVERT(INT, CONVERT(CHAR(8), fecha, 112)) AS fecha_key,
               fecha,
               YEAR(fecha) AS anio,
               DATEPART(QUARTER, fecha) AS trimestre,
               MONTH(fecha) AS mes_num,
               CHOOSE(MONTH(fecha), N'Ene', N'Feb', N'Mar', N'Abr', N'May', N'Jun',
                                    N'Jul', N'Ago', N'Set', N'Oct', N'Nov', N'Dic') AS mes,
               DAY(fecha) AS dia,
               -- 1 = lunes ... 7 = domingo, independiente de SET DATEFIRST
               (DATEDIFF(DAY, '19000101', fecha) % 7) + 1 AS dia_semana_num
        FROM d
    )
    MERGE dw.dim_fecha AS t
    USING (SELECT *, CHOOSE(dia_semana_num, N'Lun', N'Mar', N'Mié', N'Jue', N'Vie', N'Sáb', N'Dom') AS dia_semana,
                  CAST(IIF(dia_semana_num >= 6, 1, 0) AS BIT) AS es_fin_semana
           FROM src) AS s
    ON t.fecha_key = s.fecha_key
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (fecha_key, fecha, anio, trimestre, mes_num, mes, dia, dia_semana_num, dia_semana, es_fin_semana)
        VALUES (s.fecha_key, s.fecha, s.anio, s.trimestre, s.mes_num, s.mes, s.dia, s.dia_semana_num, s.dia_semana, s.es_fin_semana);

    DECLARE @n INT = (SELECT COUNT(*) FROM dw.dim_fecha);
    EXEC dw.sp_log N'dim_fecha', @ini, @n, N'OK';
END;
GO

/* ---------------------------------------------------------------- dimensiones */
CREATE OR ALTER PROCEDURE dw.sp_cargar_dimensiones
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @ini DATETIME2(3), @n INT;

    -- dim_producto (nivel variante)
    SET @ini = SYSDATETIME();
    MERGE dw.dim_producto AS t
    USING (
        SELECT v.id AS variante_id, v.sku, p.nombre AS producto, v.nombre AS variante,
               CASE WHEN NULLIF(LTRIM(RTRIM(v.nombre)), N'') IS NULL THEN p.nombre
                    ELSE p.nombre + N' - ' + v.nombre END AS articulo,
               p.tipo,
               ISNULL(c.nombre, N'Sin categoría') AS categoria,
               ISNULL(u.nombre, N'Sin unidad')    AS unidad,
               v.precio_venta, v.stock, v.stock_minimo,
               CASE WHEN v.stock < 0 THEN N'Negativo'
                    WHEN v.stock < v.stock_minimo THEN N'Bajo mínimo'
                    ELSE N'OK' END AS estado_stock,
               CAST(ISNULL(v.activo, 0) AS BIT) AS activo
        FROM dbo.variantes_producto v
        JOIN dbo.productos p       ON p.id = v.producto_id
        LEFT JOIN dbo.categorias c ON c.id = p.categoria_id
        LEFT JOIN dbo.unidades u   ON u.id = p.unidad_id
    ) AS s
    ON t.variante_id = s.variante_id
    WHEN MATCHED THEN UPDATE SET
        sku = s.sku, producto = s.producto, variante = s.variante, articulo = s.articulo, tipo = s.tipo,
        categoria = s.categoria, unidad = s.unidad, precio_venta = s.precio_venta, stock = s.stock,
        stock_minimo = s.stock_minimo, estado_stock = s.estado_stock, activo = s.activo
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (variante_id, sku, producto, variante, articulo, tipo, categoria, unidad,
                precio_venta, stock, stock_minimo, estado_stock, activo)
        VALUES (s.variante_id, s.sku, s.producto, s.variante, s.articulo, s.tipo, s.categoria, s.unidad,
                s.precio_venta, s.stock, s.stock_minimo, s.estado_stock, s.activo);
    SET @n = @@ROWCOUNT;
    EXEC dw.sp_log N'dim_producto', @ini, @n, N'OK';

    -- dim_cliente (+ miembro 0 = consumidor final para ventas sin cliente)
    SET @ini = SYSDATETIME();
    MERGE dw.dim_cliente AS t
    USING (
        SELECT 0 AS cliente_id, N'Consumidor final' AS nombre, CAST(NULL AS NVARCHAR(50)) AS documento,
               N'Consumidor final' AS tipo_cliente
        UNION ALL
        SELECT id, nombre, documento,
               CASE WHEN documento LIKE N'20%' AND LEN(documento) = 11 THEN N'Empresa'
                    WHEN documento IS NOT NULL THEN N'Persona'
                    ELSE N'Sin documento' END
        FROM dbo.clientes
    ) AS s
    ON t.cliente_id = s.cliente_id
    WHEN MATCHED THEN UPDATE SET nombre = s.nombre, documento = s.documento, tipo_cliente = s.tipo_cliente
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (cliente_id, nombre, documento, tipo_cliente) VALUES (s.cliente_id, s.nombre, s.documento, s.tipo_cliente);
    SET @n = @@ROWCOUNT;
    EXEC dw.sp_log N'dim_cliente', @ini, @n, N'OK';

    -- dim_metodo_pago (+ miembro 0 = sin especificar)
    SET @ini = SYSDATETIME();
    MERGE dw.dim_metodo_pago AS t
    USING (SELECT 0 AS metodo_pago_id, N'Sin especificar' AS metodo_pago
           UNION ALL SELECT id, nombre FROM dbo.metodos_pago) AS s
    ON t.metodo_pago_id = s.metodo_pago_id
    WHEN MATCHED THEN UPDATE SET metodo_pago = s.metodo_pago
    WHEN NOT MATCHED BY TARGET THEN INSERT (metodo_pago_id, metodo_pago) VALUES (s.metodo_pago_id, s.metodo_pago);
    SET @n = @@ROWCOUNT;
    EXEC dw.sp_log N'dim_metodo_pago', @ini, @n, N'OK';

    -- dim_proveedor
    SET @ini = SYSDATETIME();
    MERGE dw.dim_proveedor AS t
    USING (SELECT id AS proveedor_id, nombre AS proveedor, documento FROM dbo.proveedores) AS s
    ON t.proveedor_id = s.proveedor_id
    WHEN MATCHED THEN UPDATE SET proveedor = s.proveedor, documento = s.documento
    WHEN NOT MATCHED BY TARGET THEN INSERT (proveedor_id, proveedor, documento) VALUES (s.proveedor_id, s.proveedor, s.documento);
    SET @n = @@ROWCOUNT;
    EXEC dw.sp_log N'dim_proveedor', @ini, @n, N'OK';
END;
GO

/* ---------------------------------------------------------------- hechos */
CREATE OR ALTER PROCEDURE dw.sp_cargar_hechos
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @ini DATETIME2(3), @n INT, @src INT;

    -- fact_ventas: líneas de venta
    SET @ini = SYSDATETIME();
    DELETE FROM dw.fact_ventas;
    INSERT INTO dw.fact_ventas (item_venta_id, venta_id, fecha_key, hora, producto_key, cliente_key,
                                metodo_pago_key, tipo_comprobante, estado, cantidad, precio_unitario, descuento, importe)
    SELECT i.id, v.id,
           CONVERT(INT, CONVERT(CHAR(8), v.fecha, 112)),
           DATEPART(HOUR, v.fecha),
           dp.producto_key, dc.cliente_key, dm.metodo_pago_key,
           v.tipo_comprobante, ISNULL(v.estado, N'pendiente'),
           ISNULL(i.cantidad, 0), ISNULL(i.precio_unitario, 0), ISNULL(i.descuento, 0),
           ROUND(ISNULL(i.cantidad, 0) * ISNULL(i.precio_unitario, 0) - ISNULL(i.descuento, 0), 2)
    FROM dbo.items_venta i
    JOIN dbo.ventas v              ON v.id = i.venta_id
    JOIN dw.dim_producto dp        ON dp.variante_id = i.variante_id
    JOIN dw.dim_cliente dc         ON dc.cliente_id = ISNULL(v.cliente_id, 0)
    JOIN dw.dim_metodo_pago dm     ON dm.metodo_pago_id = ISNULL(v.metodo_pago_id, 0)
    WHERE v.fecha IS NOT NULL;
    SET @n = @@ROWCOUNT;
    SET @src = (SELECT COUNT(*) FROM dbo.items_venta);
    EXEC dw.sp_log N'fact_ventas', @ini, @n, N'OK', NULL;
    IF @n <> @src
        EXEC dw.sp_log N'fact_ventas_rechazos', @ini, @src, N'AVISO', N'Líneas de venta sin dimensión válida (no cargadas)';

    -- fact_produccion
    SET @ini = SYSDATETIME();
    DELETE FROM dw.fact_produccion;
    INSERT INTO dw.fact_produccion (produccion_id, referencia, fecha_key, producto_key, cantidad_programada,
                                    cantidad_obtenida, merma_cantidad, motivo_merma, estado)
    SELECT p.id, p.referencia, CONVERT(INT, CONVERT(CHAR(8), p.fecha, 112)), dp.producto_key,
           ISNULL(p.cantidad_programada, 0), ISNULL(p.cantidad_obtenida, 0), ISNULL(p.merma_cantidad, 0),
           ISNULL(p.merma_motivo, N'Sin motivo'), ISNULL(p.estado, N'pendiente')
    FROM dbo.producciones p
    JOIN dw.dim_producto dp ON dp.variante_id = p.variante_salida_id
    WHERE p.fecha IS NOT NULL;
    SET @n = @@ROWCOUNT;
    EXEC dw.sp_log N'fact_produccion', @ini, @n, N'OK';

    -- fact_compras: líneas de compra
    SET @ini = SYSDATETIME();
    DELETE FROM dw.fact_compras;
    INSERT INTO dw.fact_compras (item_compra_id, compra_id, numero_comprobante, fecha_key, proveedor_key,
                                 producto_key, estado, cantidad, costo_unitario, total)
    SELECT i.id, c.id, c.numero_comprobante, CONVERT(INT, CONVERT(CHAR(8), c.fecha, 112)),
           dpr.proveedor_key, dp.producto_key, ISNULL(c.estado, N'pendiente'),
           ISNULL(i.cantidad, 0), ISNULL(i.costo_unitario, 0), ISNULL(i.total, 0)
    FROM dbo.items_compra i
    JOIN dbo.compras c          ON c.id = i.compra_id
    JOIN dw.dim_proveedor dpr   ON dpr.proveedor_id = c.proveedor_id
    JOIN dw.dim_producto dp     ON dp.variante_id = i.variante_id
    WHERE c.fecha IS NOT NULL;
    SET @n = @@ROWCOUNT;
    EXEC dw.sp_log N'fact_compras', @ini, @n, N'OK';

    -- fact_consumo_insumos
    SET @ini = SYSDATETIME();
    DELETE FROM dw.fact_consumo_insumos;
    INSERT INTO dw.fact_consumo_insumos (consumo_id, produccion_id, fecha_key, producto_key, cantidad)
    SELECT ci.id, ci.produccion_id, CONVERT(INT, CONVERT(CHAR(8), ci.fecha, 112)), dp.producto_key, ci.cantidad
    FROM dbo.consumo_insumos ci
    JOIN dw.dim_producto dp ON dp.variante_id = ci.variante_id
    WHERE ci.fecha IS NOT NULL;
    SET @n = @@ROWCOUNT;
    EXEC dw.sp_log N'fact_consumo_insumos', @ini, @n, N'OK';
END;
GO

/* ---------------------------------------------------------------- orquestador */
CREATE OR ALTER PROCEDURE dw.sp_etl_completo
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    DECLARE @ini DATETIME2(3) = SYSDATETIME();
    BEGIN TRY
        BEGIN TRAN;
            EXEC dw.sp_cargar_dim_fecha;
            EXEC dw.sp_cargar_dimensiones;
            EXEC dw.sp_cargar_hechos;
        COMMIT;
        EXEC dw.sp_log N'ETL completo', @ini, NULL, N'OK';
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        DECLARE @msg NVARCHAR(4000) = ERROR_MESSAGE();
        EXEC dw.sp_log N'ETL completo', @ini, NULL, N'ERROR', @msg;
        THROW;
    END CATCH;
END;
GO

-- Ejecutar la carga y mostrar el resumen
EXEC dw.sp_etl_completo;
SELECT proceso, filas, estado, DATEDIFF(MILLISECOND, inicio, fin) AS ms, mensaje
FROM dw.etl_log
WHERE inicio >= DATEADD(MINUTE, -10, SYSDATETIME())
ORDER BY id;
GO
