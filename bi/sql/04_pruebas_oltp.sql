/* ==========================================================================
   CONSULTAS DE PRUEBA - panaderia_db (SQL Server)
   Ejecutar por bloques (seleccionar el bloque y F5 en SSMS).
   Donde aparece "Esperado:" es el resultado que debe salir con los datos
   importados del volcado original.
   Las pruebas que modifican datos van dentro de BEGIN TRAN ... ROLLBACK,
   así que no alteran la base.
   ========================================================================== */
USE panaderia_db;
GO

/* ==========================================================================
   1. VERIFICACIÓN DE LA MIGRACIÓN
   ========================================================================== */

-- 1.1 Conteo de filas por tabla vs. el original (la columna "ok" debe ser 1 en todas)
SELECT t.tabla, t.filas, t.esperado, IIF(t.filas = t.esperado, 1, 0) AS ok
FROM (
          SELECT 'caja' AS tabla,      (SELECT COUNT(*) FROM caja) AS filas,                0 AS esperado
UNION ALL SELECT 'categorias',             (SELECT COUNT(*) FROM categorias),               7
UNION ALL SELECT 'clientes',               (SELECT COUNT(*) FROM clientes),                 6
UNION ALL SELECT 'compras',                (SELECT COUNT(*) FROM compras),                 32
UNION ALL SELECT 'consumo_insumos',        (SELECT COUNT(*) FROM consumo_insumos),       3371
UNION ALL SELECT 'detalle_receta',         (SELECT COUNT(*) FROM detalle_receta),          28
UNION ALL SELECT 'empresa',                (SELECT COUNT(*) FROM empresa),                  1
UNION ALL SELECT 'items_compra',           (SELECT COUNT(*) FROM items_compra),           124
UNION ALL SELECT 'items_produccion',       (SELECT COUNT(*) FROM items_produccion),       823
UNION ALL SELECT 'items_venta',            (SELECT COUNT(*) FROM items_venta),          16075
UNION ALL SELECT 'marcas',                 (SELECT COUNT(*) FROM marcas),                   7
UNION ALL SELECT 'metodos_pago',           (SELECT COUNT(*) FROM metodos_pago),             5
UNION ALL SELECT 'movimientos_caja',       (SELECT COUNT(*) FROM movimientos_caja),         2
UNION ALL SELECT 'movimientos_inventario', (SELECT COUNT(*) FROM movimientos_inventario), 20417
UNION ALL SELECT 'permisos',               (SELECT COUNT(*) FROM permisos),                19
UNION ALL SELECT 'producciones',           (SELECT COUNT(*) FROM producciones),           826
UNION ALL SELECT 'productos',              (SELECT COUNT(*) FROM productos),               16
UNION ALL SELECT 'proveedores',            (SELECT COUNT(*) FROM proveedores),              6
UNION ALL SELECT 'recetas',                (SELECT COUNT(*) FROM recetas),                  7
UNION ALL SELECT 'registros_auditoria',    (SELECT COUNT(*) FROM registros_auditoria),    249
UNION ALL SELECT 'roles',                  (SELECT COUNT(*) FROM roles),                    3
UNION ALL SELECT 'roles_permisos',         (SELECT COUNT(*) FROM roles_permisos),          25
UNION ALL SELECT 'sesiones_caja',          (SELECT COUNT(*) FROM sesiones_caja),          370
UNION ALL SELECT 'unidades',               (SELECT COUNT(*) FROM unidades),                 7
UNION ALL SELECT 'usuarios',               (SELECT COUNT(*) FROM usuarios),                 3
UNION ALL SELECT 'variantes_producto',     (SELECT COUNT(*) FROM variantes_producto),      20
UNION ALL SELECT 'ventas',                 (SELECT COUNT(*) FROM ventas),                7982
) t
ORDER BY ok, t.tabla;

-- 1.2 Objetos creados.  Esperado: 27 tablas, 26 claves foráneas, 3 procedimientos, 2 CHECK
SELECT
    (SELECT COUNT(*) FROM sys.tables)             AS tablas,
    (SELECT COUNT(*) FROM sys.foreign_keys)       AS claves_foraneas,
    (SELECT COUNT(*) FROM sys.procedures)         AS procedimientos,
    (SELECT COUNT(*) FROM sys.check_constraints)  AS restricciones_check;

