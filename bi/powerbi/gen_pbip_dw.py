"""Genera el proyecto Power BI (.pbip) conectado al data warehouse (esquema dw).
Reutiliza las utilidades de gen_pbip.py (archivos de proyecto, tema y visuales)."""
import os, sys

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gen_pbip.py'), encoding='utf-8').read()
cut = lambda a: src.index(a)
PARTE_A = src[:cut('tables = []')]
PARTE_B = src[cut('model = {'):cut('pages = []')]
PARTE_C = src[cut('for name, disp in pages:'):]

exec(PARTE_A)   # ROOT, w(), hid(), project files, TYPES, mtable(), ...


def dwtable(name, item, mapping, hidden=(), measures=()):
    """mapping: list of (columna_dw, nombre_final, tipo)"""
    sel = ', '.join(f'"{s}"' for s, _, _ in mapping)
    ren = ', '.join('{"%s","%s"}' % (s, d) for s, d, _ in mapping if s != d)
    steps = [f'T = Origen{{[Schema="dw",Item="{item}"]}}[Data]',
             f'Sel = Table.SelectColumns(T, {{{sel}}})']
    last = 'Sel'
    if ren:
        steps.append(f'Ren = Table.RenameColumns(Sel, {{{ren}}})')
        last = 'Ren'
    return mtable(name, [(d, k) for _, d, k in mapping], steps, last, hidden_cols=hidden, measures=measures)


MONEY = '"S/ "#,0.00'; PCT = '0.0%'; INT = '#,0'
tables = []

cal = dwtable('Calendario', 'dim_fecha',
              [('fecha_key', 'fecha_key', 'int'), ('fecha', 'Fecha', 'date'), ('anio', 'Anio', 'int'),
               ('mes_num', 'MesNum', 'int'), ('mes', 'Mes', 'text'),
               ('dia_semana_num', 'DiaSemanaNum', 'int'), ('dia_semana', 'DiaSemana', 'text')],
              hidden=('fecha_key', 'MesNum', 'DiaSemanaNum'))
for c in cal['columns']:
    if c['name'] == 'Mes': c['sortByColumn'] = 'MesNum'
    if c['name'] == 'DiaSemana': c['sortByColumn'] = 'DiaSemanaNum'
tables.append(cal)

tables.append(dwtable('Productos', 'dim_producto',
    [('producto_key', 'producto_key', 'int'), ('sku', 'SKU', 'text'), ('producto', 'Producto', 'text'),
     ('variante', 'Variante', 'text'), ('articulo', 'Articulo', 'text'), ('tipo', 'Tipo', 'text'),
     ('categoria', 'Categoria', 'text'), ('unidad', 'Unidad', 'text'), ('precio_venta', 'PrecioVenta', 'money'),
     ('stock', 'Stock', 'num'), ('stock_minimo', 'StockMinimo', 'num'), ('estado_stock', 'EstadoStock', 'text'),
     ('activo', 'Activo', 'bool')],
    hidden=('producto_key',),
    measures=[
        ('Nro Productos', 'COUNTROWS(Productos)', INT),
        ('Stock Actual', 'SUM(Productos[Stock])', '#,0.##'),
        ('Stock Minimo', 'SUM(Productos[StockMinimo])', '#,0.##'),
        ('Productos Bajo Minimo', 'CALCULATE(COUNTROWS(Productos), Productos[EstadoStock] = "Bajo mínimo") + 0', INT),
        ('Productos Stock Negativo', 'CALCULATE(COUNTROWS(Productos), Productos[EstadoStock] = "Negativo") + 0', INT)]))

tables.append(dwtable('Clientes', 'dim_cliente',
    [('cliente_key', 'cliente_key', 'int'), ('nombre', 'Cliente', 'text'), ('tipo_cliente', 'TipoCliente', 'text')],
    hidden=('cliente_key',)))
tables.append(dwtable('MetodoPago', 'dim_metodo_pago',
    [('metodo_pago_key', 'metodo_pago_key', 'int'), ('metodo_pago', 'MetodoPago', 'text')],
    hidden=('metodo_pago_key',)))
tables.append(dwtable('Proveedores', 'dim_proveedor',
    [('proveedor_key', 'proveedor_key', 'int'), ('proveedor', 'Proveedor', 'text')],
    hidden=('proveedor_key',)))

