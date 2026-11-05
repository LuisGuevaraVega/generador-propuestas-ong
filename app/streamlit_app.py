"""App principal: convocatorias (gratis) y generador de propuestas (Pro).

Día 1: solo el feed de convocatorias. El generador se construye el fin de semana.
"""
import json
from datetime import date
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
REPORTES = RAIZ / "data" / "convocatorias" / "reportes.json"


@st.cache_data
def cargar_reportes():
    with open(REPORTES, encoding="utf-8") as f:
        return json.load(f)["reports"]


def dias_restantes(deadline: str, hoy: date):
    if not deadline:
        return None
    return (date.fromisoformat(deadline) - hoy).days


st.set_page_config(page_title="Convocatorias y propuestas", page_icon="📋", layout="centered")
st.title("Convocatorias para ONG en Perú")
st.caption("Versión gratuita: convocatorias de desarrollo económico local, actualizadas cada día.")

reportes = cargar_reportes()
fechas = [r["date"] for r in reportes]
fecha = st.selectbox("Reporte del día", fechas)
reporte = next(r for r in reportes if r["date"] == fecha)
hoy = date.fromisoformat(fecha)

st.info(reporte["summary"])

for item in reporte["items"]:
    with st.container(border=True):
        dias = dias_restantes(item["deadline"], hoy)
        cierre = "Ventanilla abierta" if dias is None else f"Cierra en {dias} días ({item['deadline']})"
        st.subheader(item["title"])
        st.markdown(f"**{item['donor']}** · {item['type']} · {cierre}")
        st.markdown(f"**Monto:** {item['amount']}")
        st.markdown(f"**Quién puede postular:** {item['eligibility']}")
        st.markdown(f"_{item['why']}_")
        st.markdown(" · ".join(f"[{l['label']}]({l['url']})" for l in item["links"]))
        st.button(
            "✨ Generar propuesta (Pro)",
            key=f"gen-{fecha}-{item['title'][:40]}",
            disabled=True,
            help="Próximamente: entrevista guiada para co-crear la propuesta técnica y económica.",
        )
