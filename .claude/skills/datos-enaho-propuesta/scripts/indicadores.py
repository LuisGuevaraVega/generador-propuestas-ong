"""Indicadores de la ENAHO por departamento para la sección «problema» de una propuesta.

Uso:
    python .claude/skills/datos-enaho-propuesta/scripts/indicadores.py --codigo 966 --anio 2024

Lee los módulos 34 (sumaria), 02 (miembros) y 05 (empleo e ingresos) de datos/enaho/,
calcula indicadores ponderados por departamento y para el total nacional, los valida
contra las cifras oficiales del INEI y guarda:
    data/enaho/indicadores_<anio>.csv
    data/enaho/validacion_<anio>.txt
Si la validación falla, no guarda la tabla y termina con error.
"""
import argparse
import sys
import zipfile
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[4]
SKILL = Path(__file__).resolve().parents[1]
LLAVES_HOGAR = ["conglome", "vivienda", "hogar"]
EDAD_JOVEN = (18, 29)
TOLERANCIA = 0.15  # puntos porcentuales frente a la cifra oficial

NOMBRES = {"01": "Amazonas", "02": "Áncash", "03": "Apurímac", "04": "Arequipa", "05": "Ayacucho", "06": "Cajamarca",
           "07": "Callao", "08": "Cusco", "09": "Huancavelica", "10": "Huánuco", "11": "Ica", "12": "Junín",
           "13": "La Libertad", "14": "Lambayeque", "15": "Lima", "16": "Loreto", "17": "Madre de Dios",
           "18": "Moquegua", "19": "Pasco", "20": "Piura", "21": "Puno", "22": "San Martín", "23": "Tacna",
           "24": "Tumbes", "25": "Ucayali"}

INGRESO_LABORAL = ["i524a1", "d529t", "i530a", "d536", "i538a1", "d540t", "i541a", "d543", "d544t"]


def leer(datos: Path, codigo: str, modulo: str, patron: str, columnas):
    """Extrae el .dta del zip (una vez) y lo lee solo con las columnas pedidas."""
    zip_ruta = datos / f"{codigo}-Modulo{modulo}.zip"
    if not zip_ruta.exists():
        sys.exit(f"Falta {zip_ruta}. Bájalo de https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/"
                 f"{codigo}-Modulo{modulo}.zip y ponlo en {datos}/")
    with zipfile.ZipFile(zip_ruta) as z:
        nombre = next(n for n in z.namelist() if n.lower().endswith(".dta") and patron in n.lower())
        destino = datos / nombre
        if not destino.exists():
            z.extract(nombre, datos)
    # Se lee por trozos y solo con las columnas útiles: el módulo 05 pesa ~190 MB.
    partes = []
    with pd.read_stata(destino, convert_categoricals=False, chunksize=40000) as lector:
        for trozo in lector:
            trozo.columns = [c.lower() for c in trozo.columns]
            partes.append(trozo[[c for c in columnas if c in trozo.columns]])
    datos_df = pd.concat(partes, ignore_index=True)
    for llave in LLAVES_HOGAR + ["codperso", "ubigeo"]:
        if llave in datos_df:
            datos_df[llave] = datos_df[llave].astype(str).str.strip()
    return datos_df


def ponderado(valor, peso):
    peso = peso.fillna(0)
    return float((valor * peso).sum() / peso.sum()) if peso.sum() else float("nan")


