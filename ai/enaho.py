"""Datos públicos de la ENAHO para la sección del problema (skill datos-enaho-propuesta, sesión 16).

La tabla `data/enaho/indicadores_<anio>.csv` la genera y valida la skill de Claude Code
`.claude/skills/datos-enaho-propuesta`. Aquí solo se lee y se arma el bloque de contexto
que recibe el generador, con la fuente "ENAHO" para que cada cifra quede citada.
"""
import csv
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ANIO = "2024"
TABLA = RAIZ / "data" / "enaho" / f"indicadores_{ANIO}.csv"


def _normal(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def cargar():
    """Devuelve {ccdd: fila} o {} si la tabla aún no existe."""
    if not TABLA.exists():
        return {}
    with open(TABLA, encoding="utf-8") as f:
        return {fila["ccdd"].zfill(2): fila for fila in csv.DictReader(f)}


def departamentos():
    """Lista [(ccdd, nombre)] sin el total nacional, ordenada por nombre."""
    return sorted(((c, f["departamento"]) for c, f in cargar().items() if c != "00"), key=lambda x: _normal(x[1]))


def detectar(*textos) -> str:
    """Código del primer departamento mencionado en los textos (idea, organización, ámbito), o ''."""
    junto = _normal(" ".join(t for t in textos if t))
    for ccdd, nombre in departamentos():
        if _normal(nombre) in junto:
            return ccdd
    ciudades = {"chiclayo": "14", "trujillo": "13", "piura": "20", "arequipa": "04", "huancayo": "12",
                "iquitos": "16", "pucallpa": "25", "tarapoto": "22", "lima": "15", "cusco": "08"}
    return next((c for ciudad, c in ciudades.items() if ciudad in junto), "")


def contexto(ccdd: str) -> str:
    """Bloque de texto con los indicadores del departamento y del país, listo para el prompt."""
    tabla = cargar()
    if not ccdd or ccdd not in tabla:
        return ""

    def linea(f):
        return (f"- {f['departamento']}: pobreza monetaria {f['pobreza_pct']}%; jóvenes de 18 a 29 años: "
                f"pobreza {f['pobreza_jovenes_pct']}%, desempleo {f['desempleo_jovenes_pct']}%, "
                f"ocupados sin afiliación a pensiones {f['ocupados_jovenes_sin_pension_pct']}% "
                f"(aproximación a la informalidad), ingreso laboral mensual promedio S/ "
                f"{float(f['ingreso_laboral_mensual_jovenes_soles']):,.0f}; población de 18 a 29 años: "
                f"{float(f['poblacion_jovenes']):,.0f} personas.")

    referencial = int(float(tabla[ccdd]["muestra_jovenes"])) < 400
    return (f"DATOS PÚBLICOS (fuente 'ENAHO'; cítalos como «INEI, ENAHO {ANIO}»):\n"
            f"{linea(tabla[ccdd])}\n{linea(tabla['00'])}\n"
            "Usa estas cifras para dimensionar el problema; aclara que «sin pensión» es una aproximación a la "
            "informalidad" + (" y que las cifras departamentales son referenciales por tamaño de muestra." if referencial else "."))