-- 1.3 Contadores IDENTITY (último ID usado).  Esperado: ventas 7990, items_venta 16090, productos 23
SELECT 'ventas' AS tabla, IDENT_CURRENT('dbo.ventas') AS ultimo_id
UNION ALL SELECT 'items_venta', IDENT_CURRENT('dbo.items_venta')
UNION ALL SELECT 'productos',   IDENT_CURRENT('dbo.productos')
UNION ALL SELECT 'movimientos_inventario', IDENT_CURRENT('dbo.movimientos_inventario');

-- 1.4 Tildes y ñ guardadas correctamente (NVARCHAR).  Esperado: aparecen "Producción" y "Anulación"
SELECT DISTINCT tipo FROM movimientos_inventario WHERE tipo COLLATE Latin1_General_CS_AS LIKE N'%ó%';

-- 1.5 El JSON de auditoría se lee como JSON válido.  Esperado: Panes, Gloria, Harina...
SELECT TOP 5 id, accion, nombre_tabla,
       JSON_VALUE(datos_nuevos, '$.nombre') AS nombre_en_json
FROM registros_auditoria
WHERE ISJSON(datos_nuevos) = 1
ORDER BY id;


/* ==========================================================================
   2. CONSULTAS BÁSICAS (SELECT, WHERE, ORDER BY, TOP)
   ========================================================================== */

-- 2.1 Productos activos con su categoría y unidad de medida
SELECT p.id, p.nombre, p.tipo, c.nombre AS categoria, u.simbolo AS unidad
FROM productos p
LEFT JOIN categorias c ON c.id = p.categoria_id
LEFT JOIN unidades  u ON u.id = p.unidad_id
WHERE p.activo = 1
ORDER BY p.tipo, p.nombre;

-- 2.2 Las 10 ventas más altas
SELECT TOP 10 id, fecha, total, tipo_comprobante, numero_comprobante
FROM ventas
WHERE estado = N'pagada'
ORDER BY total DESC;

-- 2.3 Ventas de un día concreto
SELECT id, fecha, total, metodo_pago_id, estado
FROM ventas
WHERE CAST(fecha AS DATE) = '2026-09-30'
ORDER BY fecha;

-- 2.4 Clientes con RUC (empresas: documento de 11 dígitos que empieza con 20)
SELECT id, nombre, documento, email
FROM clientes
WHERE documento LIKE '20%' AND LEN(documento) = 11;

-- 2.5 Rango de fechas con datos.  Esperado: ventas del 2026-01-15 al 2026-09-30
SELECT MIN(fecha) AS primera_venta, MAX(fecha) AS ultima_venta FROM ventas;


/* ==========================================================================
   3. JOINS
   ========================================================================== */

-- 3.1 Detalle completo de una venta (cabecera + líneas + producto)
SELECT v.id AS venta, v.fecha, v.numero_comprobante, mp.nombre AS metodo_pago,
       ISNULL(cl.nombre, N'Consumidor final') AS cliente,
       vp.sku, vp.nombre AS variante, iv.cantidad, iv.precio_unitario, iv.descuento,
       iv.cantidad * iv.precio_unitario - iv.descuento AS subtotal
FROM ventas v
JOIN items_venta iv          ON iv.venta_id = v.id
JOIN variantes_producto vp   ON vp.id = iv.variante_id
LEFT JOIN metodos_pago mp    ON mp.id = v.metodo_pago_id
LEFT JOIN clientes cl        ON cl.id = v.cliente_id
WHERE v.id = 7989;

-- 3.2 Usuarios con su rol y la cantidad de permisos del rol
SELECT u.usuario, r.nombre AS rol, COUNT(rp.permiso_id) AS num_permisos
FROM usuarios u
LEFT JOIN roles r           ON r.id_rol = u.rol_id
LEFT JOIN roles_permisos rp ON rp.rol_id = r.id_rol
GROUP BY u.usuario, r.nombre;

-- 3.3 Receta con sus insumos (pan francés clásico, receta 4)
SELECT r.nombre AS receta, r.rendimiento, vp.nombre AS insumo, p.nombre AS producto_insumo, dr.cantidad
FROM recetas r
JOIN detalle_receta dr     ON dr.receta_id = r.id
JOIN variantes_producto vp ON vp.id = dr.variante_id
JOIN productos p           ON p.id = vp.producto_id
WHERE r.id = 4;