def por_departamento(df, funcion):
    filas = {dep: funcion(g) for dep, g in df.groupby("departamento")}
    filas["00"] = funcion(df)
    return pd.Series(filas)


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--codigo", default="966", help="Código INEI de la ENAHO (966 = 2024)")
    args.add_argument("--anio", default="2024")
    args.add_argument("--datos", default=str(RAIZ / "datos" / "enaho"))
    args.add_argument("--salida", default=str(RAIZ / "data" / "enaho"))
    a = args.parse_args()
    datos, salida = Path(a.datos), Path(a.salida)

    # 1. Hogares (sumaria): pobreza monetaria con factor07 × mieperho
    hogares = leer(datos, a.codigo, "34", "sumaria", LLAVES_HOGAR + ["ubigeo", "pobreza", "mieperho", "factor07"])
    hogares = hogares[~hogares["ubigeo"].str.contains("sumaria-", na=False)]
    hogares["departamento"] = hogares["ubigeo"].str.zfill(6).str[:2]
    hogares["pobre"] = (hogares["pobreza"] <= 2).astype(float)
    hogares["peso_personas"] = hogares["factor07"] * hogares["mieperho"]
    assert not hogares.duplicated(LLAVES_HOGAR).any(), "Llaves de hogar duplicadas en la sumaria"
    pobreza = por_departamento(hogares, lambda g: ponderado(g["pobre"], g["peso_personas"]) * 100)

    # 2. Personas (módulo 02): residentes habituales, unidas a su hogar
    personas = leer(datos, a.codigo, "02", "200", LLAVES_HOGAR + ["codperso", "p204", "p205", "p206", "p208a", "facpob07"])
    residentes = ((personas["p204"] == 1) & (personas["p205"] == 2)) | ((personas["p204"] == 2) & (personas["p206"] == 1))
    personas = personas[residentes]
    filas_antes = len(personas)
    personas = personas.merge(hogares[LLAVES_HOGAR + ["departamento", "pobre"]], on=LLAVES_HOGAR, how="left",
                              validate="m:1")
    assert len(personas) == filas_antes, "La unión personas-hogares cambió el número de filas"
    jovenes = personas[personas["p208a"].between(*EDAD_JOVEN)]
    pobreza_jov = por_departamento(jovenes, lambda g: ponderado(g["pobre"], g["facpob07"]) * 100)
    poblacion_jov = por_departamento(jovenes, lambda g: float(g["facpob07"].sum()))

    # 3. Empleo e ingresos (módulo 05): jóvenes de 18 a 29 años
    empleo = leer(datos, a.codigo, "05", "500",
                  LLAVES_HOGAR + ["codperso", "ubigeo", "p208a", "ocu500", "p558a5", "fac500a"] + INGRESO_LABORAL)
    empleo["departamento"] = empleo["ubigeo"].str.zfill(6).str[:2]
    emp_jov = empleo[empleo["p208a"].between(*EDAD_JOVEN)].copy()
    pea = emp_jov[emp_jov["ocu500"].isin([1, 2])]
    ocupados = emp_jov[emp_jov["ocu500"] == 1].copy()
    ocupados["sin_pension"] = (ocupados["p558a5"] == 5).astype(float)
    ocupados["ingreso_mensual"] = ocupados[INGRESO_LABORAL].fillna(0).sum(axis=1) / 12
    desempleo = por_departamento(pea, lambda g: ponderado((g["ocu500"] == 2).astype(float), g["fac500a"]) * 100)
    sin_pension = por_departamento(ocupados, lambda g: ponderado(g["sin_pension"], g["fac500a"]) * 100)
    ingreso = por_departamento(ocupados, lambda g: ponderado(g["ingreso_mensual"], g["fac500a"]))
    muestra = por_departamento(emp_jov, lambda g: float(len(g)))

    tabla = pd.DataFrame({
        "pobreza_pct": pobreza, "pobreza_jovenes_pct": pobreza_jov, "desempleo_jovenes_pct": desempleo,
        "ocupados_jovenes_sin_pension_pct": sin_pension, "ingreso_laboral_mensual_jovenes_soles": ingreso,
        "poblacion_jovenes": poblacion_jov, "muestra_jovenes": muestra,
    }).round({"pobreza_pct": 1, "pobreza_jovenes_pct": 1, "desempleo_jovenes_pct": 1,
              "ocupados_jovenes_sin_pension_pct": 1, "ingreso_laboral_mensual_jovenes_soles": 0,
              "poblacion_jovenes": 0, "muestra_jovenes": 0})
    tabla.index.name = "ccdd"
    tabla.insert(0, "departamento", [NOMBRES.get(i, "Perú (nacional)") for i in tabla.index])
    tabla = tabla.reset_index().sort_values("ccdd")

    # 4. Validación contra el INEI
    oficial = pd.read_csv(SKILL / "referencias" / f"pobreza_departamento_{a.anio}.csv", dtype={"ccdd": str})
    lineas, errores = [f"Validación ENAHO {a.anio} (código {a.codigo})", ""], []
    nacional = float(tabla.loc[tabla["ccdd"] == "00", "pobreza_pct"].iloc[0])
    lineas.append(f"Pobreza nacional: {nacional:.1f}% (INEI: 27.6%)")
    if abs(nacional - 27.6) > TOLERANCIA:
        errores.append("pobreza nacional")
    for _, fila in oficial.iterrows():
        calc = float(tabla.loc[tabla["ccdd"] == fila["ccdd"], "pobreza_pct"].iloc[0])
        ok = abs(calc - fila["pobreza_pct"]) <= TOLERANCIA
        lineas.append(f"{'OK ' if ok else 'MAL'} {fila['departamento']:15} calculado {calc:5.1f}%  INEI {fila['pobreza_pct']:5.1f}%")
        if not ok:
            errores.append(fila["departamento"])
    lineas.append(f"\nResidentes habituales: {filas_antes:,} · jóvenes 18-29 en módulo 05: {len(emp_jov):,}")
    lineas.append("Informalidad: aproximada como ocupados sin afiliación a un sistema de pensiones (p558a5 == 5).")
    reporte = "\n".join(lineas)

    salida.mkdir(parents=True, exist_ok=True)
    (salida / f"validacion_{a.anio}.txt").write_text(reporte, encoding="utf-8")
    print(reporte)
    if errores:
        sys.exit(f"\nVALIDACIÓN FALLIDA en: {', '.join(errores)}. No se guardó la tabla.")
    tabla.to_csv(salida / f"indicadores_{a.anio}.csv", index=False, encoding="utf-8")
    print(f"\nGuardado: {salida / f'indicadores_{a.anio}.csv'} ({len(tabla)} filas)")


if __name__ == "__main__":
    main()
