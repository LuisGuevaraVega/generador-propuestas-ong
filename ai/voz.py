"""Voz a texto con Whisper (sesión 13), corriendo en la propia computadora.

Usamos faster-whisper (Whisper de OpenAI optimizado con CTranslate2) en CPU.
El audio de la organización no sale de la laptop: solo el texto transcrito
pasa luego al modelo de redacción.
"""
import io
import os
from functools import lru_cache

# Vocabulario del sector para que Whisper escriba bien siglas y términos técnicos
VOCABULARIO = (
    "ONG, TdR, términos de referencia, BMZ, Fondoempleo, CETPRO, capital semilla, mentoría, marco lógico, "
    "línea de base, indicadores, emprendimiento, empleabilidad, voluntariado juvenil, municipalidad, "
    "Chiclayo, Lambayeque, José Leonardo Ortiz, La Victoria, soles, euros."
)


@lru_cache(maxsize=1)
def _modelo():
    from faster_whisper import WhisperModel

    tamano = os.environ.get("WHISPER_MODEL", "base")
    return WhisperModel(tamano, device="cpu", compute_type="int8")


def transcribir(audio: bytes, idioma: str = "es") -> str:
    """Convierte una nota de voz (wav, mp3, ogg, m4a…) en texto en español."""
    segmentos, _info = _modelo().transcribe(
        io.BytesIO(audio),
        language=idioma,
        initial_prompt=VOCABULARIO,
        vad_filter=True,  # ignora silencios largos
        beam_size=5,
    )
    return " ".join(s.text.strip() for s in segmentos).strip()
