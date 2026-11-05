"""Plan Pro: genera la propuesta técnica y económica en tres modos."""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from ai.documentos import Recuperador, descargar_tdr, leer_documento, trocear  # noqa: E402
from ai.exportar import a_excel, a_word, etiqueta_fuente, huella_autoria  # noqa: E402
from ai.generador import MODOS, extraer_reglas, generar_propuesta  # noqa: E402
from ai.reglas import SIMBOLOS, calcular_presupuesto, reglas_efectivas, validar_matriz  # noqa: E402

st.set_page_config(page_title="Generar propuesta", page_icon="✨", layout="wide")


@st.cache_data
def cargar_json(ruta):
    with open(RAIZ / ruta, encoding="utf-8") as f:
        return json.load(f)


FORMATO = cargar_json("data/formatos/formato_base.json")
CASO = cargar_json("data/casos/caso_demo.json")
PREVIA = RAIZ / "data" / "casos" / "propuesta_previa_ficticia.docx"
ICONO = {"ok": "✅", "alerta": "⚠️", "error": "❌"}
estado = st.session_state

st.title("✨ Generar propuesta técnica y económica")
st.caption("Plan Pro · Borrador para revisar y completar: la propuesta final es de tu organización.")

# ---------------------------------------------------------------- Paso 1: convocatoria y TdR
conv = estado.get("convocatoria")
st.subheader("1. Convocatoria y términos de referencia")
if conv:
    st.markdown(f"**{conv['title']}** · {conv['donor']} · cierra: {conv['deadline'] or 'ventanilla abierta'}")
else:
    st.info("No elegiste una convocatoria del boletín. Sube el TdR o las bases, o usa el formato base.")

col_a, col_b = st.columns(2)
with col_a:
    if conv and conv.get("links"):
        enlaces = {l["label"]: l["url"] for l in conv["links"]}
        etiqueta = st.selectbox("Leer el TdR desde el enlace de la convocatoria", list(enlaces))
        if st.button("📥 Descargar y leer TdR", width="stretch"):
            with st.spinner("Descargando y leyendo el TdR…"):
                try:
                    estado.tdr_texto = descargar_tdr(enlaces[etiqueta])
                    estado.tdr_fuente = etiqueta
                except Exception as error:
                    st.error(f"No se pudo descargar ({error}). Sube el archivo a la derecha.")
with col_b:
    archivo = st.file_uploader("…o sube el TdR / bases (PDF, Word, Excel)", type=["pdf", "docx", "xlsx", "txt", "html"])
    if archivo and st.button("📄 Leer archivo subido", width="stretch"):
        estado.tdr_texto = leer_documento(archivo.name, archivo.getvalue())
        estado.tdr_fuente = archivo.name

if estado.get("tdr_texto") and estado.get("tdr_leido") != estado.get("tdr_fuente"):
    with st.spinner("Extrayendo las reglas del TdR…"):
        ficha = json.dumps({k: conv.get(k) for k in ["title", "donor", "type", "amount", "eligibility", "topic"]},
                           ensure_ascii=False) if conv else ""
        try:
            estado.reglas_tdr = extraer_reglas(estado.tdr_texto, ficha)
            estado.tdr_leido = estado.tdr_fuente
        except Exception as error:
            st.error(f"El modelo de IA no respondió: {error}")

reglas_tdr = estado.get("reglas_tdr")
if reglas_tdr:
    simbolo = SIMBOLOS.get(reglas_tdr.moneda, reglas_tdr.moneda)
    pct = lambda v: f"{v:.0%}" if v is not None else "no indica"  # noqa: E731
    monto = lambda v: f"{simbolo} {v:,.0f}" if v else "no indica"  # noqa: E731
    with st.container(border=True):
        st.markdown(f"**Reglas leídas del TdR** ({estado.tdr_fuente}): {reglas_tdr.objetivo}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Monto máximo", monto(reglas_tdr.monto_max))
        c2.metric("Duración máxima", f"{reglas_tdr.duracion_max_meses} meses" if reglas_tdr.duracion_max_meses else "no indica")
        c3.metric("Contrapartida mínima", pct(reglas_tdr.contrapartida_min_pct))
        c4.metric("Cierre", reglas_tdr.fecha_cierre or "no indica")
        with st.expander("Ver todas las reglas extraídas"):
            st.json(reglas_tdr.model_dump())
    if st.button("Quitar TdR y usar el formato base BMZ"):
        for k in ("tdr_texto", "tdr_fuente", "tdr_leido", "reglas_tdr"):
            estado.pop(k, None)
        st.rerun()