-- 3.4 Compras con proveedor y número de ítems
SELECT c.id, c.fecha, pr.nombre AS proveedor, c.numero_comprobante, c.estado, c.total,
       COUNT(ic.id) AS items
FROM compras c
JOIN proveedores pr       ON pr.id = c.proveedor_id
LEFT JOIN items_compra ic ON ic.compra_id = c.id
GROUP BY c.id, c.fecha, pr.nombre, c.numero_comprobante, c.estado, c.total
ORDER BY c.fecha DESC;


/* ==========================================================================
   4. AGREGACIONES (GROUP BY, HAVING)
   ========================================================================== */

-- 4.1 Resumen general de ventas.
--     Esperado: 7982 ventas, 7814 pagadas, 168 anuladas, total pagado 190 761.92
SELECT COUNT(*)                                        AS ventas,
       SUM(IIF(estado = N'pagada', 1, 0))              AS pagadas,
       SUM(IIF(estado = N'anulada', 1, 0))             AS anuladas,
       SUM(IIF(estado = N'pagada', total, 0))          AS total_pagado,
       CAST(AVG(IIF(estado = N'pagada', total, NULL)) AS DECIMAL(10,2)) AS ticket_promedio
FROM ventas;

-- 4.2 Ventas por mes.  Esperado (pagadas): abr 30 252.04 · may 33 116.81 · jun 31 289.25
--                                          jul 31 167.74 · ago 32 747.53 · sep 30 996.05
SELECT YEAR(fecha) AS anio, MONTH(fecha) AS mes,
       COUNT(*) AS num_ventas, SUM(total) AS total
FROM ventas
WHERE estado = N'pagada'
GROUP BY YEAR(fecha), MONTH(fecha)
ORDER BY anio, mes;

-- 4.3 Ventas por método de pago.
--     Esperado: Efectivo 3618 / 88 495.15 · Yape 2076 / 48 962.92 · Plin 911 / 22 733.26
--               Tarjeta 829 / 20 285.67 · Transferencia 380 / 10 284.92
SELECT mp.nombre, COUNT(*) AS num_ventas, SUM(v.total) AS total,
       CAST(100.0 * COUNT(*) / SUM(COUNT(*)) OVER () AS DECIMAL(5,2)) AS porcentaje
FROM ventas v
JOIN metodos_pago mp ON mp.id = v.metodo_pago_id
WHERE v.estado = N'pagada'
GROUP BY mp.nombre
ORDER BY total DESC;

-- 4.4 Productos más vendidos (unidades).
--     Esperado: Pan Frances 96 463 · Croissant 7 023 · Pan de molde 3 939 · Gaseosa 1 199 ...
SELECT TOP 10 vp.id, p.nombre AS producto, vp.nombre AS variante,
       SUM(iv.cantidad) AS unidades,
       SUM(iv.cantidad * iv.precio_unitario - iv.descuento) AS importe
FROM items_venta iv
JOIN ventas v              ON v.id = iv.venta_id AND v.estado = N'pagada'
JOIN variantes_producto vp ON vp.id = iv.variante_id
JOIN productos p           ON p.id = vp.producto_id
GROUP BY vp.id, p.nombre, vp.nombre
ORDER BY unidades DESC;

-- 4.5 Ventas por día de la semana (independiente del idioma del servidor)
SELECT CHOOSE((DATEDIFF(DAY, '19000107', fecha) % 7) + 1,
              N'Domingo', N'Lunes', N'Martes', N'Miércoles', N'Jueves', N'Viernes', N'Sábado') AS dia,
       COUNT(*) AS num_ventas, SUM(total) AS total
FROM ventas
WHERE estado = N'pagada'
GROUP BY (DATEDIFF(DAY, '19000107', fecha) % 7)
ORDER BY (DATEDIFF(DAY, '19000107', fecha) % 7);

-- 4.6 Ventas por franja horaria
SELECT DATEPART(HOUR, fecha) AS hora, COUNT(*) AS num_ventas, SUM(total) AS total
FROM ventas
WHERE estado = N'pagada'
GROUP BY DATEPART(HOUR, fecha)
ORDER BY hora;

