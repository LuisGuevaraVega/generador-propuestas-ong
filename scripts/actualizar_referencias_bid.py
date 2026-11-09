"""Descarga la lista oficial de proyectos del BID y guarda los de Perú afines a las ONG.

Fuente: datos abiertos del BID (https://data.iadb.org/dataset/idb-projects-dataset),
licencia CC BY 4.0. Se usa el CSV oficial, no se raspa la web del BID.

Uso:
    python scripts/actualizar_referencias_bid.py            # descarga y filtra
    python scripts/actualizar_referencias_bid.py lista.csv  # usa un CSV ya descargado

Guarda data/referencias/bid_peru.csv con los proyectos de Perú cerrados o en ejecución,
sin los sectores de infraestructura pesada y de reforma del Estado (carreteras, agua,
energía, vivienda…), que no se parecen a una propuesta de ONG.
"""
import csv
import io
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "data" / "referencias" / "bid_peru.csv"
API = "https://data.iadb.org/api/3/action/package_show?id=idb-projects-dataset"
RECURSO_ES = "ES - Listado de Proyectos BID"
URL_RESPALDO = "https://data.iadb.org/files/download/fc342d1e-fdc9-4590-8d47-c4499a89d381"
AGENTE = {"User-Agent": "generador-propuestas-ong/1.0 (datos abiertos)"}

ESTADOS = {"Cerrado", "Implementación"}
SECTORES_FUERA = {"TRANSPORTE", "ENERGIA", "AGUA Y SANEAMIENTO", "REFORMA/MODERNIZACIÓN DEL ESTADO",
                  "DESARROLLO Y VIVIENDA URBANOS", "INTEGRACIÓN REGIONAL"}
COLUMNAS = {  # columna del BID -> columna nuestra
    "oper_num": "codigo", "oper_nm": "nombre", "apprvl_dt": "aprobacion", "publc_sts_nm": "estado",
    "opertyp_nm": "tipo", "sector_nm": "sector", "subsector_nm": "subsector", "objtv": "objetivo",
    "orig_apprvd_useq_amnt": "monto_bid_usd", "totl_cost_orig": "costo_total_usd", "loc_cntrprt": "contrapartida_usd",
}


def url_csv() -> str:
    """URL vigente del CSV en español (cambia si el BID republica el recurso)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(API, headers=AGENTE), timeout=60) as r:
            recursos = json.load(r)["result"]["resources"]
        return next(x["url"] for x in recursos if x["name"] == RECURSO_ES)
    except Exception as error:  # la API puede fallar; el enlace directo suele seguir vivo
        print(f"No se pudo consultar la API ({error}); uso el enlace conocido.")
        return URL_RESPALDO


def descargar() -> str:
    url = url_csv()
    print(f"Descargando {url}")
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENTE), timeout=180) as r:
        return r.read().decode("utf-8-sig", errors="replace")


def _monto(valor: str) -> str:
    try:
        return f"{float(valor):.0f}"
    except (TypeError, ValueError):
        return ""


def filtrar(texto_csv: str) -> list:
    filas = []
    for f in csv.DictReader(io.StringIO(texto_csv.lstrip("﻿"))):
        if f.get("cntry_cd") != "PE" or f.get("publc_sts_nm") not in ESTADOS:
            continue
        if (f.get("sector_nm") or "").strip() in SECTORES_FUERA:
            continue
        fila = {nuestra: (f.get(suya) or "").strip() for suya, nuestra in COLUMNAS.items()}
        fila = {k: "" if v.upper() in ("NULL", "NAN") else v for k, v in fila.items()}
        fila["aprobacion"] = fila["aprobacion"][:10]
        for clave in ("monto_bid_usd", "costo_total_usd", "contrapartida_usd"):
            fila[clave] = _monto(fila[clave])
        filas.append(fila)
    return sorted(filas, key=lambda x: x["aprobacion"], reverse=True)


def guardar(filas: list, destino: Path = DESTINO) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(COLUMNAS.values()))
        escritor.writeheader()
        escritor.writerows(filas)


def main(argv):
    texto = Path(argv[1]).read_text(encoding="utf-8-sig", errors="replace") if len(argv) > 1 else descargar()
    filas = filtrar(texto)
    if not filas:
        sys.exit("No quedó ningún proyecto: revisa si cambió el formato del CSV del BID.")
    guardar(filas)
    print(f"{len(filas)} proyectos de Perú guardados en {DESTINO.relative_to(RAIZ)} ({date.today()})")


if __name__ == "__main__":
    main(sys.argv)
