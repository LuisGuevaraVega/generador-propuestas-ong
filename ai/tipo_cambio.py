"""Tipo de cambio desde la API pública del BCRP (scraping y APIs, sesión 03).

- Dólar y euro: series diarias del BCRP (soles por unidad, venta).
- Otras monedas (p. ej. dólar australiano): cruce con el euro del BCRP y la tasa
  del Banco Central Europeo (api.frankfurter.app).

El BCRP bloquea consultas muy seguidas, así que la última tasa se guarda en
`.cache/tipo_cambio.json` y se reutiliza durante el día o si la API falla.
"""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
CACHE = RAIZ / ".cache" / "tipo_cambio.json"
SERIES_BCRP = {"USD": "PD04640PD", "EUR": "PD04648PD"}
URL_BCRP = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{serie}/json/{inicio}/{fin}"
URL_BCE = "https://api.frankfurter.app/latest?from={de}&to=EUR"
CABECERAS = {"User-Agent": "Mozilla/5.0 GeneradorPropuestas/0.1"}


def _leer_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _escribir_cache(cache: dict):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")


def _bcrp(serie: str):
    """Último valor disponible de una serie diaria del BCRP en las últimas dos semanas."""
    fin = date.today()
    url = URL_BCRP.format(serie=serie, inicio=fin - timedelta(days=15), fin=fin)
    datos = requests.get(url, headers=CABECERAS, timeout=20).json()
    for periodo in reversed(datos["periods"]):
        valor = periodo["values"][0]
        if valor not in ("n.d.", ""):
            return float(valor), periodo["name"]
    raise ValueError(f"Serie {serie} sin datos recientes")


def soles_por(moneda: str) -> dict:
    """Devuelve {'valor': soles por 1 unidad, 'fecha', 'fuente'} o lanza error si no hay dato."""
    moneda = moneda.upper()
    if moneda == "PEN":
        return {"valor": 1.0, "fecha": str(date.today()), "fuente": "—"}
    cache = _leer_cache()
    guardado = cache.get(moneda)
    if guardado and guardado.get("consultado", "")[:10] == str(date.today()):
        return guardado
    try:
        if moneda in SERIES_BCRP:
            valor, fecha = _bcrp(SERIES_BCRP[moneda])
            fuente = f"BCRP serie {SERIES_BCRP[moneda]}"
        else:
            eur, fecha = _bcrp(SERIES_BCRP["EUR"])
            cruce = requests.get(URL_BCE.format(de=moneda), headers=CABECERAS, timeout=20).json()["rates"]["EUR"]
            valor, fuente = eur * cruce, f"BCRP (euro) × BCE ({moneda}→EUR)"
        resultado = {"valor": round(valor, 4), "fecha": fecha, "fuente": fuente,
                     "consultado": datetime.now().isoformat(timespec="seconds")}
        cache[moneda] = resultado
        _escribir_cache(cache)
        return resultado
    except Exception:
        if guardado:  # sin internet o API bloqueada: usar la última tasa conocida
            return {**guardado, "fuente": guardado["fuente"] + " (última tasa guardada)"}
        raise


def convertir(monto: float, de: str, a: str) -> float:
    """Convierte un monto entre monedas pasando por soles."""
    if de.upper() == a.upper():
        return monto
    return monto * soles_por(de)["valor"] / soles_por(a)["valor"]


def factor(de: str, a: str) -> float:
    return convertir(1.0, de, a)
