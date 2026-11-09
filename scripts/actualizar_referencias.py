"""Actualiza los proyectos de referencia en Perú del BID y de la cooperación alemana (BMZ).

Fuentes (datos abiertos, no se raspa ninguna web):
- BID: lista oficial de proyectos (https://data.iadb.org/dataset/idb-projects-dataset), CC BY 4.0.
- BMZ: actividades que el BMZ publica en el estándar IATI, vía la API de d-portal.org.
  Vienen en alemán o inglés: los títulos y objetivos nuevos se traducen y resumen al español
  con Gemini (los ya traducidos se reutilizan, así cada mes solo se traduce lo nuevo).

Uso:
    python scripts/actualizar_referencias.py                  # BID y BMZ
    python scripts/actualizar_referencias.py --solo bid       # o --solo bmz
    python scripts/actualizar_referencias.py --bid lista.csv  # BID desde un CSV ya descargado

Corre solo el día 1 de cada mes con GitHub Actions (.github/workflows/referencias.yml).
Guarda data/referencias/bid_peru.csv y data/referencias/bmz_peru.csv con las mismas columnas.
"""
import argparse
import csv
import io
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import List

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
CARPETA = RAIZ / "data" / "referencias"
COLUMNAS = ["fuente", "codigo", "nombre", "aprobacion", "estado", "ejecutor", "tipo", "sector", "objetivo",
            "monto", "moneda", "enlace", "idioma"]
AGENTE = {"User-Agent": "generador-propuestas-ong/1.0 (datos abiertos)"}

# ---------- BID
API_BID = "https://data.iadb.org/api/3/action/package_show?id=idb-projects-dataset"
RECURSO_BID = "ES - Listado de Proyectos BID"
URL_BID_RESPALDO = "https://data.iadb.org/files/download/fc342d1e-fdc9-4590-8d47-c4499a89d381"
ESTADOS_BID = {"Cerrado", "Implementación"}
SECTORES_FUERA = {"TRANSPORTE", "ENERGIA", "AGUA Y SANEAMIENTO", "REFORMA/MODERNIZACIÓN DEL ESTADO",
                  "DESARROLLO Y VIVIENDA URBANOS", "INTEGRACIÓN REGIONAL"}

# ---------- BMZ
URL_BMZ = "https://d-portal.org/q.xml?from=act,country&country_code=PE&reporting_ref=DE-1&limit=5000"
ESTADOS_IATI = {"2": "Implementación", "3": "Finalizado", "4": "Cerrado"}
DESDE_BMZ = "2010"
MONTO_MAX_BMZ = 20_000_000  # por encima son préstamos o programas de Estado, no proyectos de ONG
LANG = "{http://www.w3.org/XML/1998/namespace}lang"
LOTE_TRADUCCION = 15


def _bajar(url: str, segundos: int = 180) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENTE), timeout=segundos) as r:
        return r.read()


def _monto(valor) -> str:
    try:
        return f"{float(valor):.0f}"
    except (TypeError, ValueError):
        return ""


# ---------- BID
def url_csv_bid() -> str:
    """URL vigente del CSV en español (cambia si el BID republica el recurso)."""
    try:
        recursos = json.loads(_bajar(API_BID, 60))["result"]["resources"]
        return next(x["url"] for x in recursos if x["name"] == RECURSO_BID)
    except Exception as error:  # la API puede fallar; el enlace directo suele seguir vivo
        print(f"No se pudo consultar la API del BID ({error}); uso el enlace conocido.")
        return URL_BID_RESPALDO


