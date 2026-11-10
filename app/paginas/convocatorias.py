"""Versión gratuita: convocatorias del día en tarjetas compactas."""
import json
import sys
import unicodedata
from datetime import date
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parents[2]
REPORTES = RAIZ / "data" / "convocatorias" / "reportes.json"
sys.path.insert(0, str(RAIZ))

from ai.temas import sugeridos, temas_de  # noqa: E402

st.markdown("<style>[data-testid='stMainBlockContainer']{max-width:980px}</style>", unsafe_allow_html=True)


@st.cache_data
def cargar_reportes():
    with open(REPORTES, encoding="utf-8") as f:
        return json.load(f)["reports"]


def dias_restantes(deadline: str, hoy: date):
    if not deadline:
        return None
    return (date.fromisoformat(deadline) - hoy).days


def normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower()


def plazo(dias):
    """Texto y color del plazo: rojo si cierra en una semana, naranja en tres."""
    if dias is None:
        return "Ventanilla abierta", "blue"
    if dias < 0:
        return "Cerrada", "gray"
    if dias == 0:
        return "Cierra hoy", "red"
    if dias == 1:
        return "Cierra mañana", "red"
    color = "red" if dias <= 7 else "orange" if dias <= 21 else "green"
    return f"Cierra en {dias} días", color


reportes = cargar_reportes()
fechas = [r["date"] for r in reportes]

cab, sel = st.columns([3, 1], vertical_alignment="bottom")
cab.title("Convocatorias para ONG en Perú")
cab.caption("Desarrollo económico local · actualizado cada mañana · versión gratuita")
fecha = sel.selectbox("Boletín del día", fechas, help=f"{len(fechas)} días guardados en el historial")
reporte = next(r for r in reportes if r["date"] == fecha)
hoy = date.fromisoformat(fecha)

with st.expander("📰 Resumen del día", expanded=False):
    st.write(reporte["summary"])

buscar, abiertas = st.columns([3.8, 1], vertical_alignment="center")
texto = buscar.text_input("Buscar", placeholder="Buscar por tema, donante o lugar…", label_visibility="collapsed")
solo_abiertas = abiertas.toggle("Solo abiertas", value=True)

vigentes = [item for item in reporte["items"]
            if not (solo_abiertas and (d := dias_restantes(item.get("deadline"), hoy)) is not None and d < 0)]
conteo = sugeridos(vigentes)
elegidos = st.pills("Temáticas", list(conteo), selection_mode="multi", format_func=lambda t: f"{t} · {conteo[t]}",
                    help="Temáticas que aparecen en este boletín. Elige una o varias para ver solo esas.")

items = []
for item in vigentes:
    dias = dias_restantes(item.get("deadline"), hoy)
    campos = " ".join(str(item.get(k, "")) for k in ("title", "donor", "topic", "scope", "type", "amount")).lower()
    if texto and normalizar(texto) not in normalizar(campos):
        continue
    if elegidos and not set(elegidos) & set(temas_de(item)):
        continue
    items.append((dias if dias is not None else 10_000, item))
items.sort(key=lambda par: par[0])

st.caption(f"{len(items)} convocatoria(s) · ordenadas por fecha de cierre")
if not items and elegidos:
    st.info("No hay convocatorias de esas temáticas con ese filtro. Prueba con otro día en «Boletín del día».")
elif not items:
    st.info("No hay convocatorias con ese filtro.")

for dias, item in items:
    dias = None if dias == 10_000 else dias
    texto_plazo, color = plazo(dias)
    with st.container(border=True):
        izquierda, derecha = st.columns([4, 1.3], vertical_alignment="center")
        with izquierda:
            with st.container(horizontal=True, gap="small"):
                st.badge(texto_plazo, color=color, icon=":material/schedule:")
                if item.get("isNew"):
                    st.badge("Nueva", color="violet")
                st.badge(item["type"].split("(")[0].strip(), color="gray")
            st.markdown(f"#### {item['title']}")
            st.markdown(f"**{item['donor']}** · {item['amount'].split(';')[0]}")
        with derecha:
            if st.button("✨ Generar propuesta", key=f"gen-{fecha}-{item['title'][:40]}", type="primary",
                         width="stretch", help="Plan Pro: arma el borrador técnico y económico"):
                st.session_state["convocatoria"] = item
                for clave in ("tdr_texto", "tdr_fuente", "tdr_leido", "reglas_tdr", "tdr_archivo", "tdr_error",
                              "tdr_intentados", "enlace_tdr", "propuesta"):
                    st.session_state.pop(clave, None)
                st.session_state["paso"] = 1
                st.switch_page("paginas/generar.py")
        with st.expander("Ver detalles"):
            st.markdown(f"_{item['why']}_")
            st.markdown(f"**Monto y plazo:** {item['amount']}")
            st.markdown(f"**Quién puede postular:** {item['eligibility']}")
            if item.get("topic") or item.get("scope"):
                st.markdown(f"**Tema:** {item.get('topic', '—')} · **Ámbito:** {item.get('scope', '—')}")
            if item.get("deadlineNote"):
                st.markdown(f"**Sobre el plazo:** {item['deadlineNote']}")
            st.markdown(" · ".join(f"[{l['label']}]({l['url']})" for l in item.get("links", [])))
