"""Proyectos similares financiados por el BID en Perú, como referencia para la propuesta.

La tabla `data/referencias/bid_peru.csv` sale de los datos abiertos del BID (licencia CC BY 4.0)
y se actualiza con `python scripts/actualizar_referencias_bid.py`. Aquí se busca, con TF-IDF,
qué proyectos se parecen más a la convocatoria y a la idea del usuario, y se arma el bloque de
contexto que recibe el generador con la fuente "BID".
"""
import csv
from functools import lru_cache
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TABLA = RAIZ / "data" / "referencias" / "bid_peru.csv"
FUENTE = "Datos abiertos del BID (data.iadb.org, CC BY 4.0)"
MAXIMO = 5
MINIMO_PARECIDO = 0.12  # por debajo, el parecido es casual (palabras sueltas en común)
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


@lru_cache(maxsize=1)
def cargar() -> tuple:
    """Proyectos de la tabla (tupla de dicts), o vacía si la tabla aún no existe."""
    if not TABLA.exists():
        return ()
    with TABLA.open(encoding="utf-8") as f:
        return tuple(p for p in csv.DictReader(f) if (p["aprobacion"] or DESDE) >= DESDE)


@lru_cache(maxsize=1)
def _indice():
    from sklearn.feature_extraction.text import TfidfVectorizer

    proyectos = cargar()
    vectorizador = TfidfVectorizer(strip_accents="unicode", lowercase=True, ngram_range=(1, 2), min_df=1,
                                   stop_words=VACIAS + LUGARES, sublinear_tf=True)
    textos = [f"{p['nombre']} {p['nombre']} {p['subsector']} {p['objetivo']}" for p in proyectos]
    return vectorizador, vectorizador.fit_transform(textos)


def similares(*textos, k: int = MAXIMO, minimo: float = MINIMO_PARECIDO) -> list:
    """Hasta `k` proyectos más parecidos a los textos (convocatoria, idea, TdR), con su `parecido` (0 a 1)."""
    from sklearn.metrics.pairwise import cosine_similarity

    consulta = " ".join(t for t in textos if t).strip()
    proyectos = cargar()
    if not consulta or not proyectos:
        return []
    vectorizador, matriz = _indice()
    puntajes = cosine_similarity(vectorizador.transform([consulta]), matriz)[0]
    orden = [i for i in puntajes.argsort()[::-1][:k] if puntajes[i] >= minimo]
    return [{**proyectos[i], "parecido": round(float(puntajes[i]), 3), "enlace": enlace(proyectos[i]["codigo"])}
            for i in orden]


def enlace(codigo: str) -> str:
    return f"https://www.iadb.org/es/proyecto/{codigo}"


def monto(valor) -> str:
    try:
        return f"US$ {float(valor):,.0f}"
    except (TypeError, ValueError):
        return "monto no publicado"


def contexto(proyectos: list) -> str:
    """Bloque de texto para el prompt con los proyectos de referencia (fuente 'BID')."""
    if not proyectos:
        return ""
    lineas = []
    for p in proyectos:
        anio = (p.get("aprobacion") or "")[:4] or "s/f"
        objetivo = p.get("objetivo") or "(el BID no publica el objetivo)"
        lineas.append(f"- {p['codigo']} · {p['nombre']} ({anio}; {p['estado'].lower()}; {p['tipo']}; "
                      f"{p['sector'].lower()}). Financiamiento BID: {monto(p.get('monto_bid_usd'))}. "
                      f"Objetivo: {objetivo}")
    return ("PROYECTOS SIMILARES FINANCIADOS POR EL BID EN PERÚ (fuente 'BID'; " + FUENTE + "):\n"
            + "\n".join(lineas) + "\n"
            "Úsalos solo como referencia de qué tipo de objetivos, componentes y escala de montos financia la "
            "cooperación en temas parecidos. No copies su texto, no los presentes como experiencia de la "
            "organización, no afirmes que fueron exitosos ni inventes sus resultados. Si mencionas uno, cítalo como «BID, proyecto <código>» "
            "y pon \"BID\" en fuentes.")
