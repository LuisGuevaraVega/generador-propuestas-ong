"""Cliente de Gemini con salidas estructuradas, modelos de respaldo y medición de costo.

Si el modelo principal responde 503 (saturado) o 429 (límite), se prueba la
cadena de modelos de respaldo para que el demo no se caiga.

Cada llamada registra sus tokens en el "medidor" activo, para saber cuánto
cuesta generar una propuesta (dato del modelo de negocio).
"""
import json
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


def _leer_config(nombre, por_defecto=None):
    """Lee primero variables de entorno (.env) y luego st.secrets (Streamlit Cloud)."""
    valor = os.environ.get(nombre)
    if valor:
        return valor
    try:
        import streamlit as st

        return st.secrets.get(nombre, por_defecto)
    except Exception:
        return por_defecto


MODELO = _leer_config("GEMINI_MODEL", "gemini-3.6-flash")
RESPALDOS = [
    m.strip()
    for m in _leer_config("GEMINI_MODELOS_RESPALDO", "gemini-3.1-flash-lite,gemini-3-flash-preview").split(",")
    if m.strip()
]
MODELOS = [MODELO] + [m for m in RESPALDOS if m != MODELO]

with open(RAIZ / "data" / "precios_modelos.json", encoding="utf-8") as _f:
    PRECIOS = json.load(_f)

_cliente = None
_medidor: ContextVar = ContextVar("medidor", default=None)


def cliente():
    global _cliente
    if _cliente is None:
        clave = _leer_config("GEMINI_API_KEY")
        if not clave:
            raise RuntimeError("Falta GEMINI_API_KEY en el archivo .env")
        _cliente = genai.Client(api_key=clave)
    return _cliente


@contextmanager
def medir_costo():
    """Registra los tokens de todas las llamadas hechas dentro del bloque `with`."""
    llamadas = []
    token = _medidor.set(llamadas)
    try:
        yield llamadas
    finally:
        _medidor.reset(token)


def costo_usd(llamadas) -> float:
    """Costo en dólares según la tabla de precios (tokens de razonamiento se cobran como salida)."""
    total = 0.0
    for ll in llamadas:
        precio = PRECIOS["modelos"].get(ll["modelo"], PRECIOS["por_defecto"])
        salida = ll["salida"] + ll["razonamiento"]
        total += ll["entrada"] / 1e6 * precio["entrada"] + salida / 1e6 * precio["salida"]
    return total


def resumen_costo(llamadas, tipo_cambio_pen=None) -> dict:
    usd = costo_usd(llamadas)
    return {
        "llamadas": len(llamadas),
        "tokens_entrada": sum(ll["entrada"] for ll in llamadas),
        "tokens_salida": sum(ll["salida"] + ll["razonamiento"] for ll in llamadas),
        "costo_usd": round(usd, 4),
        "costo_pen": round(usd * tipo_cambio_pen, 3) if tipo_cambio_pen else None,
        "modelos": sorted({ll["modelo"] for ll in llamadas}),
    }


def _registrar(modelo, respuesta):
    llamadas = _medidor.get()
    uso = getattr(respuesta, "usage_metadata", None)
    if llamadas is None or uso is None:
        return
    llamadas.append({
        "modelo": modelo,
        "entrada": uso.prompt_token_count or 0,
        "salida": uso.candidates_token_count or 0,
        "razonamiento": getattr(uso, "thoughts_token_count", 0) or 0,
    })


def generar_estructurado(prompt: str, esquema, instrucciones: str, temperatura: float = 0.4):
    """Llama al modelo y devuelve una instancia del esquema Pydantic indicado."""
    config = types.GenerateContentConfig(
        system_instruction=instrucciones,
        response_mime_type="application/json",
        response_schema=esquema,
        temperature=temperatura,
    )
    ultimo_error = None
    for ronda in range(3):  # hasta 3 rondas por toda la cadena de modelos, con espera creciente
        for modelo in MODELOS:
            try:
                respuesta = cliente().models.generate_content(model=modelo, contents=prompt, config=config)
                _registrar(modelo, respuesta)
                if respuesta.parsed is not None:
                    return respuesta.parsed
                return esquema.model_validate_json(respuesta.text)
            except Exception as error:  # 503, 429 o JSON inválido: probar el respaldo
                ultimo_error = error
        time.sleep(3 * (ronda + 1))
    raise RuntimeError(f"No se pudo generar la respuesta: {ultimo_error}")
