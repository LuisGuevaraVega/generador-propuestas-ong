"""Temáticas del boletín: clasifica cada convocatoria por palabras clave para filtrar con un clic.

Una convocatoria puede caer en varias temáticas. Las palabras van sin tildes y en minúsculas, y se
buscan dentro del título, el tema, el tipo y la descripción de la convocatoria.
"""
import unicodedata
from collections import Counter

TEMAS = {
    "💰 Microfinanzas e inclusión financiera": (
        "microfinanz", "microcredit", "microfinance", "inclusion financiera", "financial inclusion",
        "inclusive finance", "finanzas inclusivas", "educacion financiera", "financial education",
        "financial capability", "bancos comunales", "banca comunal", "grupos de ahorro", "savings group",
        "vsla", "unicas", "ahorro y credito", "caja municipal", "cajas municipales", "caja rural", "edpyme",
        "fintech", "remesas", "seguros inclusivos"),
    "🌱 Cadenas de valor y productores": (
        "cadena de valor", "cadenas de valor", "productor", "productiv", "agricol", "agropecuari", "cooperativ",
        "asociatividad", "articulacion comercial", "cacao", "cafe", "exportab", "marcas colectivas", "artesan"),
    "📊 Estudios y evaluaciones": (
        "estudio", "evaluacion", "diagnostico", "linea de base", "sistematizacion", "mapeo", "investigacion",
        "encuesta"),
    "👷 Empleo y capacitación": (
        "empleab", "empleo", "capacitacion", "formacion laboral", "insercion laboral", "trabajadores"),
    "🚀 Emprendimiento y MYPE": (
        "emprend", "mipyme", "mype", "pyme", "microempres", "pequenas empresas", "generadores de ingresos"),
    "👩 Mujeres y género": ("mujer", "genero", "igualdad", "violencia"),
    "🌎 Clima y ambiente": (
        "clima", "climat", "ambiental", "medio ambiente", "biodivers", "bosque", "residuos"),
    "🧳 Migración": ("migra", "refugi", "venezolan"),
    "🏛️ Fortalecimiento institucional": (
        "fortalecimiento institucional", "fortalecimiento organizacional", "fortalecimiento de organizaciones",
        "evaluacion institucional", "capacidades institucionales"),
}
CAMPOS = ("title", "topic", "type", "why")


def _normal(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def temas_de(item: dict) -> list:
    """Temáticas en las que cae una convocatoria, en el orden de TEMAS."""
    texto = _normal(" ".join(str(item.get(k, "")) for k in CAMPOS))
    return [tema for tema, palabras in TEMAS.items() if any(p in texto for p in palabras)]


def sugeridos(items) -> Counter:
    """Temáticas presentes en un conjunto de convocatorias, con cuántas tiene cada una (para sugerirlas)."""
    conteo = Counter(t for item in items for t in temas_de(item))
    return Counter({t: conteo[t] for t in TEMAS if conteo[t]})