def filtrar_bid(texto_csv: str) -> list:
    """Proyectos de Perú cerrados o en ejecución, sin infraestructura pesada ni reforma del Estado."""
    filas = []
    for f in csv.DictReader(io.StringIO(texto_csv.lstrip("﻿"))):
        f = {k: "" if (v or "").strip().upper() in ("NULL", "NAN") else (v or "").strip() for k, v in f.items()}
        if f.get("cntry_cd") != "PE" or f.get("publc_sts_nm") not in ESTADOS_BID:
            continue
        if f.get("sector_nm") in SECTORES_FUERA:
            continue
        filas.append({
            "fuente": "BID", "codigo": f["oper_num"], "nombre": f["oper_nm"], "aprobacion": f["apprvl_dt"][:10],
            "estado": f["publc_sts_nm"], "ejecutor": "", "tipo": f.get("opertyp_nm", ""),
            "sector": " / ".join(x for x in (f.get("sector_nm", "").capitalize(), f.get("subsector_nm", "").capitalize()) if x),
            "objetivo": f.get("objtv", ""), "monto": _monto(f.get("orig_apprvd_useq_amnt")), "moneda": "USD",
            "enlace": f"https://www.iadb.org/es/proyecto/{f['oper_num']}", "idioma": "es",
        })
    return sorted(filas, key=lambda x: x["aprobacion"], reverse=True)


# ---------- BMZ
def _narrativa(elemento, preferencia=("ES", "EN", "DE")) -> str:
    if elemento is None:
        return ""
    textos = {(n.get(LANG) or "").upper(): (n.text or "").strip() for n in elemento.findall("narrative")}
    for idioma in preferencia:
        if textos.get(idioma):
            return textos[idioma]
    return next((t for t in textos.values() if t), "")


def filtrar_bmz(xml: bytes) -> list:
    """Proyectos del BMZ en Perú desde 2010, sin préstamos de Estado ni la banca de desarrollo (KfW)."""
    filas = []
    for a in ET.fromstring(xml).findall("iati-activity"):
        codigo = (a.findtext("iati-identifier") or "").strip()
        estado = a.find("activity-status")
        estado = ESTADOS_IATI.get(estado.get("code") if estado is not None else "")
        fechas = {d.get("type"): d.get("iso-date", "") for d in a.findall("activity-date")}
        inicio = fechas.get("2") or fechas.get("1") or ""
        titulo = _narrativa(a.find("title"), ("EN", "DE"))
        ejecutor = next((_narrativa(o, ("EN", "DE")) for o in a.findall("participating-org") if o.get("role") == "3"), "")
        monto = sum(float(t.findtext("value") or 0) for t in a.findall("transaction")
                    if (t.find("transaction-type") is not None and t.find("transaction-type").get("code") == "2"))
        if not codigo or not estado or inicio[:4] < DESDE_BMZ or "kfw" in ejecutor.lower():
            continue
        if monto > MONTO_MAX_BMZ or "policy based loan" in titulo.lower():
            continue
        descripcion = " ".join(_narrativa(d, ("EN", "DE")) for d in a.findall("description")
                               if d.get("type") in (None, "1", "2"))
        filas.append({
            "fuente": "BMZ", "codigo": codigo, "nombre": titulo, "aprobacion": inicio[:10], "estado": estado,
            "ejecutor": ejecutor, "tipo": "Cooperación alemana (BMZ)", "sector": "",
            "objetivo": " ".join(dict.fromkeys(descripcion.split("\n")))[:3000],
            "monto": _monto(monto) if monto else "", "moneda": a.get("default-currency") or "EUR",
            "enlace": f"https://d-portal.org/ctrack.html#view=act&aid={codigo}", "idioma": "original",
        })
    return sorted(filas, key=lambda x: x["aprobacion"], reverse=True)


_INGLES = {"the", "and", "of", "for", "with", "to", "in", "on", "by"}
_ESPANOL = {"de", "la", "el", "los", "las", "y", "en", "del", "para", "con", "por", "su", "sus"}


def en_espanol(*textos) -> bool:
    """Descarta las "traducciones" que el modelo devolvió en inglés (a veces copia el original)."""
    def ok(texto):
        palabras = re.findall("[a-záéíóúñ]+", (texto or "").lower())
        ingles = sum(w in _INGLES for w in palabras)
        return bool(palabras) and ingles <= sum(w in _ESPANOL for w in palabras) and ingles <= 2
    return all(ok(t) for t in textos)


