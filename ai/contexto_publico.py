"""Datos públicos del INEI por departamento, elegidos según el tema de la convocatoria.

Las tablas de `data/contexto/` (formato largo: un indicador por fila) las genera y valida la skill
de Claude Code `.claude/skills/datos-publicos-propuesta` a partir de la ENDES (cuadros oficiales
del INEI) y de los microdatos de la ENAHO. Aquí se eligen los indicadores que calzan con el tema
de la convocatoria y de la idea, y se arma el bloque que recibe el generador.
"""
import csv
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "data" / "contexto"
SIEMPRE = ("pobreza", "territorio")
MAXIMO = 8

# tema -> raíces de palabras que lo activan (sin tildes)
TEMAS = {
    "nutrición e infancia": ("nutric", "anemia", "desnutric", "infan", "nino", "nina", "alimenta", "salud",
                             "cuidado", "control de crecimiento", "lactancia", "seguridad alimentaria"),
    "salud materna": ("gestant", "materna", "materno", "parto", "embaraz", "prenatal", "salud sexual"),
    "violencia de género": ("violencia", "genero", "igualdad", "feminicid", "mujer"),
    "género": ("mujer", "genero", "igualdad", "empoderamiento", "jefa", "emprendedora", "productoras"),
    "agua y saneamiento": ("agua", "saneamiento", "higiene", "wash", "desague", "letrina"),
    "educación": ("educa", "escuela", "escolar", "joven", "juvenil", "capacitacion", "empleabilidad", "beca",
                  "formacion", "secundaria"),
}


def _normal(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def cargar() -> list:
    filas = []
    for tabla in sorted(CARPETA.glob("*.csv")):
        with tabla.open(encoding="utf-8") as f:
            filas += list(csv.DictReader(f))
    return filas


def temas(*textos) -> list:
    """Temas que se mencionan en los textos (convocatoria, idea, TdR), además de los de siempre."""
    junto = _normal(" ".join(t for t in textos if t))
    elegidos = [t for t, raices in TEMAS.items() if any(re.search(rf"\b{re.escape(r)}", junto) for r in raices)]
    return list(SIEMPRE) + elegidos


def indicadores(ccdd: str, *textos) -> list:
    """[(fila del departamento, fila nacional)] de los temas que calzan, hasta MAXIMO."""
    if not ccdd:
        return []
    filas = cargar()
    nacional = {(f["indicador"]): f for f in filas if f["ccdd"] == "00"}
    del_dep = [f for f in filas if f["ccdd"] == ccdd]
    orden = temas(*textos)
    elegidos = sorted((f for f in del_dep if f["tema"] in orden), key=lambda f: orden.index(f["tema"]))
    return [(f, nacional.get(f["indicador"])) for f in elegidos][:MAXIMO]


def contexto(ccdd: str, *textos) -> str:
    """Bloque para el prompt con los indicadores elegidos y cómo citarlos."""
    pares = indicadores(ccdd, *textos)
    if not pares:
        return ""
    lineas = []
    for f, n in pares:
        comparacion = f" (Perú: {n['valor']}{f['unidad']})" if n else ""
        notas = "; ".join(x for x in (f.get("nota"), "referencial por tamaño de muestra" if f.get("referencial") == "1"
                                       else "") if x)
        lineas.append(f"- {f['indicador']}: {f['departamento']} {f['valor']}{f['unidad']}{comparacion}. "
                      f"Fuente: {f['fuente']}" + (f" ({notas})" if notas else "") + ".")
    return ("MÁS DATOS PÚBLICOS DEL DEPARTAMENTO, elegidos por el tema de la convocatoria (fuentes 'ENAHO' y "
            "'ENDES' del INEI):\n" + "\n".join(lineas) + "\n"
            "Usa en la sección del problema los que sirvan para dimensionarlo, citando la fuente tal cual "
            "(«INEI, ENDES 2024» o «INEI, ENAHO 2024»), y pon \"ENDES\" o \"ENAHO\" en fuentes. No redondees "
            "ni cambies las cifras.")
