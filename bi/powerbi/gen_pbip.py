import json, os, shutil, uuid, hashlib, sys

ROOT = sys.argv[1]
NAME = 'Panaderia_Dashboards'
REP = f'{NAME}.Report'
SM = f'{NAME}.SemanticModel'
shutil.rmtree(ROOT, ignore_errors=True)
os.makedirs(ROOT)

S = 'https://developer.microsoft.com/json-schemas/fabric'


def w(path, obj):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8') as f:
        if isinstance(obj, str):
            f.write(obj)
        else:
            json.dump(obj, f, ensure_ascii=False, indent=2)


def hid(*parts):
    return hashlib.md5('|'.join(parts).encode()).hexdigest()[:20]


# =====================================================================
# PROJECT FILES
# =====================================================================
w(f'{NAME}.pbip', {
    "$schema": f"{S}/pbip/pbipProperties/1.0.0/schema.json",
    "version": "1.0",
    "artifacts": [{"report": {"path": REP}}],
    "settings": {"enableAutoRecovery": True}
})
w('.gitignore', "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")

w(f'{REP}/.platform', {
    "$schema": f"{S}/gitIntegration/platformProperties/2.0.0/schema.json",
    "metadata": {"type": "Report", "displayName": NAME},
    "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_DNS, 'rep.panaderia'))}
})
w(f'{SM}/.platform', {
    "$schema": f"{S}/gitIntegration/platformProperties/2.0.0/schema.json",
    "metadata": {"type": "SemanticModel", "displayName": NAME},
    "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_DNS, 'sm.panaderia'))}
})
w(f'{REP}/definition.pbir', {
    "$schema": f"{S}/item/report/definitionProperties/2.0.0/schema.json",
    "version": "4.0",
    "datasetReference": {"byPath": {"path": f"../{SM}"}}
})
w(f'{SM}/definition.pbism', {
    "$schema": f"{S}/item/semanticModel/definitionProperties/1.0.0/schema.json",
    "version": "4.0",
    "settings": {}
})

# =====================================================================
# SEMANTIC MODEL (model.bim / TMSL)
# =====================================================================
TYPES = {'int': ('int64', 'Int64.Type', '0'), 'money': ('decimal', 'Currency.Type', '"S/ "#,0.00'),
         'num': ('double', 'type number', '#,0.###'), 'text': ('string', 'type text', None),
         'date': ('dateTime', 'type date', 'dd/mm/yyyy'), 'datetime': ('dateTime', 'type datetime', 'dd/mm/yyyy hh:nn'),
         'bool': ('boolean', 'type logical', None)}

SRC = 'Origen = Sql.Database(ServidorSQL, BaseDatos)'


def nav(var, table):
    return f'{var} = Origen{{[Schema="dbo",Item="{table}"]}}[Data]'


def mtable(name, cols, steps, last, hidden_cols=(), measures=(), sort_by=None):
    """cols: list of (name, kind)"""
    typed = ', '.join('{"%s", %s}' % (c, TYPES[k][1]) for c, k in cols)
    lines = ['let', '    ' + SRC + ','] + ['    ' + s + ',' for s in steps] + \
            [f'    Tipos = Table.TransformColumnTypes({last}, {{{typed}}}),',
             f'    Final = Table.SelectColumns(Tipos, {{{", ".join(chr(34)+c+chr(34) for c, _ in cols)}}})',
             'in', '    Final']
    tcols = []
    for c, k in cols:
        d = {"name": c, "dataType": TYPES[k][0], "sourceColumn": c, "summarizeBy": "none"}
        if TYPES[k][2]:
            d["formatString"] = TYPES[k][2]
        if k in ('money', 'num') and c not in hidden_cols:
            d["summarizeBy"] = "sum"
        if c in hidden_cols:
            d["isHidden"] = True
        tcols.append(d)
    t = {"name": name, "columns": tcols,
         "partitions": [{"name": name, "mode": "import", "source": {"type": "m", "expression": lines}}]}
    if measures:
        t["measures"] = [dict(name=n, expression=e, **({"formatString": f} if f else {})) for n, e, f in measures]
    return t


MONEY = '"S/ "#,0.00'
PCT = '0.0%'
INT = '#,0'

tables = []

