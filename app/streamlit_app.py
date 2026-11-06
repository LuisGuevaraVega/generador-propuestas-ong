"""Punto de entrada: menú superior con las dos páginas de la app.

- Convocatorias (gratis): el boletín diario.
- Generar propuesta (Pro): asistente de 2 pasos.

Si se configura APP_CLAVE (en .env o en los secretos de Streamlit Cloud), la app pide esa clave
antes de mostrarse: sirve para compartir el prototipo publicado solo con quien la tenga.
"""
import hmac
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ai.llm import _leer_config  # noqa: E402

st.set_page_config(page_title="Convocatorias y propuestas", page_icon="📋", layout="wide")
# Menos espacio en blanco arriba de cada página, y cifras de las tarjetas que nunca se cortan con "…".
st.markdown("""<style>
[data-testid='stMainBlockContainer']{padding-top:2.5rem}
[data-testid='stMetricValue']{font-size:1.7rem}
[data-testid='stMetricValue'] *{overflow:visible !important;text-overflow:clip !important;white-space:normal !important}
</style>""", unsafe_allow_html=True)

clave = _leer_config("APP_CLAVE")
if clave and not st.session_state.get("acceso_ok"):
    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        st.title("🔒 Prototipo privado")
        st.caption("Generador de propuestas técnicas y económicas para ONG · versión de prueba")
        intento = st.text_input("Clave de acceso", type="password", placeholder="Escriba la clave que le compartieron")
        if intento:
            if hmac.compare_digest(intento.strip(), str(clave)):
                st.session_state.acceso_ok = True
                st.rerun()
            st.error("La clave no es correcta.")
    st.stop()

paginas = [
    st.Page("paginas/convocatorias.py", title="Convocatorias", icon="📋", default=True),
    st.Page("paginas/generar.py", title="Generar propuesta", icon="✨"),
]
st.navigation(paginas, position="top").run()
