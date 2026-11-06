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
CARACTERES_POR_PAGINA = 2500
MAX_CARACTERES = 200_000  # ~80 páginas: el TdR o las bases se leen completos salvo casos extremos


MARCA_OCR = "[Texto leído con OCR]"
IMAGENES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
MIN_CARACTERES_POR_PAGINA = 100


def leer_documento(nombre: str, contenido: bytes, ocr: bool = True) -> str:
    """Devuelve el texto de un archivo según su extensión.

    Los PDF escaneados y las imágenes se leen con OCR (Gemini) si `ocr` es True.
    """
    ext = nombre.lower().rsplit(".", 1)[-1]
    if ext in IMAGENES:
        return _ocr(contenido, IMAGENES[ext]) if ocr else ""
    if ext == "pdf":
        return _leer_pdf(contenido, ocr)
    if ext == "docx":
        return _leer_docx(contenido)
    if ext in ("xlsx", "xlsm"):
        return _leer_xlsx(contenido)
    if ext in ("html", "htm"):
        return _limpiar_html(contenido.decode("utf-8", errors="ignore"))
    return contenido.decode("utf-8", errors="ignore")


def _ocr(contenido: bytes, mime: str) -> str:
    from ai.llm import transcribir_documento  # import diferido: leer Word o Excel no necesita la API

    return f"{MARCA_OCR}\n{transcribir_documento(contenido, mime)}"


def es_escaneado(texto: str, paginas: int) -> bool:
    """Un PDF con menos de ~100 caracteres seleccionables por página es, en la práctica, una imagen."""
    return len(texto.strip()) < MIN_CARACTERES_POR_PAGINA * max(paginas, 1)


def _leer_pdf(contenido: bytes, ocr: bool = True) -> str:
    import fitz  # PyMuPDF

    with fitz.open(stream=contenido, filetype="pdf") as doc:
        texto = "\n".join(pagina.get_text() for pagina in doc)
        paginas = len(doc)
    if not es_escaneado(texto, paginas):
        return texto
    if ocr:
        try:
            return _ocr(contenido, "application/pdf")
        except Exception as error:
            return texto + f"\n[Aviso: el PDF parece escaneado y el OCR falló: {error}]"
    return texto + "\n[Aviso: el PDF parece escaneado; casi no tiene texto seleccionable.]"


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


def descargar_archivo_tdr(url: str) -> dict:
    """Descarga el TdR y devuelve {'texto', 'contenido', 'nombre', 'mime', 'es_documento'}.

    `es_documento` es True si es un PDF o Word que el usuario puede guardar; si el enlace
    es una página web, solo se extrae su texto.
    """
    respuesta = requests.get(_url_descarga(url), headers=CABECERAS, timeout=30)
    respuesta.raise_for_status()
    tipo = respuesta.headers.get("Content-Type", "").lower()
    contenido = respuesta.content
    nombre_url = re.sub(r"[?#].*$", "", url).rstrip("/").rsplit("/", 1)[-1] or "tdr"
    if "pdf" in tipo or contenido[:4] == b"%PDF":
        nombre = nombre_url if nombre_url.lower().endswith(".pdf") else "tdr.pdf"
        return {"texto": leer_documento("tdr.pdf", contenido), "contenido": contenido, "nombre": nombre,
                "mime": "application/pdf", "es_documento": True}
    if "wordprocessingml" in tipo:
        nombre = nombre_url if nombre_url.lower().endswith(".docx") else "tdr.docx"
        return {"texto": leer_documento("tdr.docx", contenido), "contenido": contenido, "nombre": nombre,
                "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "es_documento": True}
    try:
        html = contenido.decode("utf-8")
    except UnicodeDecodeError:
        html = contenido.decode(respuesta.apparent_encoding or "latin-1", errors="ignore")
    return {"texto": _limpiar_html(html), "contenido": contenido, "nombre": "convocatoria.html",
            "mime": "text/html", "es_documento": False}


def descargar_tdr(url: str) -> str:
    """Descarga el TdR o la página de la convocatoria y devuelve su texto."""
    return descargar_archivo_tdr(url)["texto"]


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
    parrafos = []
    for p in (p.strip() for p in texto.split("\n")):
        # Un "párrafo" enorme (p. ej. un PDF sin saltos de línea) se parte en trozos del tamaño del fragmento.
        parrafos += [p[i:i + tamano] for i in range(0, len(p), tamano)] if p else []
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

    def puntajes(self, consultas: List[str]):
        """Relevancia de cada fragmento: su mayor parecido con cualquiera de las consultas."""
        from sklearn.metrics.pairwise import cosine_similarity

        return cosine_similarity(self.vectorizador.transform(consultas), self.matriz).max(axis=0)