tables.append(mtable('Ventas',
    [('VentaID', 'int'), ('ClienteID', 'int'), ('FechaHora', 'datetime'), ('Fecha', 'date'), ('Hora', 'int'),
     ('Total', 'money'), ('MetodoPago', 'text'), ('Cliente', 'text'), ('Estado', 'text'),
     ('TipoComprobante', 'text'), ('Comprobante', 'text')],
    [nav('ventas', 'ventas'), nav('metodos', 'metodos_pago'), nav('clientes', 'clientes'),
     'Cols = Table.SelectColumns(ventas, {"id","cliente_id","fecha","total","metodo_pago_id","estado","tipo_comprobante","numero_comprobante"})',
     'JoinMP = Table.NestedJoin(Cols, {"metodo_pago_id"}, metodos, {"id"}, "mp", JoinKind.LeftOuter)',
     'ExpMP = Table.ExpandTableColumn(JoinMP, "mp", {"nombre"}, {"MetodoPago"})',
     'JoinCli = Table.NestedJoin(ExpMP, {"cliente_id"}, clientes, {"id"}, "cli", JoinKind.LeftOuter)',
     'ExpCli = Table.ExpandTableColumn(JoinCli, "cli", {"nombre"}, {"Cliente"})',
     'CliDef = Table.ReplaceValue(ExpCli, null, "Consumidor final", Replacer.ReplaceValue, {"Cliente"})',
     'Ren = Table.RenameColumns(CliDef, {{"id","VentaID"},{"cliente_id","ClienteID"},{"fecha","FechaHora"},{"total","Total"},{"estado","Estado"},{"tipo_comprobante","TipoComprobante"},{"numero_comprobante","Comprobante"}})',
     'AddFecha = Table.AddColumn(Ren, "Fecha", each if [FechaHora] = null then null else DateTime.Date([FechaHora]), type date)',
     'AddHora = Table.AddColumn(AddFecha, "Hora", each if [FechaHora] = null then null else Time.Hour([FechaHora]), Int64.Type)'],
    'AddHora', hidden_cols=('VentaID', 'ClienteID', 'Total'),
    measures=[
        ('Ventas Totales', 'CALCULATE(SUM(Ventas[Total]), Ventas[Estado] = "pagada")', MONEY),
        ('Nro Ventas', 'CALCULATE(COUNTROWS(Ventas), Ventas[Estado] = "pagada")', INT),
        ('Ticket Promedio', 'DIVIDE([Ventas Totales], [Nro Ventas])', MONEY),
        ('Ventas Anuladas', 'CALCULATE(COUNTROWS(Ventas), Ventas[Estado] = "anulada") + 0', INT),
        ('% Anulacion', 'DIVIDE([Ventas Anuladas], COUNTROWS(Ventas))', PCT),
    ]))

tables.append(mtable('DetalleVenta',
    [('DetalleID', 'int'), ('VentaID', 'int'), ('VarianteID', 'int'), ('Cantidad', 'num'),
     ('PrecioUnitario', 'money'), ('Descuento', 'money'), ('Importe', 'num')],
    [nav('items', 'items_venta'),
     'Cols = Table.SelectColumns(items, {"id","venta_id","variante_id","cantidad","precio_unitario","descuento"})',
     'Ren = Table.RenameColumns(Cols, {{"id","DetalleID"},{"venta_id","VentaID"},{"variante_id","VarianteID"},{"cantidad","Cantidad"},{"precio_unitario","PrecioUnitario"},{"descuento","Descuento"}})',
     'AddImp = Table.AddColumn(Ren, "Importe", each [Cantidad] * [PrecioUnitario] - [Descuento], type number)'],
    'AddImp', hidden_cols=('DetalleID', 'VentaID', 'VarianteID'),
    measures=[
        ('Unidades Vendidas', 'CALCULATE(SUM(DetalleVenta[Cantidad]), Ventas[Estado] = "pagada")', INT),
        ('Importe Vendido', 'CALCULATE(SUM(DetalleVenta[Importe]), Ventas[Estado] = "pagada")', MONEY),
    ]))

