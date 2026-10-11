/* ==========================================================================
   02_dw_ddl.sql  -  Data warehouse (modelo estrella) de la Panadería Chapala
   Motor: SQL Server 2016+      Base: panaderia_db      Esquema: dw
   Requisito previo: 01_crear_bd_oltp.sql
   Granos:
     fact_ventas          1 fila = 1 línea de venta (items_venta)
     fact_produccion      1 fila = 1 orden de producción
     fact_compras         1 fila = 1 línea de compra (items_compra)
     fact_consumo_insumos 1 fila = 1 consumo de insumo por orden
   ========================================================================== */
USE panaderia_db;
GO
IF SCHEMA_ID(N'dw') IS NULL EXEC (N'CREATE SCHEMA dw AUTHORIZATION dbo;');
GO

-- Limpieza (permite re-ejecutar): primero hechos, luego dimensiones
DECLARE @t NVARCHAR(200);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR
    SELECT N'dw.' + QUOTENAME(name) FROM (VALUES
        (1, 'fact_ventas_exp'), (2, 'fact_ventas'), (3, 'fact_produccion'), (4, 'fact_compras'),
        (5, 'fact_consumo_insumos'), (6, 'dim_fecha'), (7, 'dim_producto'), (8, 'dim_cliente'),
        (9, 'dim_metodo_pago'), (10, 'dim_proveedor'), (11, 'etl_log'), (12, 'exp_resultados')) v(ord, name)
    WHERE OBJECT_ID(N'dw.' + name, N'U') IS NOT NULL
    ORDER BY ord;
OPEN c; FETCH NEXT FROM c INTO @t;
WHILE @@FETCH_STATUS = 0 BEGIN EXEC (N'DROP TABLE ' + @t); FETCH NEXT FROM c INTO @t; END;
CLOSE c; DEALLOCATE c;
GO

/* ------------------------------------------------------------ DIMENSIONES */
CREATE TABLE dw.dim_fecha (
    fecha_key         INT          NOT NULL CONSTRAINT pk_dim_fecha PRIMARY KEY,   -- yyyymmdd
    fecha             DATE         NOT NULL,
    anio              SMALLINT     NOT NULL,
    trimestre         TINYINT      NOT NULL,
    mes_num           TINYINT      NOT NULL,
    mes               NVARCHAR(3)  NOT NULL,     -- Ene, Feb, ...
    dia               TINYINT      NOT NULL,
    dia_semana_num    TINYINT      NOT NULL,     -- 1 = lunes ... 7 = domingo
    dia_semana        NVARCHAR(3)  NOT NULL,     -- Lun, Mar, ...
    es_fin_semana     BIT          NOT NULL
);

CREATE TABLE dw.dim_producto (
    producto_key      INT IDENTITY(1,1) NOT NULL CONSTRAINT pk_dim_producto PRIMARY KEY,
    variante_id       INT           NOT NULL CONSTRAINT uq_dim_producto_variante UNIQUE,   -- clave de negocio
    sku               NVARCHAR(100) NULL,
    producto          NVARCHAR(255) NOT NULL,
    variante          NVARCHAR(255) NULL,
    articulo          NVARCHAR(520) NOT NULL,    -- producto - variante
    tipo              NVARCHAR(20)  NOT NULL,    -- insumo / elaborado / reventa
    categoria         NVARCHAR(150) NOT NULL,
    unidad            NVARCHAR(50)  NOT NULL,
    precio_venta      DECIMAL(12,2) NULL,
    stock             DECIMAL(12,3) NULL,
    stock_minimo      DECIMAL(12,3) NULL,
    estado_stock      NVARCHAR(20)  NOT NULL,    -- OK / Bajo mínimo / Negativo
    activo            BIT           NOT NULL
);

CREATE TABLE dw.dim_cliente (
    cliente_key       INT IDENTITY(1,1) NOT NULL CONSTRAINT pk_dim_cliente PRIMARY KEY,
    cliente_id        INT           NOT NULL CONSTRAINT uq_dim_cliente_id UNIQUE,   -- 0 = consumidor final
    nombre            NVARCHAR(255) NOT NULL,
    documento         NVARCHAR(50)  NULL,
    tipo_cliente      NVARCHAR(20)  NOT NULL     -- Empresa / Persona / Consumidor final
);

CREATE TABLE dw.dim_metodo_pago (
    metodo_pago_key   INT IDENTITY(1,1) NOT NULL CONSTRAINT pk_dim_metodo_pago PRIMARY KEY,
    metodo_pago_id    INT           NOT NULL CONSTRAINT uq_dim_metodo_pago_id UNIQUE,
    metodo_pago       NVARCHAR(100) NOT NULL
);

CREATE TABLE dw.dim_proveedor (
    proveedor_key     INT IDENTITY(1,1) NOT NULL CONSTRAINT pk_dim_proveedor PRIMARY KEY,
    proveedor_id      INT           NOT NULL CONSTRAINT uq_dim_proveedor_id UNIQUE,
    proveedor         NVARCHAR(255) NOT NULL,
    documento         NVARCHAR(50)  NULL
);

