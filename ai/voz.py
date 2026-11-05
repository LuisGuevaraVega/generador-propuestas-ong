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


def analizar_audio(audio: bytes) -> dict:
    """Duración y volumen de una grabación WAV, para avisar si llegó en silencio."""
    import array
    import io
    import wave

    try:
        with wave.open(io.BytesIO(audio)) as w:
            frames, tasa, ancho = w.readframes(w.getnframes()), w.getframerate(), w.getsampwidth()
            duracion = w.getnframes() / float(tasa or 1)
    except Exception:
        return {"duracion": None, "pico": None, "rms": None}
    if ancho != 2 or not frames:
        return {"duracion": duracion, "pico": None, "rms": None}
    muestras = array.array("h", frames)
    pico = max(abs(m) for m in muestras) / 32768
    rms = (sum(m * m for m in muestras) / len(muestras)) ** 0.5 / 32768
    return {"duracion": duracion, "pico": pico, "rms": rms}


def transcribir(audio: bytes, idioma: str = "es", tiempo_max: int = 180) -> str:
    """Convierte una nota de voz (wav, mp3, ogg, m4a…) en texto, en un proceso aparte."""
    pico = analizar_audio(audio)["pico"]
    if pico is not None and pico < 0.01:  # silencio: Whisper inventaría texto
        return ""
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
    # Primero con filtro de voz (ignora silencios); si descarta todo, por ejemplo
    # porque la voz llegó con poco volumen, se reintenta sin el filtro.
    for filtro in (True, False):
        segmentos, _info = modelo.transcribe(
            ruta, language=idioma, initial_prompt=VOCABULARIO if filtro else None, vad_filter=filtro, beam_size=5
        )
        texto = " ".join(s.text.strip() for s in segmentos).strip()
        if texto and texto not in VOCABULARIO:  # evita devolver el vocabulario como "alucinación"
            return texto
    return ""


if __name__ == "__main__":
    print(_transcribir_aqui(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "es"))