tables.append(mtable('Productos',
    [('VarianteID', 'int'), ('SKU', 'text'), ('Producto', 'text'), ('Variante', 'text'), ('Articulo', 'text'),
     ('Tipo', 'text'), ('Categoria', 'text'), ('PrecioVenta', 'money'), ('Stock', 'num'),
     ('StockMinimo', 'num'), ('Activo', 'bool'), ('EstadoStock', 'text')],
    [nav('variantes', 'variantes_producto'), nav('productos', 'productos'), nav('categorias', 'categorias'),
     'Cols = Table.SelectColumns(variantes, {"id","producto_id","sku","nombre","precio_venta","stock","stock_minimo","activo"})',
     'JoinP = Table.NestedJoin(Cols, {"producto_id"}, productos, {"id"}, "p", JoinKind.LeftOuter)',
     'ExpP = Table.ExpandTableColumn(JoinP, "p", {"nombre","tipo","categoria_id"}, {"Producto","Tipo","categoria_id"})',
     'JoinC = Table.NestedJoin(ExpP, {"categoria_id"}, categorias, {"id"}, "c", JoinKind.LeftOuter)',
     'ExpC = Table.ExpandTableColumn(JoinC, "c", {"nombre"}, {"Categoria"})',
     'Ren = Table.RenameColumns(ExpC, {{"id","VarianteID"},{"sku","SKU"},{"nombre","Variante"},{"precio_venta","PrecioVenta"},{"stock","Stock"},{"stock_minimo","StockMinimo"},{"activo","Activo"}})',
     'AddArt = Table.AddColumn(Ren, "Articulo", each if [Variante] = null or [Variante] = "" then [Producto] else [Producto] & " - " & [Variante], type text)',
     'AddEst = Table.AddColumn(AddArt, "EstadoStock", each if [Stock] < 0 then "Negativo" else if [Stock] < [StockMinimo] then "Bajo mínimo" else "OK", type text)'],
    'AddEst', hidden_cols=('VarianteID',),
    measures=[
        ('Nro Productos', 'COUNTROWS(Productos)', INT),
        ('Stock Actual', 'SUM(Productos[Stock])', '#,0.##'),
        ('Stock Minimo', 'SUM(Productos[StockMinimo])', '#,0.##'),
        ('Productos Bajo Minimo', 'CALCULATE(COUNTROWS(Productos), Productos[EstadoStock] = "Bajo mínimo") + 0', INT),
        ('Productos Stock Negativo', 'CALCULATE(COUNTROWS(Productos), Productos[EstadoStock] = "Negativo") + 0', INT),
    ]))

tables.append(mtable('Producciones',
    [('ProduccionID', 'int'), ('Referencia', 'text'), ('VarianteSalidaID', 'int'), ('CantidadProgramada', 'num'),
     ('CantidadObtenida', 'num'), ('MermaCantidad', 'num'), ('MotivoMerma', 'text'),
     ('FechaHora', 'datetime'), ('Fecha', 'date'), ('Estado', 'text')],
    [nav('prod', 'producciones'),
     'Cols = Table.SelectColumns(prod, {"id","referencia","variante_salida_id","cantidad_programada","cantidad_obtenida","merma_cantidad","merma_motivo","fecha","estado"})',
     'Ren = Table.RenameColumns(Cols, {{"id","ProduccionID"},{"referencia","Referencia"},{"variante_salida_id","VarianteSalidaID"},{"cantidad_programada","CantidadProgramada"},{"cantidad_obtenida","CantidadObtenida"},{"merma_cantidad","MermaCantidad"},{"merma_motivo","MotivoMerma"},{"fecha","FechaHora"},{"estado","Estado"}})',
     'MotDef = Table.ReplaceValue(Ren, null, "Sin motivo", Replacer.ReplaceValue, {"MotivoMerma"})',
     'AddFecha = Table.AddColumn(MotDef, "Fecha", each if [FechaHora] = null then null else DateTime.Date([FechaHora]), type date)'],
    'AddFecha', hidden_cols=('ProduccionID', 'VarianteSalidaID'),
    measures=[
        ('Ordenes Produccion', 'CALCULATE(COUNTROWS(Producciones), Producciones[Estado] = "finalizada")', INT),
        ('Unidades Programadas', 'CALCULATE(SUM(Producciones[CantidadProgramada]), Producciones[Estado] = "finalizada")', INT),
        ('Unidades Obtenidas', 'CALCULATE(SUM(Producciones[CantidadObtenida]), Producciones[Estado] = "finalizada")', INT),
        ('Merma Unidades', 'CALCULATE(SUM(Producciones[MermaCantidad]), Producciones[Estado] = "finalizada")', INT),
        ('% Merma', 'DIVIDE([Merma Unidades], [Unidades Programadas])', PCT),
    ]))