-- 4.7 Merma de producción por producto (HAVING: solo los que tienen más de 50 órdenes)
SELECT p.nombre, COUNT(*) AS ordenes,
       SUM(pr.cantidad_programada) AS programado,
       SUM(pr.cantidad_obtenida)   AS obtenido,
       SUM(pr.merma_cantidad)      AS merma,
       CAST(100.0 * SUM(pr.merma_cantidad) / NULLIF(SUM(pr.cantidad_programada), 0) AS DECIMAL(5,2)) AS pct_merma
FROM producciones pr
JOIN variantes_producto vp ON vp.id = pr.variante_salida_id
JOIN productos p           ON p.id = vp.producto_id
GROUP BY p.nombre
HAVING COUNT(*) > 50
ORDER BY pct_merma DESC;

-- 4.8 Motivos de merma más frecuentes
SELECT merma_motivo, COUNT(*) AS veces, SUM(merma_cantidad) AS unidades
FROM producciones
WHERE merma_motivo IS NOT NULL
GROUP BY merma_motivo
ORDER BY veces DESC;

-- 4.9 Compras por proveedor
SELECT pr.nombre, COUNT(c.id) AS compras, SUM(c.total) AS total_comprado
FROM proveedores pr
LEFT JOIN compras c ON c.proveedor_id = pr.id AND c.estado <> N'anulada'
GROUP BY pr.nombre
ORDER BY total_comprado DESC;

-- 4.10 Mejores clientes identificados
SELECT cl.nombre, COUNT(*) AS compras, SUM(v.total) AS total
FROM ventas v
JOIN clientes cl ON cl.id = v.cliente_id
WHERE v.estado = N'pagada'
GROUP BY cl.nombre
ORDER BY total DESC;


/* ==========================================================================
   5. SUBCONSULTAS, CTE Y FUNCIONES DE VENTANA
   ========================================================================== */

-- 5.1 Ventas por encima del ticket promedio (subconsulta escalar).  Esperado: 2717
SELECT COUNT(*) AS ventas_sobre_promedio
FROM ventas
WHERE estado = N'pagada'
  AND total > (SELECT AVG(total) FROM ventas WHERE estado = N'pagada');

-- 5.2 Ventas diarias con acumulado del mes (CTE + SUM OVER)
WITH diario AS (
    SELECT CAST(fecha AS DATE) AS dia, SUM(total) AS total_dia
    FROM ventas
    WHERE estado = N'pagada' AND fecha >= '2026-09-01' AND fecha < '2026-10-01'
    GROUP BY CAST(fecha AS DATE)
)
SELECT dia, total_dia,
       SUM(total_dia) OVER (ORDER BY dia ROWS UNBOUNDED PRECEDING) AS acumulado_mes,
       AVG(total_dia) OVER (ORDER BY dia ROWS 6 PRECEDING)         AS promedio_movil_7d
FROM diario
ORDER BY dia;

-- 5.3 Ranking de productos por mes (RANK + PARTITION BY): el top 3 de cada mes
WITH ventas_mes AS (
    SELECT FORMAT(v.fecha, 'yyyy-MM') AS mes, vp.nombre AS variante,
           SUM(iv.cantidad * iv.precio_unitario - iv.descuento) AS importe
    FROM items_venta iv
    JOIN ventas v              ON v.id = iv.venta_id AND v.estado = N'pagada'
    JOIN variantes_producto vp ON vp.id = iv.variante_id
    GROUP BY FORMAT(v.fecha, 'yyyy-MM'), vp.nombre
)
SELECT *
FROM (SELECT mes, variante, importe,
             RANK() OVER (PARTITION BY mes ORDER BY importe DESC) AS puesto
      FROM ventas_mes) x
WHERE puesto <= 3
ORDER BY mes, puesto;

-- 5.4 Crecimiento mes a mes (LAG)
WITH m AS (
    SELECT DATEFROMPARTS(YEAR(fecha), MONTH(fecha), 1) AS mes, SUM(total) AS total
    FROM ventas
    WHERE estado = N'pagada' AND fecha >= '2026-04-01'
    GROUP BY DATEFROMPARTS(YEAR(fecha), MONTH(fecha), 1)
)
SELECT mes, total,
       LAG(total) OVER (ORDER BY mes) AS mes_anterior,
       CAST(100.0 * (total - LAG(total) OVER (ORDER BY mes))
            / NULLIF(LAG(total) OVER (ORDER BY mes), 0) AS DECIMAL(6,2)) AS variacion_pct