tables.append(dwtable('Ventas', 'fact_ventas',
    [('item_venta_id', 'item_venta_id', 'int'), ('venta_id', 'venta_id', 'int'), ('fecha_key', 'fecha_key', 'int'),
     ('hora', 'Hora', 'int'), ('producto_key', 'producto_key', 'int'), ('cliente_key', 'cliente_key', 'int'),
     ('metodo_pago_key', 'metodo_pago_key', 'int'), ('tipo_comprobante', 'TipoComprobante', 'text'),
     ('estado', 'Estado', 'text'), ('cantidad', 'Cantidad', 'num'), ('precio_unitario', 'PrecioUnitario', 'money'),
     ('descuento', 'Descuento', 'money'), ('importe', 'Importe', 'money')],
    hidden=('item_venta_id', 'venta_id', 'fecha_key', 'producto_key', 'cliente_key', 'metodo_pago_key', 'Importe'),
    measures=[
        ('Ventas Totales', 'CALCULATE(SUM(Ventas[Importe]), Ventas[Estado] = "pagada")', MONEY),
        ('Nro Ventas', 'CALCULATE(DISTINCTCOUNT(Ventas[venta_id]), Ventas[Estado] = "pagada")', INT),
        ('Ticket Promedio', 'DIVIDE([Ventas Totales], [Nro Ventas])', MONEY),
        ('Unidades Vendidas', 'CALCULATE(SUM(Ventas[Cantidad]), Ventas[Estado] = "pagada")', INT),
        ('Ventas Anuladas', 'CALCULATE(DISTINCTCOUNT(Ventas[venta_id]), Ventas[Estado] = "anulada") + 0', INT),
        ('% Anulacion', 'DIVIDE([Ventas Anuladas], DISTINCTCOUNT(Ventas[venta_id]))', PCT)]))

tables.append(dwtable('Producciones', 'fact_produccion',
    [('produccion_id', 'produccion_id', 'int'), ('referencia', 'Referencia', 'text'), ('fecha_key', 'fecha_key', 'int'),
     ('producto_key', 'producto_key', 'int'), ('cantidad_programada', 'CantidadProgramada', 'num'),
     ('cantidad_obtenida', 'CantidadObtenida', 'num'), ('merma_cantidad', 'MermaCantidad', 'num'),
     ('motivo_merma', 'MotivoMerma', 'text'), ('estado', 'Estado', 'text')],
    hidden=('produccion_id', 'fecha_key', 'producto_key'),
    measures=[
        ('Ordenes Produccion', 'CALCULATE(COUNTROWS(Producciones), Producciones[Estado] = "finalizada")', INT),
        ('Unidades Programadas', 'CALCULATE(SUM(Producciones[CantidadProgramada]), Producciones[Estado] = "finalizada")', INT),
        ('Unidades Obtenidas', 'CALCULATE(SUM(Producciones[CantidadObtenida]), Producciones[Estado] = "finalizada")', INT),
        ('Merma Unidades', 'CALCULATE(SUM(Producciones[MermaCantidad]), Producciones[Estado] = "finalizada")', INT),
        ('% Merma', 'DIVIDE([Merma Unidades], [Unidades Programadas])', PCT)]))

tables.append(dwtable('Compras', 'fact_compras',
    [('item_compra_id', 'item_compra_id', 'int'), ('compra_id', 'compra_id', 'int'),
     ('numero_comprobante', 'Comprobante', 'text'), ('fecha_key', 'fecha_key', 'int'),
     ('proveedor_key', 'proveedor_key', 'int'), ('producto_key', 'producto_key', 'int'), ('estado', 'Estado', 'text'),
     ('cantidad', 'Cantidad', 'num'), ('costo_unitario', 'CostoUnitario', 'money'), ('total', 'Total', 'money')],
    hidden=('item_compra_id', 'compra_id', 'fecha_key', 'proveedor_key', 'producto_key', 'Total'),
    measures=[
        ('Total Compras', 'CALCULATE(SUM(Compras[Total]), Compras[Estado] <> "anulada")', MONEY),
        ('Nro Compras', 'CALCULATE(DISTINCTCOUNT(Compras[compra_id]), Compras[Estado] <> "anulada")', INT),
        ('Proveedores Activos', 'CALCULATE(DISTINCTCOUNT(Compras[proveedor_key]), Compras[Estado] <> "anulada")', INT)]))

