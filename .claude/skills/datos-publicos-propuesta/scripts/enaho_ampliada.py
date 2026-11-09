"""Indicadores adicionales de la ENAHO por departamento (complementan los de jóvenes de la skill de la ENAHO).

Uso:
    python .claude/skills/datos-publicos-propuesta/scripts/enaho_ampliada.py --codigo 966 --anio 2024

Usa los módulos 34 (sumaria), 02 (miembros) y 03 (educación) de datos/enaho/ y guarda
data/contexto/enaho_<anio>.csv en formato largo. Reutiliza el lector de la skill
datos-enaho-propuesta (mismas reglas: pesos, residentes habituales, departamento por ubigeo).

Validación: la pobreza extrema nacional debe coincidir con la cifra oficial del INEI
(REFERENCIA) con una tolerancia de 0.15 puntos; si no, no se guarda nada.
"""
import argparse
import csv
import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
_ENAHO = RAIZ / ".claude" / "skills" / "datos-enaho-propuesta" / "scripts" / "indicadores.py"
_spec = importlib.util.spec_from_file_location("indicadores_enaho", _ENAHO)
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

REFERENCIA = {"2024": {"pobreza_extrema": 5.5}}  # INEI, Evolución de la pobreza monetaria 2024
TOLERANCIA = 0.15
ESTRATO_RURAL = (6, 7, 8)  # en la ENAHO, estratos 1 a 5 son urbanos y 6 a 8 rurales
SECUNDARIA_COMPLETA = range(6, 12)  # p301a: 6 = secundaria completa ... 11 = posgrado
EDAD_SECUNDARIA = (20, 24)


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--codigo", default="966")
    args.add_argument("--anio", default="2024")
    args.add_argument("--datos", default=str(RAIZ / "datos" / "enaho"))
    args.add_argument("--salida", default=str(RAIZ / "data" / "contexto"))
    a = args.parse_args()
    datos = Path(a.datos)
    llaves = base.LLAVES_HOGAR

    # Hogares: pobreza extrema (pobreza == 1) y ruralidad, con peso de personas factor07 × mieperho
    hogares = base.leer(datos, a.codigo, "34", "sumaria-", llaves + ["ubigeo", "pobreza", "mieperho", "factor07", "estrato"])
    hogares["departamento"] = hogares["ubigeo"].str.zfill(6).str[:2]
    hogares["peso_personas"] = hogares["factor07"] * hogares["mieperho"]
    extrema = base.por_departamento(hogares, lambda g: base.ponderado((g["pobreza"] == 1).astype(float), g["peso_personas"]) * 100)
    rural = base.por_departamento(hogares, lambda g: base.ponderado(g["estrato"].isin(ESTRATO_RURAL).astype(float),
                                                                    g["peso_personas"]) * 100)

    # Jefatura femenina: jefe del hogar (p203 == 1) mujer (p207 == 2), ponderado por hogar (factor07)
    personas = base.leer(datos, a.codigo, "02", "200", llaves + ["codperso", "p203", "p207"])
    jefes = personas[personas["p203"] == 1].merge(hogares[llaves + ["departamento", "factor07"]], on=llaves,
                                                  how="inner", validate="1:1")
    jefa = base.por_departamento(jefes, lambda g: base.ponderado((g["p207"] == 2).astype(float), g["factor07"]) * 100)

    # Educación: jóvenes de 20 a 24 años con secundaria completa o más (residentes, factora07)
    edu = base.leer(datos, a.codigo, "03", "300", llaves + ["codperso", "ubigeo", "p208a", "p301a", "factora07",
                                                             "p204", "p205", "p206"])
    residentes = ((edu["p204"] == 1) & (edu["p205"] == 2)) | ((edu["p204"] == 2) & (edu["p206"] == 1))
    edu = edu[residentes & edu["p208a"].between(*EDAD_SECUNDARIA)].copy()
    edu["departamento"] = edu["ubigeo"].str.zfill(6).str[:2]
    secundaria = base.por_departamento(edu, lambda g: base.ponderado(g["p301a"].isin(SECUNDARIA_COMPLETA).astype(float),
                                                                     g["factora07"]) * 100)
    muestra_edu = base.por_departamento(edu, lambda g: float(len(g)))

    indicadores = [
        ("pobreza", "Población en pobreza extrema", extrema, None),
        ("territorio", "Población que vive en zona rural", rural, None),
        ("género", "Hogares con jefatura femenina", jefa, None),
        ("educación", "Jóvenes de 20 a 24 años con secundaria completa o más", secundaria, muestra_edu),
    ]

    nacional = float(extrema["00"])
    esperado = REFERENCIA.get(a.anio, {}).get("pobreza_extrema")
    print(f"Pobreza extrema nacional: {nacional:.1f}% (INEI: {esperado}%)")
    if esperado is not None and abs(nacional - esperado) > TOLERANCIA:
        sys.exit("VALIDACIÓN FALLIDA: la pobreza extrema no coincide con el INEI. No se guardó la tabla.")

    filas = []
    for tema, nombre, serie, muestra in indicadores:
        for ccdd in sorted(serie.index):
            filas.append({"ccdd": ccdd, "departamento": base.NOMBRES.get(ccdd, "Perú (nacional)"), "tema": tema,
                          "indicador": nombre, "valor": round(float(serie[ccdd]), 1), "unidad": "%",
                          "fuente": f"INEI, ENAHO {a.anio}", "anio": a.anio,
                          "referencial": int(muestra is not None and float(muestra[ccdd]) < 300),
                          "nota": "" if (tema == "pobreza" and ccdd == "00") else "cálculo propio con microdatos"})
        print(f"{nombre}: Perú {float(serie['00']):.1f}%")
    salida = Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    destino = salida / f"enaho_{a.anio}.csv"
    with destino.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(filas[0]))
        escritor.writeheader()
        escritor.writerows(filas)
    print(f"Guardado: {destino} ({len(filas)} filas)")


if __name__ == "__main__":
    main()
