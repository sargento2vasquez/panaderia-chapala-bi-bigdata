"""Analiza el experimento: compara tiempos de SQL Server vs Spark por consulta y factor de escala.

Entradas (en experimento/resultados/):
  sqlserver_resultados.csv  exportado de dw.exp_resultados (con o sin encabezado)
  spark_resultados.csv      generado por bigdata/run_pipeline.py --etapas experimento
Salidas:
  resumen_experimento.csv   promedio, mínimo, máximo y desviación por plataforma/escala/consulta
  resumen_experimento.md    tabla lista para pegar en el informe
  tiempos_por_consulta.png  gráfico de líneas (ms vs filas) por consulta

Uso:  python experimento/analizar_resultados.py
"""
from pathlib import Path

import pandas as pd

DIR = Path(__file__).resolve().parent / "resultados"
COLS = ["plataforma", "factor_escala", "filas_hecho", "consulta", "repeticion", "ms", "filas_result"]


def leer(nombre):
    ruta = DIR / nombre
    if not ruta.exists():
        print(f"(falta {ruta.name}, se omite)")
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(ruta, header=None)
    if str(df.iloc[0, 0]).strip().lower() == "plataforma":      # tiene encabezado
        df = pd.read_csv(ruta)
    else:
        df.columns = COLS
    return df[COLS]


def main():
    datos = pd.concat([leer("sqlserver_resultados.csv"), leer("spark_resultados.csv")], ignore_index=True)
    if datos.empty:
        raise SystemExit("No hay resultados. Ejecute primero el experimento en ambas plataformas.")
    for c in ["factor_escala", "filas_hecho", "repeticion", "ms", "filas_result"]:
        datos[c] = pd.to_numeric(datos[c])

    medidas = datos[datos.repeticion > 0]                       # se descarta el calentamiento
    resumen = (medidas.groupby(["plataforma", "factor_escala", "filas_hecho", "consulta"])
               .agg(ms_promedio=("ms", "mean"), ms_min=("ms", "min"), ms_max=("ms", "max"),
                    ms_desv=("ms", "std"), filas_result=("filas_result", "max"))
               .round(1).reset_index())
    resumen.to_csv(DIR / "resumen_experimento.csv", index=False)

    # Tabla comparativa: una fila por escala y consulta, una columna por plataforma
    pivote = resumen.pivot_table(index=["factor_escala", "filas_hecho", "consulta"],
                                 columns="plataforma", values="ms_promedio").reset_index()
    if {"sqlserver", "spark"} <= set(pivote.columns):
        pivote["spark/sqlserver"] = (pivote["spark"] / pivote["sqlserver"]).round(2)
    try:
        tabla_md = pivote.to_markdown(index=False)          # requiere el paquete tabulate
    except ImportError:
        tabla_md = pivote.to_string(index=False)
    (DIR / "resumen_experimento.md").write_text(tabla_md, encoding="utf-8")
    print(pivote.to_string(index=False))

    # Verificación: ambas plataformas devuelven el mismo número de filas por consulta
    chequeo = resumen.pivot_table(index=["factor_escala", "consulta"], columns="plataforma",
                                  values="filas_result")
    if chequeo.shape[1] > 1 and (chequeo.nunique(axis=1) > 1).any():
        print("ATENCIÓN: hay consultas con distinto número de filas entre plataformas:\n", chequeo)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib no está instalado: se omite el gráfico")
        return
    consultas = sorted(resumen.consulta.unique())
    fig, ejes = plt.subplots(1, len(consultas), figsize=(4 * len(consultas), 3.6), sharey=False)
    ejes = [ejes] if len(consultas) == 1 else ejes
    for ax, q in zip(ejes, consultas):
        for plat, g in resumen[resumen.consulta == q].groupby("plataforma"):
            g = g.sort_values("filas_hecho")
            ax.plot(g.filas_hecho, g.ms_promedio, marker="o", label=plat)
        ax.set_title(q)
        ax.set_xlabel("filas en fact_ventas")
        ax.set_ylabel("ms (promedio)")
        ax.grid(alpha=0.3)
    ejes[0].legend()
    fig.suptitle("Tiempo de respuesta por consulta: SQL Server vs Spark")
    fig.tight_layout()
    fig.savefig(DIR / "tiempos_por_consulta.png", dpi=150)
    print(f"Gráfico: {DIR / 'tiempos_por_consulta.png'}")


if __name__ == "__main__":
    main()
