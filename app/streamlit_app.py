"""Punto de entrada: menú superior con las dos páginas de la app.

- Convocatorias (gratis): el boletín diario.
- Generar propuesta (Pro): asistente de 3 pasos.
"""
import streamlit as st

st.set_page_config(page_title="Convocatorias y propuestas", page_icon="📋", layout="wide")
# Menos espacio en blanco arriba de cada página, y cifras de las tarjetas que nunca se cortan con "…".
st.markdown("""<style>
[data-testid='stMainBlockContainer']{padding-top:2.5rem}
[data-testid='stMetricValue']{font-size:1.7rem}
[data-testid='stMetricValue'] *{overflow:visible !important;text-overflow:clip !important;white-space:normal !important}
</style>""", unsafe_allow_html=True)

paginas = [
    st.Page("paginas/convocatorias.py", title="Convocatorias", icon="📋", default=True),
    st.Page("paginas/generar.py", title="Generar propuesta", icon="✨"),
]
st.navigation(paginas, position="top").run()
