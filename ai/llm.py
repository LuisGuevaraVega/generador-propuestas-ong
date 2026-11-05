"""Cliente de Gemini con salidas estructuradas y modelo de respaldo.

Si el modelo principal responde 503 (saturado) o 429 (límite), se prueba la
cadena de modelos de respaldo para que el demo no se caiga.
"""
import os
import time
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


MODELO = _leer_config("GEMINI_MODEL", "gemini-3.5-flash")
RESPALDOS = [
    m.strip()
    for m in _leer_config("GEMINI_MODELOS_RESPALDO", "gemini-3.1-flash-lite,gemini-3-flash-preview").split(",")
    if m.strip()
]
MODELOS = [MODELO] + [m for m in RESPALDOS if m != MODELO]

_cliente = None


def cliente():
    global _cliente
    if _cliente is None:
        clave = _leer_config("GEMINI_API_KEY")
        if not clave:
            raise RuntimeError("Falta GEMINI_API_KEY en el archivo .env")
        _cliente = genai.Client(api_key=clave)
    return _cliente


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
                if respuesta.parsed is not None:
                    return respuesta.parsed
                return esquema.model_validate_json(respuesta.text)
            except Exception as error:  # 503, 429 o JSON inválido: probar el respaldo
                ultimo_error = error
        time.sleep(3 * (ronda + 1))
    raise RuntimeError(f"No se pudo generar la respuesta: {ultimo_error}")