/* ------------------------------------------------------------ HECHOS */
CREATE TABLE dw.fact_ventas (
    item_venta_id     INT           NOT NULL CONSTRAINT pk_fact_ventas PRIMARY KEY,
    venta_id          INT           NOT NULL,              -- dimensión degenerada
    fecha_key         INT           NOT NULL CONSTRAINT fk_fv_fecha    REFERENCES dw.dim_fecha (fecha_key),
    hora              TINYINT       NOT NULL,
    producto_key      INT           NOT NULL CONSTRAINT fk_fv_producto REFERENCES dw.dim_producto (producto_key),
    cliente_key       INT           NOT NULL CONSTRAINT fk_fv_cliente  REFERENCES dw.dim_cliente (cliente_key),
    metodo_pago_key   INT           NOT NULL CONSTRAINT fk_fv_metodo   REFERENCES dw.dim_metodo_pago (metodo_pago_key),
    tipo_comprobante  NVARCHAR(20)  NOT NULL,
    estado            NVARCHAR(10)  NOT NULL,              -- pagada / anulada / pendiente
    cantidad          DECIMAL(12,3) NOT NULL,
    precio_unitario   DECIMAL(12,2) NOT NULL,
    descuento         DECIMAL(12,2) NOT NULL,
    importe           DECIMAL(14,2) NOT NULL               -- cantidad * precio - descuento
);
CREATE INDEX ix_fv_fecha    ON dw.fact_ventas (fecha_key) INCLUDE (importe, estado);
CREATE INDEX ix_fv_producto ON dw.fact_ventas (producto_key);
CREATE INDEX ix_fv_venta    ON dw.fact_ventas (venta_id);

CREATE TABLE dw.fact_produccion (
    produccion_id       INT           NOT NULL CONSTRAINT pk_fact_produccion PRIMARY KEY,
    referencia          NVARCHAR(100) NULL,
    fecha_key           INT           NOT NULL CONSTRAINT fk_fp_fecha    REFERENCES dw.dim_fecha (fecha_key),
    producto_key        INT           NOT NULL CONSTRAINT fk_fp_producto REFERENCES dw.dim_producto (producto_key),
    cantidad_programada DECIMAL(12,3) NOT NULL,
    cantidad_obtenida   DECIMAL(12,3) NOT NULL,
    merma_cantidad      DECIMAL(12,3) NOT NULL,
    motivo_merma        NVARCHAR(255) NOT NULL,
    estado              NVARCHAR(50)  NOT NULL
);
CREATE INDEX ix_fp_fecha ON dw.fact_produccion (fecha_key);

CREATE TABLE dw.fact_compras (
    item_compra_id    INT           NOT NULL CONSTRAINT pk_fact_compras PRIMARY KEY,
    compra_id         INT           NOT NULL,              -- dimensión degenerada
    numero_comprobante NVARCHAR(100) NULL,
    fecha_key         INT           NOT NULL CONSTRAINT fk_fc_fecha     REFERENCES dw.dim_fecha (fecha_key),
    proveedor_key     INT           NOT NULL CONSTRAINT fk_fc_proveedor REFERENCES dw.dim_proveedor (proveedor_key),
    producto_key      INT           NOT NULL CONSTRAINT fk_fc_producto  REFERENCES dw.dim_producto (producto_key),
    estado            NVARCHAR(50)  NOT NULL,
    cantidad          DECIMAL(12,3) NOT NULL,
    costo_unitario    DECIMAL(12,2) NOT NULL,
    total             DECIMAL(14,2) NOT NULL
);

CREATE TABLE dw.fact_consumo_insumos (
    consumo_id        INT           NOT NULL CONSTRAINT pk_fact_consumo PRIMARY KEY,
    produccion_id     INT           NOT NULL,
    fecha_key         INT           NOT NULL CONSTRAINT fk_fci_fecha    REFERENCES dw.dim_fecha (fecha_key),
    producto_key      INT           NOT NULL CONSTRAINT fk_fci_producto REFERENCES dw.dim_producto (producto_key),
    cantidad          DECIMAL(12,3) NOT NULL
);

/* ------------------------------------------------------------ CONTROL */
CREATE TABLE dw.etl_log (
    id        INT IDENTITY(1,1) NOT NULL CONSTRAINT pk_etl_log PRIMARY KEY,
    proceso   NVARCHAR(100) NOT NULL,
    inicio    DATETIME2(3)  NOT NULL,
    fin       DATETIME2(3)  NULL,
    filas     INT           NULL,
    estado    NVARCHAR(20)  NOT NULL,     -- OK / ERROR
    mensaje   NVARCHAR(4000) NULL
);

CREATE TABLE dw.exp_resultados (
    id            INT IDENTITY(1,1) NOT NULL CONSTRAINT pk_exp_resultados PRIMARY KEY,
    plataforma    NVARCHAR(20)  NOT NULL,     -- sqlserver
    factor_escala INT           NOT NULL,
    filas_hecho   BIGINT        NOT NULL,
    consulta      NVARCHAR(10)  NOT NULL,     -- Q1..Q5
    repeticion    TINYINT       NOT NULL,     -- 0 = calentamiento, 1..3 = medidas
    ms            INT           NOT NULL,
    filas_result  INT           NOT NULL,
    fecha_hora    DATETIME2(0)  NOT NULL CONSTRAINT df_exp_fecha DEFAULT (SYSDATETIME())
);
GO
PRINT 'Esquema dw creado.';