tables.append(dwtable('ConsumoInsumos', 'fact_consumo_insumos',
    [('consumo_id', 'consumo_id', 'int'), ('produccion_id', 'produccion_id', 'int'), ('fecha_key', 'fecha_key', 'int'),
     ('producto_key', 'producto_key', 'int'), ('cantidad', 'Cantidad', 'num')],
    hidden=('consumo_id', 'produccion_id', 'fecha_key', 'producto_key'),
    measures=[('Consumo Insumos', 'SUM(ConsumoInsumos[Cantidad])', '#,0.0')]))


def rel(ft, fc, tt, tc):
    return {"name": hid('rel', ft, fc, tt, tc), "fromTable": ft, "fromColumn": fc, "toTable": tt, "toColumn": tc}


relationships = [
    rel('Ventas', 'fecha_key', 'Calendario', 'fecha_key'),
    rel('Ventas', 'producto_key', 'Productos', 'producto_key'),
    rel('Ventas', 'cliente_key', 'Clientes', 'cliente_key'),
    rel('Ventas', 'metodo_pago_key', 'MetodoPago', 'metodo_pago_key'),
    rel('Producciones', 'fecha_key', 'Calendario', 'fecha_key'),
    rel('Producciones', 'producto_key', 'Productos', 'producto_key'),
    rel('Compras', 'fecha_key', 'Calendario', 'fecha_key'),
    rel('Compras', 'proveedor_key', 'Proveedores', 'proveedor_key'),
    rel('Compras', 'producto_key', 'Productos', 'producto_key'),
    rel('ConsumoInsumos', 'fecha_key', 'Calendario', 'fecha_key'),
    rel('ConsumoInsumos', 'producto_key', 'Productos', 'producto_key'),
]

exec(PARTE_B)   # model.bim + report.json, theme and visual helpers

pages = []
P = 'pag_ventas'
pages.append((P, 'Ventas'))
header(P, 'Panadería Chapala · Dashboard de Ventas', 'Fuente: data warehouse (dw.fact_ventas) · ventas pagadas por línea de detalle')
slicers(P, C('Calendario', 'Mes'), C('MetodoPago', 'MetodoPago'))
cards(P, [M('Ventas', 'Ventas Totales'), M('Ventas', 'Nro Ventas'), M('Ventas', 'Ticket Promedio'),
          M('Ventas', 'Unidades Vendidas'), M('Ventas', '% Anulacion')])
visual(P, 'v_mes', 'clusteredColumnChart', (20, 184, 610, 258),
       {"Category": [C('Calendario', 'Mes')], "Y": [M('Ventas', 'Ventas Totales')]},
       'Ventas por mes', LABELS_ON, sort=(C('Calendario', 'Mes'), 'Ascending'), z=20)
visual(P, 'v_mp', 'donutChart', (640, 184, 300, 258),
       {"Category": [C('MetodoPago', 'MetodoPago')], "Y": [M('Ventas', 'Ventas Totales')]},
       'Ventas por método de pago', z=21)
visual(P, 'v_dow', 'clusteredColumnChart', (950, 184, 310, 258),
       {"Category": [C('Calendario', 'DiaSemana')], "Y": [M('Ventas', 'Ventas Totales')]},
       'Ventas por día de la semana', sort=(C('Calendario', 'DiaSemana'), 'Ascending'), z=22)
visual(P, 'v_dia', 'lineChart', (20, 452, 610, 258),
       {"Category": [C('Calendario', 'Fecha')], "Y": [M('Ventas', 'Ventas Totales')]},
       'Ventas diarias', sort=(C('Calendario', 'Fecha'), 'Ascending'), z=23)
visual(P, 'v_top', 'clusteredBarChart', (640, 452, 300, 258),
       {"Category": [C('Productos', 'Articulo')], "Y": [M('Ventas', 'Ventas Totales')]},
       'Productos más vendidos (S/)', LABELS_ON, sort=(M('Ventas', 'Ventas Totales'), 'Descending'), z=24)
visual(P, 'v_hora', 'clusteredColumnChart', (950, 452, 310, 258),
       {"Category": [C('Ventas', 'Hora')], "Y": [M('Ventas', 'Nro Ventas')]},
       'Nro de ventas por hora', sort=(C('Ventas', 'Hora'), 'Ascending'), z=25)

P = 'pag_produccion'
pages.append((P, 'Producción y merma'))
header(P, 'Panadería Chapala · Producción y Merma', 'Fuente: dw.fact_produccion · órdenes finalizadas')
slicers(P, C('Calendario', 'Mes'), C('Productos', 'Articulo'))
cards(P, [M('Producciones', 'Ordenes Produccion'), M('Producciones', 'Unidades Programadas'),
          M('Producciones', 'Unidades Obtenidas'), M('Producciones', 'Merma Unidades'), M('Producciones', '% Merma')])