FROM m
ORDER BY mes;

-- 5.5 Kardex de una variante: últimos 20 movimientos del Pan Francés (id 15)
SELECT TOP 20 mi.fecha, mi.tipo, mi.motivo, mi.cantidad, mi.stock_anterior, mi.stock_nuevo
FROM movimientos_inventario mi
WHERE mi.variante_id = 15
ORDER BY mi.fecha DESC, mi.id DESC;

-- 5.6 Productos que nunca se vendieron (NOT EXISTS).  Esperado: 9 filas (insumos y algunos ítems)
SELECT vp.id, vp.sku, vp.nombre
FROM variantes_producto vp
WHERE NOT EXISTS (SELECT 1 FROM items_venta iv WHERE iv.variante_id = vp.id);

-- 5.7 Consumo teórico de insumos vs. consumo registrado en septiembre
SELECT vp.nombre AS insumo, SUM(ci.cantidad) AS consumido
FROM consumo_insumos ci
JOIN variantes_producto vp ON vp.id = ci.variante_id
WHERE ci.fecha >= '2026-09-01' AND ci.fecha < '2026-10-01'
GROUP BY vp.nombre
ORDER BY consumido DESC;

-- 5.8 Cuadre de caja por sesión (últimas 10)
SELECT TOP 10 s.id, s.abierto_en, s.cerrado_en, s.monto_apertura, s.monto_esperado,
       s.monto_cierre, s.diferencia,
       (SELECT COUNT(*) FROM ventas v WHERE v.sesion_caja_id = s.id) AS num_ventas
FROM sesiones_caja s
ORDER BY s.id DESC;


/* ==========================================================================
   6. CALIDAD E INTEGRIDAD DE LOS DATOS
   (Estas consultas detectan incoherencias que YA venían en el volcado
    original; no son errores de la migración.)
   ========================================================================== */

-- 6.1 Productos con stock negativo.  Esperado: 6 filas (ids 1, 4, 11, 22, 24, 27)
SELECT vp.id, vp.sku, vp.nombre, vp.stock, vp.stock_minimo
FROM variantes_producto vp
WHERE vp.stock < 0
ORDER BY vp.stock;

-- 6.2 Productos por debajo del stock mínimo (alerta de reposición)
SELECT vp.id, p.nombre, vp.nombre AS variante, vp.stock, vp.stock_minimo
FROM variantes_producto vp
JOIN productos p ON p.id = vp.producto_id
WHERE vp.activo = 1 AND p.controla_stock = 1 AND vp.stock < vp.stock_minimo;

-- 6.3 Ventas cuyo total no coincide con la suma de sus líneas.  Esperado: 6 filas
--     (5 con diferencia + la venta 22, que no tiene líneas)
SELECT v.id, v.total, x.suma_lineas, v.total - ISNULL(x.suma_lineas, 0) AS diferencia
FROM ventas v
LEFT JOIN (SELECT venta_id, ROUND(SUM(cantidad * precio_unitario - descuento), 2) AS suma_lineas
           FROM items_venta GROUP BY venta_id) x ON x.venta_id = v.id
WHERE ABS(v.total - ISNULL(x.suma_lineas, 0)) > 0.01;

-- 6.4 Compras cuyo total no coincide con sus ítems.  Esperado: 0 filas
SELECT c.id, c.total, SUM(ic.total) AS suma_items
FROM compras c
JOIN items_compra ic ON ic.compra_id = c.id
GROUP BY c.id, c.total
HAVING ABS(c.total - SUM(ic.total)) > 0.01;

-- 6.5 Producciones donde programado <> obtenido + merma.  Esperado: 9 filas
SELECT id, referencia, cantidad_programada, cantidad_obtenida, merma_cantidad
FROM producciones
WHERE ABS(cantidad_programada - cantidad_obtenida - merma_cantidad) > 0.001;

