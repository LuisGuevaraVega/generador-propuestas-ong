"""Versión gratuita: convocatorias del día en tarjetas compactas."""
import json
import unicodedata
from datetime import date
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parents[2]
REPORTES = RAIZ / "data" / "convocatorias" / "reportes.json"

st.markdown("<style>[data-testid='stMainBlockContainer']{max-width:980px}</style>", unsafe_allow_html=True)


@st.cache_data
def cargar_reportes():
    with open(REPORTES, encoding="utf-8") as f:
        return json.load(f)["reports"]


def dias_restantes(deadline: str, hoy: date):
    if not deadline:
        return None
    return (date.fromisoformat(deadline) - hoy).days


# Palabras que identifican una convocatoria de microfinanzas (sin tildes, en minúsculas).
MICROFINANZAS = ("microfinanz", "microcredit", "microfinance", "inclusion financiera", "financial inclusion",
                 "inclusive finance", "finanzas inclusivas", "educacion financiera", "financial education",
                 "financial capability", "bancos comunales", "banca comunal", "grupos de ahorro", "savings group",
                 "vsla", "unicas", "ahorro y credito", "caja municipal", "cajas municipales", "caja rural",
                 "edpyme", "fintech", "remesas", "seguros inclusivos")


def normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower()


def es_microfinanzas(item) -> bool:
    campos = normalizar(" ".join(str(item.get(k, "")) for k in ("title", "topic", "type", "why", "amount")))
    return any(palabra in campos for palabra in MICROFINANZAS)


def plazo(dias):
    """Texto y color del plazo: rojo si cierra en una semana, naranja en tres."""
    if dias is None:
        return "Ventanilla abierta", "blue"
    if dias < 0:
        return "Cerrada", "gray"
    if dias == 0:
        return "Cierra hoy", "red"
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

buscar, tema, abiertas = st.columns([2.6, 1.2, 1], vertical_alignment="center")
texto = buscar.text_input("Buscar", placeholder="Buscar por tema, donante o lugar…", label_visibility="collapsed")
solo_micro = tema.pills("Tema", ["💰 Microfinanzas"], label_visibility="collapsed") is not None
solo_abiertas = abiertas.toggle("Solo abiertas", value=True)

items = []
for item in reporte["items"]:
    dias = dias_restantes(item.get("deadline"), hoy)
    if solo_abiertas and dias is not None and dias < 0:
        continue
    campos = " ".join(str(item.get(k, "")) for k in ("title", "donor", "topic", "scope", "type", "amount")).lower()
    if texto and normalizar(texto) not in normalizar(campos):
        continue
    if solo_micro and not es_microfinanzas(item):
        continue
    items.append((dias if dias is not None else 10_000, item))
items.sort(key=lambda par: par[0])

st.caption(f"{len(items)} convocatoria(s) · ordenadas por fecha de cierre")
if not items and solo_micro:
    st.info("Este boletín no tiene convocatorias de microfinanzas. Prueba con otro día en «Boletín del día».")
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