tables.append(mtable('ConsumoInsumos',
    [('ConsumoID', 'int'), ('ProduccionID', 'int'), ('VarianteID', 'int'), ('Cantidad', 'num'), ('Fecha', 'date')],
    [nav('cons', 'consumo_insumos'),
     'Cols = Table.SelectColumns(cons, {"id","produccion_id","variante_id","cantidad","fecha"})',
     'Ren = Table.RenameColumns(Cols, {{"id","ConsumoID"},{"produccion_id","ProduccionID"},{"variante_id","VarianteID"},{"cantidad","Cantidad"},{"fecha","FechaHora"}})',
     'AddFecha = Table.AddColumn(Ren, "Fecha", each if [FechaHora] = null then null else DateTime.Date([FechaHora]), type date)'],
    'AddFecha', hidden_cols=('ConsumoID', 'ProduccionID', 'VarianteID'),
    measures=[('Consumo Insumos', 'SUM(ConsumoInsumos[Cantidad])', '#,0.0')]))

tables.append(mtable('Compras',
    [('CompraID', 'int'), ('Proveedor', 'text'), ('Comprobante', 'text'), ('Fecha', 'date'),
     ('Total', 'money'), ('Estado', 'text')],
    [nav('compras', 'compras'), nav('prov', 'proveedores'),
     'Cols = Table.SelectColumns(compras, {"id","proveedor_id","numero_comprobante","fecha","total","estado"})',
     'JoinPr = Table.NestedJoin(Cols, {"proveedor_id"}, prov, {"id"}, "pr", JoinKind.LeftOuter)',
     'ExpPr = Table.ExpandTableColumn(JoinPr, "pr", {"nombre"}, {"Proveedor"})',
     'Ren = Table.RenameColumns(ExpPr, {{"id","CompraID"},{"numero_comprobante","Comprobante"},{"fecha","FechaHora"},{"total","Total"},{"estado","Estado"}})',
     'AddFecha = Table.AddColumn(Ren, "Fecha", each if [FechaHora] = null then null else DateTime.Date([FechaHora]), type date)'],
    'AddFecha', hidden_cols=('CompraID', 'Total'),
    measures=[
        ('Total Compras', 'CALCULATE(SUM(Compras[Total]), Compras[Estado] <> "anulada")', MONEY),
        ('Nro Compras', 'CALCULATE(COUNTROWS(Compras), Compras[Estado] <> "anulada")', INT),
        ('Proveedores Activos', 'CALCULATE(DISTINCTCOUNT(Compras[Proveedor]), Compras[Estado] <> "anulada")', INT),
    ]))

# Calendar (calculated table)
cal_expr = [
    'VAR Base = SELECTCOLUMNS(CALENDAR(DATE(2026, 1, 1), DATE(2026, 12, 31)), "Fecha", [Date])',
    'RETURN',
    'ADDCOLUMNS(Base,',
    '    "Anio", YEAR([Fecha]),',
    '    "MesNum", MONTH([Fecha]),',
    '    "Mes", SWITCH(MONTH([Fecha]), 1,"Ene", 2,"Feb", 3,"Mar", 4,"Abr", 5,"May", 6,"Jun", 7,"Jul", 8,"Ago", 9,"Set", 10,"Oct", 11,"Nov", 12,"Dic"),',
    '    "DiaSemanaNum", WEEKDAY([Fecha], 2),',
    '    "DiaSemana", SWITCH(WEEKDAY([Fecha], 2), 1,"Lun", 2,"Mar", 3,"Mié", 4,"Jue", 5,"Vie", 6,"Sáb", 7,"Dom")',
    ')']


def ccol(n, dt, fmt=None, hidden=False, sortby=None, key=False):
    d = {"type": "calculatedTableColumn", "name": n, "dataType": dt, "isNameInferred": True,
         "isDataTypeInferred": True, "sourceColumn": f"[{n}]", "summarizeBy": "none"}
    if fmt: d["formatString"] = fmt
    if hidden: d["isHidden"] = True
    if sortby: d["sortByColumn"] = sortby
    if key: d["isKey"] = True
    return d


