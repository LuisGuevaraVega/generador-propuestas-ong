"""Historial de propuestas: guarda y abre propuestas generadas como archivos JSON.

Sirve para no perder el trabajo al recargar la página y como respaldo del demo
si el modelo de IA está saturado. La carpeta `historial/` no se sube a GitHub
porque puede tener información de la organización.
"""
import json
import re
from datetime import datetime
from pathlib import Path

from ai.esquemas import (AuditoriaPresupuesto, Evaluacion, MatrizImpacto, Presupuesto, ReglasConvocatoria,
                         TextosPropuesta)

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "historial"
MODELOS = {"textos": TextosPropuesta, "matriz": MatrizImpacto, "presupuesto": Presupuesto,
           "reglas_tdr": ReglasConvocatoria, "auditoria": AuditoriaPresupuesto, "evaluacion": Evaluacion}


def _a_json(propuesta: dict) -> dict:
    salida = {}
    for clave, valor in propuesta.items():
        salida[clave] = valor.model_dump() if hasattr(valor, "model_dump") else valor
    return salida


def _desde_json(datos: dict) -> dict:
    propuesta = dict(datos)
    for clave, modelo in MODELOS.items():
        if propuesta.get(clave) is not None:
            propuesta[clave] = modelo.model_validate(propuesta[clave])
    return propuesta


def _nombre_archivo(propuesta: dict) -> str:
    titulo = propuesta["textos"].titulo_proyecto.lower()
    titulo = re.sub(r"[^a-z0-9áéíóúñ]+", "-", titulo).strip("-")[:50]
    return f"{datetime.now():%Y%m%d-%H%M%S}_{titulo}.json"


def guardar(propuesta: dict, carpeta: Path = CARPETA) -> Path:
    """Guarda la propuesta. Si ya tiene archivo, lo sobrescribe (para guardar ediciones)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = propuesta.get("archivo") or _nombre_archivo(propuesta)
    propuesta["archivo"] = nombre
    propuesta["actualizado"] = datetime.now().isoformat(timespec="seconds")
    propuesta.setdefault("creado", propuesta["actualizado"])
    ruta = carpeta / nombre
    ruta.write_text(json.dumps(_a_json(propuesta), ensure_ascii=False, indent=1), encoding="utf-8")
    return ruta


def abrir(ruta) -> dict:
    return _desde_json(json.loads(Path(ruta).read_text(encoding="utf-8")))


def listar(carpeta: Path = CARPETA):
    """Devuelve [(ruta, título, fecha, modo)] de la más reciente a la más antigua."""
    if not carpeta.exists():
        return []
    filas = []
    for ruta in sorted(carpeta.glob("*.json"), reverse=True):
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            filas.append((ruta, datos["textos"]["titulo_proyecto"], datos.get("actualizado", ""), datos.get("modo", "")))
        except (json.JSONDecodeError, KeyError):
            continue
    return filas
