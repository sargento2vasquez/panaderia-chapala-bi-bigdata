/* ==========================================================================
   05_consultas_dw.sql  -  Consultas analíticas sobre el modelo estrella (dw)
   Requisito: 02_dw_ddl.sql y 03_dw_etl.sql ejecutados.
   "Esperado:" = resultado con los datos del volcado original (ene-sep 2026).
   ========================================================================== */
USE panaderia_db;
GO

-- A. Conteo de filas del DW.
--    Esperado: dim_fecha 365, dim_producto 20, dim_cliente 7, dim_metodo_pago 6, dim_proveedor 6,
--              fact_ventas 16075, fact_produccion 826, fact_compras 124, fact_consumo_insumos 3371
SELECT 'dim_fecha' AS tabla, COUNT(*) AS filas FROM dw.dim_fecha
UNION ALL SELECT 'dim_producto', COUNT(*) FROM dw.dim_producto
UNION ALL SELECT 'dim_cliente', COUNT(*) FROM dw.dim_cliente
UNION ALL SELECT 'dim_metodo_pago', COUNT(*) FROM dw.dim_metodo_pago
UNION ALL SELECT 'dim_proveedor', COUNT(*) FROM dw.dim_proveedor
UNION ALL SELECT 'fact_ventas', COUNT(*) FROM dw.fact_ventas
UNION ALL SELECT 'fact_produccion', COUNT(*) FROM dw.fact_produccion
UNION ALL SELECT 'fact_compras', COUNT(*) FROM dw.fact_compras
UNION ALL SELECT 'fact_consumo_insumos', COUNT(*) FROM dw.fact_consumo_insumos;

-- B. Conciliación OLTP vs DW (las diferencias vienen de ventas cuyo total de cabecera
--    no coincide con sus líneas; el DW usa el importe de las líneas).
--    Esperado: oltp_total 190761.92 · dw_total 190289.42 · oltp_ventas 7814 · dw_ventas 7813
SELECT
  (SELECT SUM(total) FROM dbo.ventas WHERE estado = N'pagada')                     AS oltp_total,
  (SELECT SUM(importe) FROM dw.fact_ventas WHERE estado = N'pagada')               AS dw_total,
  (SELECT COUNT(*) FROM dbo.ventas WHERE estado = N'pagada')                       AS oltp_ventas,
  (SELECT COUNT(DISTINCT venta_id) FROM dw.fact_ventas WHERE estado = N'pagada')   AS dw_ventas;

-- C. Ventas por mes (Q1 del experimento)
SELECT d.anio, d.mes_num, d.mes, SUM(f.importe) AS ventas, COUNT(DISTINCT f.venta_id) AS tickets
FROM dw.fact_ventas f
JOIN dw.dim_fecha d ON d.fecha_key = f.fecha_key
WHERE f.estado = N'pagada'
GROUP BY d.anio, d.mes_num, d.mes
ORDER BY d.anio, d.mes_num;

-- D. Top 10 artículos por importe (Q2)
SELECT TOP 10 p.articulo, p.categoria, SUM(f.cantidad) AS unidades, SUM(f.importe) AS ventas
FROM dw.fact_ventas f
JOIN dw.dim_producto p ON p.producto_key = f.producto_key
WHERE f.estado = N'pagada'
GROUP BY p.articulo, p.categoria
ORDER BY ventas DESC;

-- E. Método de pago x día de la semana (Q3)
SELECT m.metodo_pago, d.dia_semana_num, d.dia_semana, COUNT(*) AS lineas, SUM(f.importe) AS ventas
FROM dw.fact_ventas f
JOIN dw.dim_metodo_pago m ON m.metodo_pago_key = f.metodo_pago_key
JOIN dw.dim_fecha d       ON d.fecha_key = f.fecha_key
WHERE f.estado = N'pagada'
GROUP BY m.metodo_pago, d.dia_semana_num, d.dia_semana
ORDER BY m.metodo_pago, d.dia_semana_num;

-- F. Ticket promedio por tipo de cliente (Q4)
WITH tickets AS (
    SELECT f.venta_id, c.tipo_cliente, SUM(f.importe) AS total
    FROM dw.fact_ventas f
    JOIN dw.dim_cliente c ON c.cliente_key = f.cliente_key
    WHERE f.estado = N'pagada'
    GROUP BY f.venta_id, c.tipo_cliente
)
SELECT tipo_cliente, COUNT(*) AS tickets, CAST(AVG(total) AS DECIMAL(12,2)) AS ticket_promedio
FROM tickets
GROUP BY tipo_cliente
ORDER BY tickets DESC;

-- G. Las 3 horas de mayor venta en cada mes (Q5, función de ventana)
WITH h AS (
    SELECT d.mes_num, f.hora, SUM(f.importe) AS ventas
    FROM dw.fact_ventas f
    JOIN dw.dim_fecha d ON d.fecha_key = f.fecha_key
    WHERE f.estado = N'pagada'
    GROUP BY d.mes_num, f.hora
)
SELECT mes_num, hora, ventas, puesto
FROM (SELECT *, RANK() OVER (PARTITION BY mes_num ORDER BY ventas DESC) AS puesto FROM h) r
WHERE puesto <= 3
ORDER BY mes_num, puesto;

-- H. Merma por producto (fact_produccion).  Esperado: merma total 12.49 % de lo programado
SELECT p.articulo, COUNT(*) AS ordenes, SUM(f.cantidad_programada) AS programado,
       SUM(f.merma_cantidad) AS merma,
       CAST(100.0 * SUM(f.merma_cantidad) / NULLIF(SUM(f.cantidad_programada), 0) AS DECIMAL(5,2)) AS pct_merma
FROM dw.fact_produccion f
JOIN dw.dim_producto p ON p.producto_key = f.producto_key
WHERE f.estado = N'finalizada'
GROUP BY ROLLUP (p.articulo)
ORDER BY GROUPING(p.articulo), pct_merma DESC;

-- I. Compras por proveedor.  Esperado: 27 compras, S/ 55 263.06 sin anuladas.
--    (3 compras de cabecera sin líneas de detalle, S/ 10 080.00, no entran al DW de líneas)
SELECT ISNULL(pr.proveedor, N'TOTAL') AS proveedor, COUNT(DISTINCT f.compra_id) AS compras, SUM(f.total) AS total
FROM dw.fact_compras f
JOIN dw.dim_proveedor pr ON pr.proveedor_key = f.proveedor_key
WHERE f.estado <> N'anulada'
GROUP BY ROLLUP (pr.proveedor)
ORDER BY GROUPING(pr.proveedor), total DESC;

-- J. Bitácora de la última carga ETL
SELECT TOP 20 proceso, filas, estado, DATEDIFF(MILLISECOND, inicio, fin) AS ms, mensaje, inicio
FROM dw.etl_log ORDER BY id DESC;
GO