else:
    st.caption("Sin TdR: se usan las reglas del formato base (BMZ: hasta 75% de financiamiento, 12% administrativos, reserva 3.5%).")

# ---------------------------------------------------------------- Paso 2: modo
st.subheader("2. ¿Cómo quieres empezar?")
descripciones = {
    "tdr": "La IA lee el TdR y te propone un proyecto completo como **guía para empezar**.",
    "previos": "Subes propuestas anteriores y la IA **reutiliza tus ideas y tu estilo** siguiendo el nuevo TdR.",
    "entrevista": "Respondes preguntas por sección y la IA redacta **solo con tus respuestas**.",
}
modo = st.radio("Modo", list(MODOS), format_func=lambda m: MODOS[m], horizontal=True, label_visibility="collapsed")
st.markdown(descripciones[modo])

col_org, col_idea = st.columns(2)
organizacion = col_org.text_input("Tu organización (nombre y en qué trabaja)",
                                  placeholder="Asociación Juventud Emprende Norte (ficticia), ONG de Chiclayo")
idea = col_idea.text_input("Tu idea en una línea (opcional)",
                           placeholder="Emprendimiento juvenil con capital semilla y voluntariado en Chiclayo")

recuperador, respuestas = None, None
if modo == "previos":
    previas = st.file_uploader("Propuestas anteriores (PDF, Word o Excel)", type=["pdf", "docx", "xlsx"],
                               accept_multiple_files=True)
    usar_ejemplo = st.checkbox("Usar la propuesta anterior de ejemplo (ficticia)", value=not previas)
    fragmentos = []
    for f in previas or []:
        fragmentos += trocear(f.name, leer_documento(f.name, f.getvalue()))
    if usar_ejemplo:
        fragmentos += trocear(PREVIA.name, leer_documento(PREVIA.name, PREVIA.read_bytes()))
    if fragmentos:
        recuperador = Recuperador(fragmentos)
        st.caption(f"📚 {len(fragmentos)} fragmentos listos para consultar.")

if modo == "entrevista":
    def rellenar_ejemplo():
        for qid, texto in CASO["respuestas"].items():
            estado[f"resp_{qid}"] = texto

    st.button("Rellenar con el caso de ejemplo (ficticio)", on_click=rellenar_ejemplo)
    respuestas = {}
    for seccion in FORMATO["secciones"]:
        with st.expander(seccion["titulo"]):
            st.caption(seccion["proposito"])
            for pregunta in seccion["preguntas"]:
                respuestas[pregunta["id"]] = st.text_area(pregunta["texto"], key=f"resp_{pregunta['id']}", height=80)
    respondidas = sum(1 for v in respuestas.values() if v.strip())
    st.progress(respondidas / len(respuestas), text=f"{respondidas} de {len(respuestas)} preguntas respondidas")

listo = not (modo == "previos" and recuperador is None) and not (modo == "entrevista" and not any(
    v.strip() for v in (respuestas or {}).values()))
if st.button("✨ Generar propuesta", type="primary", disabled=not listo, width="stretch"):
    with st.status("Generando la propuesta…", expanded=True) as status:
        try:
            propuesta = generar_propuesta(
                modo, FORMATO, reglas_tdr=reglas_tdr, texto_tdr=estado.get("tdr_texto", ""), idea=idea,
                organizacion=organizacion, respuestas=respuestas, recuperador=recuperador,
                al_avanzar=lambda paso, total, msg: status.update(label=f"[{paso}/{total}] {msg}"),
            )
            estado.propuesta = propuesta
            status.update(label="Propuesta lista", state="complete", expanded=False)
        except Exception as error:
            status.update(label="No se pudo generar", state="error")
            st.error(f"El modelo de IA no respondió. Intenta de nuevo en un minuto. Detalle: {error}")

# ---------------------------------------------------------------- Paso 3: resultado
propuesta = estado.get("propuesta")
if not propuesta:
    st.stop()

reglas = reglas_efectivas(FORMATO, reglas_tdr)
resumen, chequeos_pre = calcular_presupuesto(propuesta["presupuesto"], reglas)
chequeos = chequeos_pre + validar_matriz(propuesta["matriz"], reglas, resumen["solicitado"])
simbolo = SIMBOLOS.get(resumen["moneda"], resumen["moneda"])

st.divider()
st.subheader(f"3. {propuesta['textos'].titulo_proyecto}")
st.caption(f"Modo: {MODOS[propuesta['modo']]} · Reglas: {reglas['origen']}")