tables.append({
    "name": "Calendario", "dataCategory": "Time",
    "columns": [ccol('Fecha', 'dateTime', 'dd/mm/yyyy', key=True), ccol('Anio', 'int64', '0'),
                ccol('MesNum', 'int64', '0', hidden=True), ccol('Mes', 'string', sortby='MesNum'),
                ccol('DiaSemanaNum', 'int64', '0', hidden=True), ccol('DiaSemana', 'string', sortby='DiaSemanaNum')],
    "partitions": [{"name": "Calendario", "mode": "import", "source": {"type": "calculated", "expression": cal_expr}}]
})


def rel(ft, fc, tt, tc):
    return {"name": hid('rel', ft, fc, tt, tc), "fromTable": ft, "fromColumn": fc, "toTable": tt, "toColumn": tc}


relationships = [
    rel('Ventas', 'Fecha', 'Calendario', 'Fecha'),
    rel('DetalleVenta', 'VentaID', 'Ventas', 'VentaID'),
    rel('DetalleVenta', 'VarianteID', 'Productos', 'VarianteID'),
    rel('Producciones', 'Fecha', 'Calendario', 'Fecha'),
    rel('Producciones', 'VarianteSalidaID', 'Productos', 'VarianteID'),
    rel('ConsumoInsumos', 'Fecha', 'Calendario', 'Fecha'),
    rel('ConsumoInsumos', 'VarianteID', 'Productos', 'VarianteID'),
    rel('Compras', 'Fecha', 'Calendario', 'Fecha'),
]

model = {
    "compatibilityLevel": 1567,
    "model": {
        "culture": "es-ES",
        "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
        "defaultPowerBIDataSourceVersion": "powerBI_V3",
        "sourceQueryCulture": "es-PE",
        "tables": tables,
        "relationships": relationships,
        "expressions": [
            {"name": "ServidorSQL", "kind": "m",
             "expression": '"localhost" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
             "description": "Nombre del servidor SQL Server (ej.: localhost, .\\SQLEXPRESS, MIPC\\SQLEXPRESS)"},
            {"name": "BaseDatos", "kind": "m",
             "expression": '"panaderia_db" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'}
        ],
        "annotations": [
            {"name": "PBI_QueryOrder", "value": json.dumps(['ServidorSQL', 'BaseDatos'] + [t['name'] for t in tables if t['name'] != 'Calendario'])},
            {"name": "__PBI_TimeIntelligenceEnabled", "value": "0"}
        ]
    }
}
w(f'{SM}/model.bim', model)

