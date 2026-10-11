/* ==========================================================================
   06_experimento_sqlserver.sql  -  Experimento: tiempos de consulta en SQL Server
   Mide las consultas Q1..Q5 sobre dw.fact_ventas replicada x1, x10 y x50
   (las mismas consultas que ejecuta Spark en bigdata/src/experimento.py).
   Requisito: 02_dw_ddl.sql y 03_dw_etl.sql.
   Salida: tabla dw.exp_resultados -> exportar a experimento/resultados/sqlserver_resultados.csv
   ========================================================================== */
USE panaderia_db;
GO

CREATE OR ALTER PROCEDURE dw.sp_experimento
    @factor_escala INT,
    @repeticiones  INT = 3,      -- medidas por consulta (además de 1 de calentamiento)
    @columnstore   BIT = 0       -- 1 = probar también con índice columnar
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @plataforma NVARCHAR(20) = IIF(@columnstore = 1, N'sqlserver_cci', N'sqlserver');

    /* 1. Construir la tabla de hechos escalada (cada réplica con venta_id distinto) */
    IF OBJECT_ID(N'dw.fact_ventas_exp', N'U') IS NOT NULL DROP TABLE dw.fact_ventas_exp;

    ;WITH r AS (SELECT TOP (@factor_escala) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS rep
                FROM sys.all_objects)
    SELECT CAST(f.venta_id AS BIGINT) + CAST(r.rep AS BIGINT) * 1000000 AS venta_id,
           f.fecha_key, f.hora, f.producto_key, f.cliente_key, f.metodo_pago_key,
           f.estado, f.cantidad, f.importe
    INTO dw.fact_ventas_exp
    FROM dw.fact_ventas f CROSS JOIN r;

    IF @columnstore = 1
        CREATE CLUSTERED COLUMNSTORE INDEX cci_fact_ventas_exp ON dw.fact_ventas_exp;

    DECLARE @filas BIGINT = (SELECT COUNT_BIG(*) FROM dw.fact_ventas_exp);

    /* 2. Consultas del experimento (idénticas en significado a las de Spark SQL) */
    DECLARE @q TABLE (id NVARCHAR(10), sql NVARCHAR(MAX));
    INSERT INTO @q VALUES
    (N'Q1', N'SELECT d.anio, d.mes_num, SUM(f.importe) AS ventas, COUNT(DISTINCT f.venta_id) AS tickets
             INTO #r FROM dw.fact_ventas_exp f JOIN dw.dim_fecha d ON d.fecha_key = f.fecha_key
             WHERE f.estado = N''pagada'' GROUP BY d.anio, d.mes_num'),
    (N'Q2', N'SELECT TOP 10 p.articulo, SUM(f.cantidad) AS unidades, SUM(f.importe) AS ventas
             INTO #r FROM dw.fact_ventas_exp f JOIN dw.dim_producto p ON p.producto_key = f.producto_key
             WHERE f.estado = N''pagada'' GROUP BY p.articulo ORDER BY ventas DESC'),
    (N'Q3', N'SELECT m.metodo_pago, d.dia_semana_num, COUNT(*) AS lineas, SUM(f.importe) AS ventas
             INTO #r FROM dw.fact_ventas_exp f
             JOIN dw.dim_metodo_pago m ON m.metodo_pago_key = f.metodo_pago_key
             JOIN dw.dim_fecha d ON d.fecha_key = f.fecha_key
             WHERE f.estado = N''pagada'' GROUP BY m.metodo_pago, d.dia_semana_num'),
    (N'Q4', N'WITH t AS (SELECT f.venta_id, c.tipo_cliente, SUM(f.importe) AS total
                       FROM dw.fact_ventas_exp f JOIN dw.dim_cliente c ON c.cliente_key = f.cliente_key
                       WHERE f.estado = N''pagada'' GROUP BY f.venta_id, c.tipo_cliente)
             SELECT tipo_cliente, COUNT(*) AS tickets, AVG(total) AS ticket_promedio
             INTO #r FROM t GROUP BY tipo_cliente'),
    (N'Q5', N'WITH h AS (SELECT d.mes_num, f.hora, SUM(f.importe) AS ventas
                       FROM dw.fact_ventas_exp f JOIN dw.dim_fecha d ON d.fecha_key = f.fecha_key
                       WHERE f.estado = N''pagada'' GROUP BY d.mes_num, f.hora)
             SELECT mes_num, hora, ventas, puesto INTO #r
             FROM (SELECT *, RANK() OVER (PARTITION BY mes_num ORDER BY ventas DESC) AS puesto FROM h) x
             WHERE puesto <= 3');

    /* 3. Ejecutar y cronometrar: repetición 0 = calentamiento (caché), 1..N = medidas */
    DECLARE @id NVARCHAR(10), @sql NVARCHAR(MAX), @stmt NVARCHAR(MAX), @rep INT,
            @t0 DATETIME2(7), @ms INT, @res INT;
    DECLARE cq CURSOR LOCAL FAST_FORWARD FOR SELECT id, sql FROM @q ORDER BY id;
    OPEN cq; FETCH NEXT FROM cq INTO @id, @sql;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        -- el resultado se materializa en #r (sin enviarlo al cliente) y se cuentan sus filas
        SET @stmt = @sql + N'; SELECT @n = COUNT(*) FROM #r; DROP TABLE #r;';
        SET @rep = 0;
        WHILE @rep <= @repeticiones
        BEGIN
            SET @t0 = SYSDATETIME();
            EXEC sp_executesql @stmt, N'@n INT OUTPUT', @n = @res OUTPUT;
            SET @ms = DATEDIFF(MILLISECOND, @t0, SYSDATETIME());
            INSERT INTO dw.exp_resultados (plataforma, factor_escala, filas_hecho, consulta, repeticion, ms, filas_result)
            VALUES (@plataforma, @factor_escala, @filas, @id, @rep, @ms, @res);
            SET @rep += 1;
        END;
        FETCH NEXT FROM cq INTO @id, @sql;
    END;
    CLOSE cq; DEALLOCATE cq;
END;
GO

/* ==========================================================================
   EJECUCIÓN DEL EXPERIMENTO (x1, x10, x50). Con x50 tarda unos minutos.
   ========================================================================== */
DELETE FROM dw.exp_resultados WHERE plataforma LIKE N'sqlserver%';
EXEC dw.sp_experimento @factor_escala = 1;
EXEC dw.sp_experimento @factor_escala = 10;
EXEC dw.sp_experimento @factor_escala = 50;
-- Opcional: misma prueba con índice columnar (almacenamiento por columnas, como Parquet)
-- EXEC dw.sp_experimento @factor_escala = 50, @columnstore = 1;
GO

-- Resumen: promedio de las repeticiones medidas (sin el calentamiento)
SELECT plataforma, factor_escala, filas_hecho, consulta,
       AVG(ms) AS ms_promedio, MIN(ms) AS ms_min, MAX(ms) AS ms_max, MAX(filas_result) AS filas_result
FROM dw.exp_resultados
WHERE repeticion > 0
GROUP BY plataforma, factor_escala, filas_hecho, consulta
ORDER BY plataforma, factor_escala, consulta;

-- Detalle para exportar: en SSMS, clic derecho sobre el resultado -> "Guardar resultados como..."
--   -> experimento/resultados/sqlserver_resultados.csv
-- o desde la consola:
--   bcp "SELECT plataforma,factor_escala,filas_hecho,consulta,repeticion,ms,filas_result FROM panaderia_db.dw.exp_resultados" queryout experimento\resultados\sqlserver_resultados.csv -c -t, -S localhost -T
SELECT plataforma, factor_escala, filas_hecho, consulta, repeticion, ms, filas_result
FROM dw.exp_resultados
ORDER BY plataforma, factor_escala, consulta, repeticion;
GO