visual(P, 'p_prod', 'clusteredColumnChart', (20, 184, 610, 258),
       {"Category": [C('Productos', 'Articulo')],
        "Y": [M('Producciones', 'Unidades Obtenidas'), M('Producciones', 'Merma Unidades')]},
       'Unidades obtenidas vs. merma por producto', z=20)
visual(P, 'p_mes', 'lineChart', (640, 184, 620, 258),
       {"Category": [C('Calendario', 'Mes')], "Y": [M('Producciones', '% Merma')]},
       '% de merma por mes', LABELS_ON, sort=(C('Calendario', 'Mes'), 'Ascending'), z=21)
visual(P, 'p_mot', 'clusteredBarChart', (20, 452, 480, 258),
       {"Category": [C('Producciones', 'MotivoMerma')], "Y": [M('Producciones', 'Merma Unidades')]},
       'Merma por motivo', LABELS_ON, sort=(M('Producciones', 'Merma Unidades'), 'Descending'), z=22)
visual(P, 'p_tab', 'tableEx', (510, 452, 750, 258),
       {"Values": [(C('Productos', 'Articulo'), 'Producto'), M('Producciones', 'Ordenes Produccion'),
                   M('Producciones', 'Unidades Programadas'), M('Producciones', 'Unidades Obtenidas'),
                   M('Producciones', 'Merma Unidades'), M('Producciones', '% Merma')]},
       'Detalle por producto', z=23)

P = 'pag_inventario'
pages.append((P, 'Inventario y compras'))
header(P, 'Panadería Chapala · Inventario y Compras', 'Fuente: dw.fact_compras, dw.fact_consumo_insumos y dw.dim_producto')
slicers(P, C('Calendario', 'Mes'), C('Productos', 'Tipo'))
cards(P, [M('Compras', 'Total Compras'), M('Compras', 'Nro Compras'), M('Compras', 'Proveedores Activos'),
          M('Productos', 'Productos Bajo Minimo'), M('Productos', 'Productos Stock Negativo')])
visual(P, 'i_prov', 'clusteredBarChart', (20, 184, 400, 258),
       {"Category": [C('Proveedores', 'Proveedor')], "Y": [M('Compras', 'Total Compras')]},
       'Compras por proveedor', LABELS_ON, sort=(M('Compras', 'Total Compras'), 'Descending'), z=20)
visual(P, 'i_mes', 'clusteredColumnChart', (430, 184, 400, 258),
       {"Category": [C('Calendario', 'Mes')], "Y": [M('Compras', 'Total Compras')]},
       'Compras por mes', LABELS_ON, sort=(C('Calendario', 'Mes'), 'Ascending'), z=21)
visual(P, 'i_cons', 'clusteredBarChart', (840, 184, 420, 258),
       {"Category": [C('Productos', 'Articulo')], "Y": [M('ConsumoInsumos', 'Consumo Insumos')]},
       'Consumo de insumos en producción', LABELS_ON, sort=(M('ConsumoInsumos', 'Consumo Insumos'), 'Descending'), z=22)
visual(P, 'i_tab', 'tableEx', (20, 452, 820, 258),
       {"Values": [(C('Productos', 'Articulo'), 'Producto'), C('Productos', 'Tipo'), C('Productos', 'Categoria'),
                   M('Productos', 'Stock Actual'), M('Productos', 'Stock Minimo'),
                   (C('Productos', 'EstadoStock'), 'Estado')]},
       'Stock actual por producto', sort=(M('Productos', 'Stock Actual'), 'Ascending'), z=23)
visual(P, 'i_est', 'donutChart', (850, 452, 410, 258),
       {"Category": [C('Productos', 'EstadoStock')], "Y": [M('Productos', 'Nro Productos')]},
       'Productos por estado de stock', z=24)

exec(PARTE_C)

# Orden de consultas: incluir todas las tablas (aquí Calendario también es una consulta M)
import json as _json
_p = os.path.join(ROOT, f'{SM}/model.bim')
_m = _json.load(open(_p, encoding='utf-8'))
for _a in _m['model']['annotations']:
    if _a['name'] == 'PBI_QueryOrder':
        _a['value'] = _json.dumps(['ServidorSQL', 'BaseDatos'] + [t['name'] for t in _m['model']['tables']])
_json.dump(_m, open(_p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
