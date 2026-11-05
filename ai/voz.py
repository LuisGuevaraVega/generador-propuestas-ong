"""Voz a texto con Whisper (sesión 13), corriendo en la propia computadora.

Usamos faster-whisper (Whisper de OpenAI optimizado con CTranslate2) en CPU.
El audio de la organización no sale de la laptop: solo el texto transcrito
pasa luego al modelo de redacción.

Whisper corre en un proceso aparte: en Windows, CTranslate2 choca con la
librería OpenMP que ya cargaron numpy y scikit-learn dentro de Streamlit y
el programa se cae (access violation). Aislarlo evita ese choque.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Vocabulario del sector para que Whisper escriba bien siglas y términos técnicos
VOCABULARIO = (
    "ONG, TdR, términos de referencia, BMZ, Fondoempleo, CETPRO, capital semilla, mentoría, marco lógico, "
    "línea de base, indicadores, emprendimiento, empleabilidad, voluntariado juvenil, municipalidad, "
    "Chiclayo, Lambayeque, José Leonardo Ortiz, La Victoria, soles, euros."
)


def transcribir(audio: bytes, idioma: str = "es", tiempo_max: int = 180) -> str:
    """Convierte una nota de voz (wav, mp3, ogg, m4a…) en texto, en un proceso aparte."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as archivo:
        archivo.write(audio)
        ruta = archivo.name
    try:
        entorno = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        resultado = subprocess.run(
            [sys.executable, "-m", "ai.voz", ruta, idioma],
            cwd=RAIZ, capture_output=True, timeout=tiempo_max, env=entorno,
        )
        if resultado.returncode != 0:
            detalle = resultado.stderr.decode("utf-8", errors="ignore").strip().splitlines()[-1:]
            raise RuntimeError(f"Whisper no pudo transcribir: {detalle}")
        return resultado.stdout.decode("utf-8").strip()
    finally:
        os.unlink(ruta)


def _transcribir_aqui(ruta: str, idioma: str) -> str:
    from faster_whisper import WhisperModel

    modelo = WhisperModel(os.environ.get("WHISPER_MODEL", "base"), device="cpu", compute_type="int8")
    segmentos, _info = modelo.transcribe(
        ruta, language=idioma, initial_prompt=VOCABULARIO, vad_filter=True, beam_size=5
    )
    return " ".join(s.text.strip() for s in segmentos).strip()


if __name__ == "__main__":
    print(_transcribir_aqui(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "es"))