-- 6.6 Números de comprobante: Esperado 7982 ventas y 7973 números distintos. La diferencia son 9 ventas
--     SIN número (NULL), que el GROUP BY de abajo muestra como un grupo NULL; no hay números repetidos.
SELECT COUNT(*) AS ventas, COUNT(DISTINCT numero_comprobante) AS comprobantes_distintos FROM ventas;

SELECT numero_comprobante, COUNT(*) AS veces
FROM ventas
GROUP BY numero_comprobante
HAVING COUNT(*) > 1;

-- 6.7 Huérfanos (deben ser 0 gracias a las claves foráneas)
SELECT
  (SELECT COUNT(*) FROM items_venta iv WHERE NOT EXISTS (SELECT 1 FROM ventas v WHERE v.id = iv.venta_id)) AS items_sin_venta,
  (SELECT COUNT(*) FROM ventas v WHERE v.cliente_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM clientes c WHERE c.id = v.cliente_id))                          AS ventas_cliente_inexistente,
  (SELECT COUNT(*) FROM movimientos_inventario m
        WHERE NOT EXISTS (SELECT 1 FROM variantes_producto vp WHERE vp.id = m.variante_id))            AS movimientos_sin_variante;

-- 6.8 Textos con caracteres mal codificados (vienen así del origen, p. ej. "auditor├¡a")
SELECT id_rol, nombre, descripcion FROM roles WHERE descripcion LIKE N'%├%';


/* ==========================================================================
   7. PRUEBAS DE RESTRICCIONES (todas se deshacen con ROLLBACK)
   Nota: un INSERT que falla o se revierte igual consume un número IDENTITY;
   es normal en SQL Server y solo deja un salto en la numeración.
   ========================================================================== */

-- 7.1 Valores por defecto e IDENTITY: insertar una categoría solo con el nombre
BEGIN TRAN;
    INSERT INTO categorias (nombre) VALUES (N'Categoría de prueba');
    SELECT id, nombre, creado_en FROM categorias WHERE id = SCOPE_IDENTITY();   -- creado_en = fecha/hora actual
ROLLBACK;

-- 7.2 Clave foránea: venta con método de pago inexistente.  Esperado: error 547 (FOREIGN KEY)
BEGIN TRY
    INSERT INTO ventas (cliente_id, fecha, total, metodo_pago_id, tipo_comprobante)
    VALUES (NULL, SYSDATETIME(), 10, 999, N'boleta');
    PRINT 'FALLO DE PRUEBA: se insertó una venta con FK inválida';
END TRY
BEGIN CATCH
    PRINT 'OK 7.2 -> ' + ERROR_MESSAGE();
END CATCH;

-- 7.3 CHECK del enum: estado no permitido.  Esperado: error 547 (CHECK ck_ventas_estado)
BEGIN TRY
    UPDATE ventas SET estado = N'devuelta' WHERE id = 7990;
    PRINT 'FALLO DE PRUEBA: se aceptó un estado inválido';
END TRY
BEGIN CATCH
    PRINT 'OK 7.3 -> ' + ERROR_MESSAGE();
END CATCH;

-- 7.4 CHECK de productos.tipo.  Esperado: error 547 (CHECK ck_productos_tipo)
BEGIN TRY
    INSERT INTO productos (nombre, tipo) VALUES (N'Prueba', N'servicio');
    PRINT 'FALLO DE PRUEBA: se aceptó un tipo inválido';
END TRY
BEGIN CATCH
    PRINT 'OK 7.4 -> ' + ERROR_MESSAGE();
END CATCH;

-- 7.5 UNIQUE: usuario repetido.  Esperado: error 2601 (índice único)
BEGIN TRY
    INSERT INTO usuarios (usuario, rol_id) VALUES (N'admin', 1);
    PRINT 'FALLO DE PRUEBA: se duplicó el usuario';
END TRY
BEGIN CATCH
    PRINT 'OK 7.5 -> ' + ERROR_MESSAGE();
END CATCH;

-- 7.6 UNIQUE filtrado: se permiten varios proveedores sin documento (NULL), pero no RUC repetidos
BEGIN TRAN;
    INSERT INTO proveedores (nombre, documento) VALUES (N'Prov sin doc A', NULL), (N'Prov sin doc B', NULL);
    PRINT 'OK 7.6a -> se aceptan varios NULL';
    BEGIN TRY
        INSERT INTO proveedores (nombre, documento) VALUES (N'Molinos duplicado', N'20111111111');
        PRINT 'FALLO DE PRUEBA: se duplicó el RUC';
    END TRY
    BEGIN CATCH
        PRINT 'OK 7.6b -> ' + ERROR_MESSAGE();
    END CATCH;
