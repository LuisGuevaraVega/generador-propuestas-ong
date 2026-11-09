"""Proyectos similares financiados por el BID y por la cooperación alemana (BMZ) en Perú.

Las tablas de `data/referencias/` salen de datos abiertos (BID: data.iadb.org, CC BY 4.0; BMZ:
estándar IATI vía d-portal.org) y se actualizan cada mes con `scripts/actualizar_referencias.py`.
Aquí se buscan, con TF-IDF, los proyectos que más se parecen a la convocatoria y a la idea del
usuario, y se arma el bloque que la IA usa como base para diseñar la propuesta.
"""
import csv
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "data" / "referencias"
TABLAS = {"BID": CARPETA / "bid_peru.csv", "BMZ": CARPETA / "bmz_peru.csv"}
FUENTES = {
    "BID": "Banco Interamericano de Desarrollo (datos abiertos, data.iadb.org, CC BY 4.0)",
    "BMZ": "Ministerio Federal de Cooperación Económica y Desarrollo de Alemania (BMZ, datos IATI vía d-portal.org)",
}
POR_FUENTE = 4
MINIMO_PARECIDO = 0.18  # por debajo, el parecido es casual (pedazos de palabras sueltas en común)
DESDE = "2005"  # los proyectos más antiguos casi nunca publican su objetivo

# Palabras que aparecen en casi todo proyecto y no dicen nada del tema.
VACIAS = """a al ante con contra de del desde durante e el en entre esta este hacia hasta la las lo los mediante
o para por que se sin sobre su sus u un una y apoyo programa proyecto proyectos objetivo objetivos general
especifico especificos fortalecimiento fortalecer mejorar mejora desarrollo peru nacional cooperacion tecnica
asi como tambien otros otras traves dicho dicha buscar busca""".split()
# Los lugares no dicen de qué trata el proyecto: sin esto, "Lambayeque" pesa más que "agroecología".
LUGARES = """amazonas ancash apurimac arequipa ayacucho cajamarca callao cusco huancavelica huanuco ica junin
libertad lambayeque lima loreto madre dios moquegua pasco piura puno martin tacna tumbes ucayali chiclayo
trujillo huancayo iquitos pucallpa tarapoto sur norte centro region regional regiones""".split()

_cache = {}


def _limpiar(texto: str) -> str:
    """Minúsculas sin tildes y sin palabras vacías ni lugares, para comparar por tema."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    fuera = _cache.setdefault("fuera", frozenset(VACIAS + LUGARES))
    return " ".join(w for w in re.findall(r"[a-z]+", texto) if len(w) > 2 and w not in fuera)


def _firma():
    return tuple((f, t.stat().st_mtime) for f, t in TABLAS.items() if t.exists())


def cargar() -> tuple:
    """Proyectos de todas las fuentes (tupla de dicts). Se recarga sola si cambian las tablas."""
    firma = _firma()
    if _cache.get("firma") != firma:
        proyectos = []
        for fuente, tabla in TABLAS.items():
            if tabla.exists():
                with tabla.open(encoding="utf-8") as f:
                    proyectos += [{**p, "fuente": p.get("fuente") or fuente} for p in csv.DictReader(f)
                                  if (p.get("aprobacion") or DESDE) >= DESDE and p.get("idioma", "es") == "es"]
        _cache.clear()
        _cache.update(firma=firma, proyectos=tuple(proyectos), indice=None)
    return _cache["proyectos"]


def _indice():
    from sklearn.feature_extraction.text import TfidfVectorizer

    cargar()
    if _cache["indice"] is None:
        # Pedazos de 4 y 5 letras: "agroecológicas" se parece a "agroecológico" y "microempresarias" a "microempresa".
        vectorizador = TfidfVectorizer(analyzer="char_wb", ngram_range=(4, 5), sublinear_tf=True,
                                       min_df=1, max_df=0.3 if len(_cache["proyectos"]) >= 50 else 1.0)
        textos = [_limpiar(f"{p['nombre']} {p['nombre']} {p.get('sector', '')} {p['objetivo']}")
                  for p in _cache["proyectos"]]
        _cache["indice"] = (vectorizador, vectorizador.fit_transform(textos))
    return _cache["indice"]


def similares(*textos, por_fuente: int = POR_FUENTE, minimo: float = MINIMO_PARECIDO) -> list:
    """Los proyectos más parecidos a los textos: hasta `por_fuente` de cada fuente, con su `parecido` (0 a 1)."""
    from sklearn.metrics.pairwise import cosine_similarity

    consulta = _limpiar(" ".join(t for t in textos if t))
    proyectos = cargar()
    if not consulta or not proyectos:
        return []
    vectorizador, matriz = _indice()
    puntajes = cosine_similarity(vectorizador.transform([consulta]), matriz)[0]
    elegidos, cuenta = [], {}
    for i in puntajes.argsort()[::-1]:
        if puntajes[i] < minimo:
            break
        fuente = proyectos[i]["fuente"]
        if cuenta.get(fuente, 0) < por_fuente:
            cuenta[fuente] = cuenta.get(fuente, 0) + 1
            elegidos.append({**proyectos[i], "parecido": round(float(puntajes[i]), 3)})
    return elegidos


SIMBOLO = {"USD": "US$", "EUR": "€"}


def monto(proyecto) -> str:
    try:
        return f"{SIMBOLO.get(proyecto.get('moneda'), proyecto.get('moneda', ''))} {float(proyecto['monto']):,.0f}"
    except (TypeError, ValueError, KeyError):
        return "monto no publicado"


def anio(proyecto) -> str:
    return (proyecto.get("aprobacion") or "")[:4] or "s/f"


def contexto(proyectos: list) -> str:
    """Bloque para el prompt: los proyectos de referencia y cómo usarlos."""
    if not proyectos:
        return ""
    lineas = []
    for p in proyectos:
        ejecutor = f" Ejecutor: {p['ejecutor']}." if p.get("ejecutor") else ""
        lineas.append(f"- [{p['codigo']}] {p['fuente']} · {p['nombre']} ({anio(p)}; {p['estado'].lower()}; "
                      f"{monto(p)}).{ejecutor} Objetivo: {p.get('objetivo') or '(no publicado)'}")
    return ("PROYECTOS DE REFERENCIA: proyectos parecidos que ya financiaron el BID y la cooperación alemana "
            "(BMZ) en el Perú:\n" + "\n".join(lineas) + "\n"
            "Úsalos como BASE para diseñar la propuesta: toma de ellos los enfoques, los tipos de componentes y "
            "actividades, la población objetivo y la escala de montos que ya financió la cooperación, y adáptalos "
            "al TdR y a la organización. No copies su texto, no los presentes como experiencia de la organización, "
            "no afirmes que fueron exitosos, que demostraron o lograron algo, ni inventes sus resultados (no los tenemos). Cuando un párrafo se inspire en uno, pon "
            "su fuente (\"BID\" o \"BMZ\") en `fuentes`, y anota en `referencias` cada proyecto que usaste, con su "
            "código exacto (sin corchetes) y qué tomaste de él.")


def usadas(declaradas, candidatos: list) -> list:
    """Cruza lo que la IA dice haber usado con los candidatos reales (descarta códigos inventados)."""
    por_codigo = {p["codigo"]: p for p in candidatos}
    salida = []
    for r in declaradas or []:
        codigo = r.codigo.strip().strip("[]")
        if codigo in por_codigo and codigo not in {x["codigo"] for x in salida}:
            salida.append({**por_codigo[codigo], "aporte": r.aporte})
    return salida
