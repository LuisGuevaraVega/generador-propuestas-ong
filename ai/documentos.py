"""Lectura de documentos y búsqueda de fragmentos (RAG, sesión 08).

- Lee PDF, Word, Excel y texto plano.
- Descarga el TdR desde el enlace de la convocatoria (scraping, sesión 03).
- Parte las propuestas anteriores en fragmentos y recupera los más parecidos
  a cada sección con TF-IDF, sin llamar a ninguna API.
"""
import io
import re
from dataclasses import dataclass
from typing import List

import requests

CABECERAS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GeneradorPropuestas/0.1"}
MAX_CARACTERES = 60000


def leer_documento(nombre: str, contenido: bytes) -> str:
    """Devuelve el texto de un archivo según su extensión."""
    ext = nombre.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        return _leer_pdf(contenido)
    if ext == "docx":
        return _leer_docx(contenido)
    if ext in ("xlsx", "xlsm"):
        return _leer_xlsx(contenido)
    if ext in ("html", "htm"):
        return _limpiar_html(contenido.decode("utf-8", errors="ignore"))
    return contenido.decode("utf-8", errors="ignore")


def _leer_pdf(contenido: bytes) -> str:
    import fitz  # PyMuPDF

    with fitz.open(stream=contenido, filetype="pdf") as doc:
        texto = "\n".join(pagina.get_text() for pagina in doc)
    if len(texto.strip()) < 200:
        texto += "\n[Aviso: el PDF parece escaneado; casi no tiene texto seleccionable.]"
    return texto


def _leer_docx(contenido: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(contenido))
    partes = [p.text for p in doc.paragraphs if p.text.strip()]
    for tabla in doc.tables:
        for fila in tabla.rows:
            celdas = [c.text.strip() for c in fila.cells]
            if any(celdas):
                partes.append(" | ".join(celdas))
    return "\n".join(partes)


def _leer_xlsx(contenido: bytes) -> str:
    from openpyxl import load_workbook

    libro = load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
    partes = []
    for hoja in libro.worksheets:
        partes.append(f"# Hoja: {hoja.title}")
        for fila in hoja.iter_rows(values_only=True):
            valores = [str(v) for v in fila if v is not None]
            if valores:
                partes.append(" | ".join(valores))
    return "\n".join(partes)


def _limpiar_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|nav|footer|header).*?</\1>", " ", html)
    texto = re.sub(r"(?s)<[^>]+>", " ", html)
    texto = re.sub(r"&nbsp;", " ", texto)
    return re.sub(r"\s{2,}", "\n", texto).strip()


def _url_descarga(url: str) -> str:
    """Convierte enlaces de Google Drive a descarga directa."""
    m = re.search(r"drive\.google\.com/file/d/([^/]+)", url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    return url


def descargar_tdr(url: str) -> str:
    """Descarga el TdR o la página de la convocatoria y devuelve su texto."""
    respuesta = requests.get(_url_descarga(url), headers=CABECERAS, timeout=30)
    respuesta.raise_for_status()
    tipo = respuesta.headers.get("Content-Type", "").lower()
    if "pdf" in tipo or respuesta.content[:4] == b"%PDF":
        return leer_documento("tdr.pdf", respuesta.content)
    if "wordprocessingml" in tipo:
        return leer_documento("tdr.docx", respuesta.content)
    try:
        html = respuesta.content.decode("utf-8")
    except UnicodeDecodeError:
        html = respuesta.content.decode(respuesta.apparent_encoding or "latin-1", errors="ignore")
    return _limpiar_html(html)


def recortar(texto: str, maximo: int = MAX_CARACTERES) -> str:
    return texto if len(texto) <= maximo else texto[:maximo] + "\n[...texto recortado...]"


@dataclass
class Fragmento:
    doc: str
    numero: int
    texto: str

    @property
    def etiqueta(self) -> str:
        return f"DOC:{self.doc}#{self.numero}"


def trocear(nombre: str, texto: str, tamano: int = 1200, solape: int = 200) -> List[Fragmento]:
    """Parte un documento en fragmentos de ~1200 caracteres, respetando párrafos."""
    parrafos = [p.strip() for p in texto.split("\n") if p.strip()]
    fragmentos, actual = [], ""
    for parrafo in parrafos:
        if len(actual) + len(parrafo) > tamano and actual:
            fragmentos.append(actual)
            actual = actual[-solape:]
        actual += ("\n" if actual else "") + parrafo
    if actual:
        fragmentos.append(actual)
    return [Fragmento(nombre, i + 1, t) for i, t in enumerate(fragmentos)]


class Recuperador:
    """Buscador TF-IDF sobre las propuestas anteriores de la organización."""

    def __init__(self, fragmentos: List[Fragmento]):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.fragmentos = fragmentos
        self.vectorizador = TfidfVectorizer(strip_accents="unicode", lowercase=True, ngram_range=(1, 2), min_df=1)
        self.matriz = self.vectorizador.fit_transform([f.texto for f in fragmentos])

    def buscar(self, consulta: str, k: int = 4) -> List[Fragmento]:
        from sklearn.metrics.pairwise import cosine_similarity

        puntajes = cosine_similarity(self.vectorizador.transform([consulta]), self.matriz)[0]
        orden = puntajes.argsort()[::-1][:k]
        return [self.fragmentos[i] for i in orden if puntajes[i] > 0]
