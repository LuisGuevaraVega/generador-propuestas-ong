"""Punto de entrada: menú superior con las dos páginas de la app.

- Convocatorias (gratis): el boletín diario.
- Generar propuesta (Pro): asistente de 3 pasos.
"""
import streamlit as st

st.set_page_config(page_title="Convocatorias y propuestas", page_icon="📋", layout="wide")
# Menos espacio en blanco arriba de cada página.
st.markdown("<style>[data-testid='stMainBlockContainer']{padding-top:2.5rem}</style>", unsafe_allow_html=True)

paginas = [
    st.Page("paginas/convocatorias.py", title="Convocatorias", icon="📋", default=True),
    st.Page("paginas/generar.py", title="Generar propuesta", icon="✨"),
]
st.navigation(paginas, position="top").run()
