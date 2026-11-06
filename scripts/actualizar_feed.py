"""Acumula los reportes diarios de convocatorias en data/convocatorias/reportes.json.

Uso:
    python scripts/actualizar_feed.py RUTA [RUTA ...]

RUTA puede ser el HTML del artefacto «Convocatorias DEL Perú» (se extrae el bloque
<script id="report-data">) o un JSON con la forma {"reports": [...]}.

- Agrega los días nuevos y reemplaza un día si llega una versión más reciente.
- Nunca borra días anteriores: el archivo es el historial completo del feed.
- Valida cada reporte (fecha y campos mínimos) antes de guardarlo.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "data" / "convocatorias" / "reportes.json"
CAMPOS_ITEM = {"title", "donor", "type", "deadline", "links"}
_BLOQUE = re.compile(r'<script id="report-data" type="application/json">(.*?)</script>', re.S)


def leer_reportes(ruta: Path) -> list:
    texto = ruta.read_text(encoding="utf-8")
    m = _BLOQUE.search(texto)
    datos = json.loads(m.group(1) if m else texto)
    return datos["reports"]


def validar(reporte: dict) -> list:
    """Devuelve la lista de problemas del reporte (vacía si está bien)."""
    problemas = []
    try:
        date.fromisoformat(reporte.get("date", ""))
    except ValueError:
        problemas.append(f"fecha inválida: {reporte.get('date')!r}")
    if not isinstance(reporte.get("items"), list):
        problemas.append("sin lista de items")
    else:
        for i, item in enumerate(reporte["items"]):
            faltan = CAMPOS_ITEM - set(item)
            if faltan:
                problemas.append(f"item {i} sin {sorted(faltan)}")
    return problemas


def combinar(actuales: list, nuevos: list) -> tuple:
    """Une por fecha (lo nuevo reemplaza lo viejo) y ordena del más reciente al más antiguo."""
    por_fecha = {r["date"]: r for r in actuales}
    agregados, actualizados = [], []
    for r in nuevos:
        if r["date"] not in por_fecha:
            agregados.append(r["date"])
        elif por_fecha[r["date"]] != r:
            actualizados.append(r["date"])
        por_fecha[r["date"]] = r
    combinados = sorted(por_fecha.values(), key=lambda r: r["date"], reverse=True)
    return combinados, agregados, actualizados


def main(rutas, destino: Path = DESTINO) -> int:
    actuales = json.loads(destino.read_text(encoding="utf-8"))["reports"] if destino.exists() else []
    nuevos = []
    for ruta in rutas:
        for reporte in leer_reportes(Path(ruta)):
            problemas = validar(reporte)
            if problemas:
                print(f"Se omite el reporte {reporte.get('date')}: {'; '.join(problemas)}")
                continue
            nuevos.append(reporte)
    combinados, agregados, actualizados = combinar(actuales, nuevos)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({"reports": combinados}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Días en el historial: {len(combinados)} · nuevos: {agregados or 'ninguno'} · "
          f"actualizados: {actualizados or 'ninguno'} · más reciente: {combinados[0]['date'] if combinados else '-'}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