# =====================================================================
# REPORT (PBIR)
# =====================================================================
DEF = f'{REP}/definition'
w(f'{DEF}/version.json', {"$schema": f"{S}/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})

THEME_COLORS = ["#B5651D", "#E0A458", "#7B3F00", "#5C8D89", "#C1666B", "#D9B26F", "#4A6670", "#A8C69F"]
theme = {
    "name": "Panaderia",
    "dataColors": THEME_COLORS,
    "background": "#FFFFFF", "foreground": "#3B2A20", "tableAccent": "#B5651D",
    "good": "#5C8D89", "neutral": "#E0A458", "bad": "#C1666B",
    "visualStyles": {
        "page": {"*": {"background": [{"color": {"solid": {"color": "#FBF6EF"}}, "transparency": 0}]}},
        "*": {"*": {
            "background": [{"show": True, "color": {"solid": {"color": "#FFFFFF"}}, "transparency": 0}],
            "border": [{"show": True, "color": {"solid": {"color": "#EAD9C6"}}, "radius": 8}],
            "title": [{"fontColor": {"solid": {"color": "#7B3F00"}}, "fontSize": 12, "bold": True}]
        }},
        "card": {"*": {"labels": [{"color": {"solid": {"color": "#7B3F00"}}, "fontSize": 24}],
                       "categoryLabels": [{"color": {"solid": {"color": "#6B5B4E"}}, "fontSize": 11}]}}
    }
}
base_theme = dict(theme, name="CY24SU10")
w(f'{REP}/StaticResources/RegisteredResources/Panaderia.json', theme)
w(f'{REP}/StaticResources/SharedResources/BaseThemes/CY24SU10.json', base_theme)

w(f'{DEF}/report.json', {
    "$schema": f"{S}/item/report/definition/report/2.0.0/schema.json",
    "themeCollection": {
        "baseTheme": {"name": "CY24SU10", "reportVersionAtImport": "5.61", "type": "SharedResources"},
        "customTheme": {"name": "Panaderia.json", "reportVersionAtImport": "5.61", "type": "RegisteredResources"}
    },
    "resourcePackages": [
        {"name": "SharedResources", "type": "SharedResources",
         "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
        {"name": "RegisteredResources", "type": "RegisteredResources",
         "items": [{"name": "Panaderia.json", "path": "Panaderia.json", "type": "CustomTheme"}]}
    ],
    "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True,
                 "allowChangeFilterTypes": True, "useEnhancedTooltips": True}
})


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def C(e, p):
    return ('col', e, p)


def M(e, p):
    return ('mea', e, p)


def field(f):
    kind, e, p = f
    k = 'Column' if kind == 'col' else 'Measure'
    return {k: {"Expression": {"SourceRef": {"Entity": e}}, "Property": p}}


def proj(f, display=None):
    d = {"field": field(f), "queryRef": f"{f[1]}.{f[2]}", "nativeQueryRef": f[2]}
    if display:
        d["displayName"] = display
    return d


def visual(page, key, vtype, pos, roles=None, title=None, objects=None, sort=None, z=0):
    name = hid(page, key)
    v = {"visualType": vtype}
    if roles:
        qs = {}
        for role, fields in roles.items():
            qs[role] = {"projections": [proj(f) if isinstance(f, tuple) and len(f) == 3 else proj(*f) for f in fields]}
        v["query"] = {"queryState": qs}
        if sort:
            f, d = sort
            v["query"]["sortDefinition"] = {"sort": [{"field": field(f), "direction": d}], "isDefaultSort": False}
    if objects:
        v["objects"] = objects
    if title:
        v["visualContainerObjects"] = {"title": [{"properties": {"show": lit("true"), "text": lit("'%s'" % title.replace("'", "''"))}}]}
    x, y, wd, ht = pos
    obj = {"$schema": f"{S}/item/report/definition/visualContainer/2.0.0/schema.json",
           "name": name,
           "position": {"x": x, "y": y, "z": z, "width": wd, "height": ht, "tabOrder": z},
           "visual": v}
    w(f'{DEF}/pages/{page}/visuals/{name}/visual.json', obj)


def header(page, text, subtitle):
    name = hid(page, 'header')
    obj = {"$schema": f"{S}/item/report/definition/visualContainer/2.0.0/schema.json",
           "name": name,
           "position": {"x": 20, "y": 8, "z": 0, "width": 820, "height": 58, "tabOrder": 0},
           "visual": {"visualType": "textbox",
                      "objects": {"general": [{"properties": {"paragraphs": [
                          {"textRuns": [{"value": text, "textStyle": {"fontWeight": "bold", "fontSize": "20pt", "color": "#7B3F00"}}]},
                          {"textRuns": [{"value": subtitle, "textStyle": {"fontSize": "10pt", "color": "#6B5B4E"}}]}
                      ]}}]},
                      "visualContainerObjects": {"background": [{"properties": {"show": lit("false")}}],
                                                 "border": [{"properties": {"show": lit("false")}}]}}}
    w(f'{DEF}/pages/{page}/visuals/{name}/visual.json', obj)


DROPDOWN = {"data": [{"properties": {"mode": lit("'Dropdown'")}}]}
LABELS_ON = {"labels": [{"properties": {"show": lit("true")}}]}
CARD_FMT = {"labels": [{"properties": {"labelDisplayUnits": lit("1D")}}]}


def slicers(page, f1, f2):
    visual(page, 's1', 'slicer', (870, 8, 190, 58), {"Values": [f1]}, objects=DROPDOWN, z=1)
    visual(page, 's2', 'slicer', (1070, 8, 190, 58), {"Values": [f2]}, objects=DROPDOWN, z=2)


def cards(page, measures):
    wd = (1240 - 10 * (len(measures) - 1)) / len(measures)
    for i, m in enumerate(measures):
        visual(page, f'card{i}', 'card', (20 + i * (wd + 10), 76, wd, 96), {"Values": [m]}, objects=CARD_FMT, z=10 + i)


pages = []

# ---------------- PAGE 1: VENTAS
P = 'pag_ventas'
pages.append((P, 'Ventas'))
header(P, 'Panadería · Dashboard de Ventas', 'Ventas pagadas, tickets, medios de pago y productos más vendidos')
slicers(P, C('Calendario', 'Mes'), C('Ventas', 'MetodoPago'))
cards(P, [M('Ventas', 'Ventas Totales'), M('Ventas', 'Nro Ventas'), M('Ventas', 'Ticket Promedio'),
          M('DetalleVenta', 'Unidades Vendidas'), M('Ventas', '% Anulacion')])
visual(P, 'v_mes', 'clusteredColumnChart', (20, 184, 610, 258),
       {"Category": [C('Calendario', 'Mes')], "Y": [M('Ventas', 'Ventas Totales')]},
       'Ventas por mes', LABELS_ON, sort=(C('Calendario', 'Mes'), 'Ascending'), z=20)
visual(P, 'v_mp', 'donutChart', (640, 184, 300, 258),
       {"Category": [C('Ventas', 'MetodoPago')], "Y": [M('Ventas', 'Ventas Totales')]},
       'Ventas por método de pago', z=21)
visual(P, 'v_dow', 'clusteredColumnChart', (950, 184, 310, 258),
       {"Category": [C('Calendario', 'DiaSemana')], "Y": [M('Ventas', 'Ventas Totales')]},
       'Ventas por día de la semana', sort=(C('Calendario', 'DiaSemana'), 'Ascending'), z=22)
visual(P, 'v_dia', 'lineChart', (20, 452, 610, 258),
       {"Category": [C('Calendario', 'Fecha')], "Y": [M('Ventas', 'Ventas Totales')]},
       'Ventas diarias', sort=(C('Calendario', 'Fecha'), 'Ascending'), z=23)
visual(P, 'v_top', 'clusteredBarChart', (640, 452, 300, 258),
       {"Category": [C('Productos', 'Articulo')], "Y": [M('DetalleVenta', 'Importe Vendido')]},
       'Productos más vendidos (S/)', LABELS_ON, sort=(M('DetalleVenta', 'Importe Vendido'), 'Descending'), z=24)
visual(P, 'v_hora', 'clusteredColumnChart', (950, 452, 310, 258),
       {"Category": [C('Ventas', 'Hora')], "Y": [M('Ventas', 'Nro Ventas')]},
       'Nro de ventas por hora', sort=(C('Ventas', 'Hora'), 'Ascending'), z=25)

# ---------------- PAGE 2: PRODUCCION
P = 'pag_produccion'
pages.append((P, 'Producción y merma'))
header(P, 'Panadería · Producción y Merma', 'Órdenes finalizadas, unidades obtenidas y pérdidas de proceso')
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

# ---------------- PAGE 3: INVENTARIO Y COMPRAS
P = 'pag_inventario'
pages.append((P, 'Inventario y compras'))
header(P, 'Panadería · Inventario y Compras', 'Compras a proveedores, consumo de insumos y estado del stock')
slicers(P, C('Calendario', 'Mes'), C('Productos', 'Tipo'))
cards(P, [M('Compras', 'Total Compras'), M('Compras', 'Nro Compras'), M('Compras', 'Proveedores Activos'),
          M('Productos', 'Productos Bajo Minimo'), M('Productos', 'Productos Stock Negativo')])
visual(P, 'i_prov', 'clusteredBarChart', (20, 184, 400, 258),
       {"Category": [C('Compras', 'Proveedor')], "Y": [M('Compras', 'Total Compras')]},
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

for name, disp in pages:
    w(f'{DEF}/pages/{name}/page.json', {
        "$schema": f"{S}/item/report/definition/page/2.0.0/schema.json",
        "name": name, "displayName": disp, "displayOption": "FitToPage", "height": 720, "width": 1280})
w(f'{DEF}/pages/pages.json', {
    "$schema": f"{S}/item/report/definition/pagesMetadata/1.0.0/schema.json",
    "pageOrder": [p for p, _ in pages], "activePageName": pages[0][0]})
print('ok')