errores = sum(1 for n, _ in chequeos if n == "error")
alertas = sum(1 for n, _ in chequeos if n == "alerta")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total del proyecto", f"{simbolo} {resumen['total']:,.0f}")
m2.metric("Monto solicitado", f"{simbolo} {resumen['solicitado']:,.0f}")
m3.metric("Aporte propio", f"{resumen['pct_propio']:.1%}")
m4.metric("Semáforo", "❌ Corregir" if errores else ("⚠️ Revisar" if alertas else "✅ Cumple"),
          f"{errores} errores · {alertas} alertas", delta_color="off")

convocatoria_txt = conv["title"] if conv else (reglas_tdr.nombre_convocatoria if reglas_tdr else "")
d1, d2 = st.columns(2)
d1.download_button("⬇️ Propuesta técnica (Word)", a_word(propuesta, FORMATO, convocatoria_txt, resumen),
                   file_name="propuesta_tecnica.docx", width="stretch",
                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
d2.download_button("⬇️ Propuesta económica (Excel)", a_excel(propuesta, resumen, reglas),
                   file_name="propuesta_economica.xlsx", width="stretch",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

tab_reglas, tab_tecnica, tab_matriz, tab_pre, tab_huella = st.tabs(
    ["🚦 Reglas del donante", "📝 Propuesta técnica", "🎯 Matriz de impacto", "💰 Presupuesto", "🖐️ Huella de autoría"])

with tab_reglas:
    for nivel, mensaje in sorted(chequeos, key=lambda c: ["error", "alerta", "ok"].index(c[0])):
        st.markdown(f"{ICONO[nivel]} {mensaje}")

with tab_tecnica:
    titulos = {s["id"]: s["titulo"] for s in FORMATO["secciones"]}
    for seccion in propuesta["textos"].secciones:
        st.markdown(f"#### {titulos.get(seccion.seccion_id, seccion.seccion_id)}")
        for parrafo in seccion.parrafos:
            st.markdown(parrafo.texto)
            st.caption("📌 " + " · ".join(etiqueta_fuente(f) for f in parrafo.fuentes))
        for pendiente in seccion.pendientes:
            st.warning(f"Pendiente: {pendiente}")

with tab_matriz:
    m = propuesta["matriz"]
    if m.objetivo_superior:
        st.markdown(f"**Objetivo superior:** {m.objetivo_superior}")
    st.markdown(f"**Objetivo del proyecto:** {m.objetivo_proyecto}")
    filas = [{"Nivel": "Proyecto", "Código": i.codigo, "Indicador": i.indicador, "Línea de base": i.linea_base,
              "Meta": i.meta, "Medio de verificación": i.medio_verificacion} for i in m.indicadores_proyecto]
    for oe in m.objetivos_especificos:
        filas += [{"Nivel": f"{oe.codigo}: {oe.texto}", "Código": i.codigo, "Indicador": i.indicador,
                   "Línea de base": i.linea_base, "Meta": i.meta, "Medio de verificación": i.medio_verificacion}
                  for i in oe.indicadores]
    st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
    actividades = [{"Objetivo": oe.codigo, "Actividad": f"{a.codigo} {a.descripcion}", "Inicio": a.mes_inicio,
                    "Fin": a.mes_fin} for oe in m.objetivos_especificos for a in oe.actividades]
    st.markdown("**Actividades y cronograma**")
    st.dataframe(pd.DataFrame(actividades), hide_index=True, width="stretch")

with tab_pre:
    tabla = pd.DataFrame([{
        "Objetivo": l["objetivo"], "Categoría": l["categoria"], "Descripción": l["descripcion"],
        "Cantidad": l["cantidad"], "Costo unitario": l["costo_unitario"], "Total": l["total"],
        "Origen": ", ".join(etiqueta_fuente(f) for f in l["fuentes"]),
    } for l in resumen["lineas"]])
    st.dataframe(tabla, hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(format="%.0f") for c in ["Costo unitario", "Total"]})
    st.markdown(
        f"Gastos: **{simbolo} {resumen['gastos']:,.0f}** · Reserva: {simbolo} {resumen['reserva']:,.0f} · "
        f"Administrativos: {simbolo} {resumen['administrativos']:,.0f} · **Total: {simbolo} {resumen['total']:,.0f}**")
    for a in propuesta["presupuesto"].aportes_propios:
        st.markdown(f"- Aporte de {a.fuente} ({a.tipo}): {simbolo} {a.monto:,.0f}")

with tab_huella:
    st.markdown("De dónde salió cada párrafo, indicador y línea de presupuesto de este borrador:")
    huella = huella_autoria(propuesta)
    st.bar_chart(pd.DataFrame({"Piezas": huella}), horizontal=True)
    st.caption("Mientras más pese «Tus respuestas» y «Tus propuestas previas», más tuya es la propuesta.")