def traducir(filas: list, previas: dict) -> list:
    """Reutiliza las traducciones del mes anterior y traduce al español solo lo nuevo (con Gemini)."""
    pendientes = []
    for f in filas:
        anterior = previas.get(f["codigo"])
        if anterior and anterior.get("idioma") == "es" and en_espanol(anterior["nombre"], anterior["objetivo"]):
            f.update(nombre=anterior["nombre"], objetivo=anterior["objetivo"], sector=anterior.get("sector", ""),
                     idioma="es")
        else:
            pendientes.append(f)
    if not pendientes:
        return filas
    try:
        from pydantic import BaseModel, Field

        from ai.llm import MODELOS, generar_estructurado

        class Traduccion(BaseModel):
            codigo: str
            nombre: str = Field(description="Título del proyecto en español, fiel al original")
            objetivo: str = Field(description="Resumen en español de 40 a 80 palabras: objetivo, población y "
                                              "enfoque o actividades principales. Sin inventar datos.")
            sector: str = Field(description="Tema principal en 2 a 4 palabras, p. ej. 'Agricultura familiar'")

        class Lote(BaseModel):
            items: List[Traduccion]

        lite = [m for m in MODELOS if "lite" in m] + [m for m in MODELOS if "lite" not in m]
        for i in range(0, len(pendientes), LOTE_TRADUCCION):
            lote = pendientes[i:i + LOTE_TRADUCCION]
            entrada = [{"codigo": f["codigo"], "titulo": f["nombre"], "descripcion": f["objetivo"][:1500]} for f in lote]
            salida = generar_estructurado(
                json.dumps(entrada, ensure_ascii=False), Lote,
                "Traduce y resume al español proyectos de cooperación al desarrollo en el Perú. Escribe TODO en "
                "español, también el título (nunca lo dejes en inglés o alemán). Devuelve un item por proyecto, "
                "con el mismo código.", temperatura=0.1, modelos=lite)
            por_codigo = {t.codigo: t for t in salida.items}
            for f in lote:
                t = por_codigo.get(f["codigo"])
                if t and en_espanol(t.nombre, t.objetivo):
                    f.update(nombre=t.nombre, objetivo=t.objetivo, sector=t.sector, idioma="es")
            print(f"  traducidos {min(i + LOTE_TRADUCCION, len(pendientes))}/{len(pendientes)}", flush=True)
    except Exception as error:  # sin clave o sin cuota: se guardan en el idioma original y se reintenta el próximo mes
        print(f"No se pudo traducir ({error}); quedan en el idioma original.")
    for f in filas:
        if f["idioma"] != "es":
            f["objetivo"] = f["objetivo"][:800]
    return filas


# ---------- archivos
def leer(destino: Path) -> dict:
    if not destino.exists():
        return {}
    with destino.open(encoding="utf-8") as f:
        return {fila["codigo"]: fila for fila in csv.DictReader(f)}


def guardar(filas: list, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
        escritor.writeheader()
        escritor.writerows(filas)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--solo", choices=["bid", "bmz"])
    parser.add_argument("--bid", help="CSV del BID ya descargado")
    args = parser.parse_args(argv)

    if args.solo in (None, "bid"):
        if args.bid:
            texto = Path(args.bid).read_text(encoding="utf-8-sig", errors="replace")
        else:
            url = url_csv_bid()
            print(f"BID: descargando {url}")
            texto = _bajar(url).decode("utf-8-sig", errors="replace")
        filas = filtrar_bid(texto)
        if not filas:
            sys.exit("BID: no quedó ningún proyecto; revisa si cambió el formato del CSV.")
        guardar(filas, CARPETA / "bid_peru.csv")
        print(f"BID: {len(filas)} proyectos de Perú ({date.today()})")

    if args.solo in (None, "bmz"):
        print("BMZ: descargando actividades IATI de Perú")
        filas = filtrar_bmz(_bajar(URL_BMZ, 300))
        if not filas:
            sys.exit("BMZ: no quedó ningún proyecto; revisa la consulta a d-portal.")
        destino = CARPETA / "bmz_peru.csv"
        filas = traducir(filas, leer(destino))
        guardar(filas, destino)
        print(f"BMZ: {len(filas)} proyectos de Perú, {sum(f['idioma'] == 'es' for f in filas)} en español "
              f"({date.today()})")


if __name__ == "__main__":
    main()