ROLLBACK;

-- 7.7 ON DELETE CASCADE: al borrar una venta se borran sus líneas.  Esperado: antes 3, después 0
BEGIN TRAN;
    SELECT COUNT(*) AS lineas_antes   FROM items_venta WHERE venta_id = 7989;
    DELETE FROM ventas WHERE id = 7989;
    SELECT COUNT(*) AS lineas_despues FROM items_venta WHERE venta_id = 7989;
ROLLBACK;

-- 7.8 ON DELETE SET NULL: al borrar un cliente sus ventas quedan con cliente_id NULL
BEGIN TRAN;
    SELECT COUNT(*) AS ventas_cliente_7 FROM ventas WHERE cliente_id = 7;          -- 353
    DELETE FROM clientes WHERE id = 7;
    SELECT COUNT(*) AS ventas_cliente_7_despues FROM ventas WHERE cliente_id = 7;   -- 0
ROLLBACK;

-- 7.9 Restricción sin cascada: no se puede borrar un método de pago en uso.  Esperado: error 547
BEGIN TRY
    BEGIN TRAN;
        DELETE FROM metodos_pago WHERE id = 1;
        PRINT 'FALLO DE PRUEBA: se borró un método de pago en uso';
    ROLLBACK;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK;
    PRINT 'OK 7.9 -> ' + ERROR_MESSAGE();
END CATCH;


/* ==========================================================================
   8. PRUEBA DE LOS PROCEDIMIENTOS ALMACENADOS (se deshacen con ROLLBACK)
   2026-10-05 es lunes (día de compra), así se prueban los tres.
   ========================================================================== */
BEGIN TRAN;
    DECLARE @v0 INT = (SELECT COUNT(*) FROM ventas),
            @p0 INT = (SELECT COUNT(*) FROM producciones),
            @c0 INT = (SELECT COUNT(*) FROM compras);

    EXEC dbo.sp_seed_compras    '2026-10-05', '2026-10-05';
    EXEC dbo.sp_seed_produccion '2026-10-05', '2026-10-05';
    EXEC dbo.sp_seed_ventas     '2026-10-05', '2026-10-05';

    -- Esperado: 1 compra nueva, 4 o 5 producciones nuevas, ~30-45 ventas nuevas
    SELECT (SELECT COUNT(*) FROM compras)      - @c0 AS compras_nuevas,
           (SELECT COUNT(*) FROM producciones) - @p0 AS producciones_nuevas,
           (SELECT COUNT(*) FROM ventas)       - @v0 AS ventas_nuevas;

    -- Coherencia: el total de cada venta nueva = suma de sus líneas (esperado: 0 filas)
    SELECT v.id, v.total, SUM(ROUND(iv.cantidad * iv.precio_unitario - iv.descuento, 2)) AS suma
    FROM ventas v JOIN items_venta iv ON iv.venta_id = v.id
    WHERE CAST(v.fecha AS DATE) = '2026-10-05'
    GROUP BY v.id, v.total
    HAVING ABS(v.total - SUM(ROUND(iv.cantidad * iv.precio_unitario - iv.descuento, 2))) > 0.01;

    -- Producción del día: referencia, cantidades y merma
    SELECT referencia, cantidad_programada, cantidad_obtenida, merma_cantidad, merma_motivo
    FROM producciones WHERE CAST(fecha AS DATE) = '2026-10-05';

    -- Cierre de caja del día
    SELECT id, abierto_en, cerrado_en, monto_apertura, monto_esperado, monto_cierre, diferencia
    FROM sesiones_caja WHERE CAST(abierto_en AS DATE) = '2026-10-05';
ROLLBACK;

-- Comprobación final: nada cambió.  Esperado: 7982 ventas, 826 producciones, 32 compras
SELECT (SELECT COUNT(*) FROM ventas) AS ventas,
       (SELECT COUNT(*) FROM producciones) AS producciones,
       (SELECT COUNT(*) FROM compras) AS compras;
GO
