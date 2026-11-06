"""Plan Pro: genera la propuesta técnica y económica en tres modos."""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from ai import enaho, fondoempleo, historial  # noqa: E402
from ai.auditor import auditar_presupuesto, chequeos_auditoria, evaluar, puntaje_total  # noqa: E402
from ai.documentos import Recuperador, descargar_archivo_tdr, leer_documento, trocear  # noqa: E402
from ai.esquemas import Aporte, LineaPresupuesto, Parrafo  # noqa: E402
from ai.exportar import a_excel, a_word, etiqueta_fuente, huella_autoria  # noqa: E402
from ai.generador import MODOS, extraer_reglas, generar_propuesta, regenerar_seccion  # noqa: E402
from ai.llm import resumen_costo  # noqa: E402
from ai.reglas import SIMBOLOS, calcular_presupuesto, reglas_efectivas, validar_matriz  # noqa: E402
from ai.tipo_cambio import factor, soles_por  # noqa: E402
from ai.verificador import verificar  # noqa: E402
from ai.voz import analizar_audio, transcribir  # noqa: E402

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


def abrir_propuesta(propuesta):
    """Pone una propuesta en pantalla y renueva las claves de los editores."""
    estado.propuesta = propuesta
    estado.version = estado.get("version", 0) + 1


with st.sidebar:
    st.markdown("### 📂 Historial")
    guardadas = historial.listar()
    if not guardadas:
        st.caption("Aún no hay propuestas guardadas.")
    else:
        opciones = {f"{titulo[:45]} · {fecha[:16].replace('T', ' ')}": ruta for ruta, titulo, fecha, _ in guardadas}
        elegida = st.selectbox("Propuestas guardadas", list(opciones), label_visibility="collapsed")
        if st.button("Abrir propuesta", width="stretch"):
            abrir_propuesta(historial.abrir(opciones[elegida]))
            st.rerun()
        st.caption(f"{len(guardadas)} propuesta(s) en tu computadora (carpeta historial/).")

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
        etiqueta = st.selectbox("Enlace de la convocatoria", list(enlaces))
        st.link_button("🔗 Abrir la página original", enlaces[etiqueta], width="stretch")
        if st.button("📥 Leer TdR desde el enlace", width="stretch",
                     help="La app descarga el TdR, lo lee y extrae sus reglas: monto, plazo, topes y criterios."):
            with st.spinner("Descargando y leyendo el TdR…"):
                try:
                    archivo_tdr = descargar_archivo_tdr(enlaces[etiqueta])
                    estado.tdr_texto = archivo_tdr["texto"]
                    estado.tdr_fuente = etiqueta
                    estado.tdr_archivo = archivo_tdr if archivo_tdr["es_documento"] else None
                except Exception as error:
                    st.error(f"No se pudo descargar ({error}). Ábrelo con el botón de arriba y súbelo a la derecha.")
        if estado.get("tdr_archivo"):
            arch = estado.tdr_archivo
            st.download_button(f"⬇️ Guardar el TdR en mi computadora ({arch['nombre']})", arch["contenido"],
                               file_name=arch["nombre"], mime=arch["mime"], width="stretch")
        elif estado.get("tdr_fuente") == etiqueta:
            st.caption("Este enlace es una página web, no un PDF: ábrela con «Abrir la página original».")
with col_b:
    archivo = st.file_uploader("…o sube el TdR / bases (PDF, Word, Excel)", type=["pdf", "docx", "xlsx", "txt", "html"])
    if archivo and st.button("📄 Leer archivo subido", width="stretch"):
        estado.tdr_texto = leer_documento(archivo.name, archivo.getvalue())
        estado.tdr_fuente = archivo.name
        estado.tdr_archivo = None

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
        for k in ("tdr_texto", "tdr_fuente", "tdr_leido", "reglas_tdr", "tdr_archivo"):
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

lista_dep = enaho.departamentos()
if lista_dep:
    sugerido = enaho.detectar(idea, organizacion, conv.get("scope", "") if conv else "")
    codigos = [""] + [c for c, _ in lista_dep]
    nombres = dict(lista_dep)
    dep = st.selectbox(f"Departamento del proyecto (datos de la ENAHO {enaho.ANIO} para el problema)", codigos,
                       index=codigos.index(sugerido) if sugerido in codigos else 0,
                       format_func=lambda c: nombres.get(c, "Sin datos de la ENAHO"))
    datos_publicos = enaho.contexto(dep)
    if datos_publicos:
        with st.expander("Ver los datos de la ENAHO que se usarán"):
            st.text(datos_publicos)
else:
    datos_publicos = ""

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

    def procesar_voz(contenido):
        """Transcribe y devuelve (texto, mensaje para el usuario, nivel)."""
        nivel = analizar_audio(contenido)
        dur, pico = nivel["duracion"], nivel["pico"]
        print(f"[voz] {len(contenido)} bytes · {dur} s · pico {pico} · rms {nivel['rms']}", flush=True)
        if pico is not None and pico < 0.01:
            return "", (f"La grabación ({dur:.1f} s) llegó en silencio: Chrome está usando un micrófono que no te "
                        "capta. Cámbialo en el ícono de la barra de direcciones → Micrófono."), "error"
        try:
            texto = transcribir(contenido)
        except Exception as error:
            return "", f"Whisper falló: {error}", "error"
        print(f"[voz] texto: {texto!r}", flush=True)
        if not texto:
            return "", (f"Grabé {dur or 0:.1f} s con volumen bajo (pico {pico or 0:.0%}) y no reconocí palabras. "
                        "Acércate al micrófono o revisa cuál usa Chrome."), "alerta"
        return texto, f"Transcrito ({dur or 0:.1f} s): «{texto}»", "ok"

    st.button("Rellenar con el caso de ejemplo (ficticio)", on_click=rellenar_ejemplo)
    st.caption("Responde escribiendo o con 🎙️: tu nota de voz se transcribe con Whisper en esta computadora; "
               "el audio no se envía a internet.")

    with st.expander("🎙️ Probar micrófono"):
        st.caption("Graba 3 a 5 segundos diciendo cualquier frase. Verás el volumen y lo que entendió Whisper.")
        prueba = st.audio_input("Prueba de micrófono", key="voz_prueba")
        if prueba is not None:
            datos = analizar_audio(prueba.getvalue())
            with st.spinner("Transcribiendo con Whisper…"):
                texto, mensaje, nivel_msg = procesar_voz(prueba.getvalue())
            c1, c2 = st.columns(2)
            c1.metric("Duración", f"{datos['duracion'] or 0:.1f} s")
            c2.metric("Volumen máximo", f"{datos['pico'] or 0:.0%}",
                      help="Por debajo de 1% es silencio: el micrófono elegido en Chrome no te escucha.")
            {"ok": st.success, "alerta": st.warning, "error": st.error}[nivel_msg](mensaje)

    respuestas = {}
    for seccion in FORMATO["secciones"]:
        with st.expander(seccion["titulo"]):
            st.caption(seccion["proposito"])
            for pregunta in seccion["preguntas"]:
                qid = pregunta["id"]
                col_texto, col_voz = st.columns([7, 1], vertical_alignment="bottom")
                # La voz se procesa antes de dibujar el cuadro de texto para poder escribir en él.
                with col_voz.popover("🎙️", help="Responder por voz"):
                    audio = st.audio_input("Graba tu respuesta", key=f"voz_{qid}")
                if audio is not None:
                    contenido = audio.getvalue()
                    huella = hash(contenido)
                    if estado.get(f"voz_hecha_{qid}") != huella:
                        with st.spinner("Transcribiendo con Whisper…"):
                            texto, mensaje, nivel_msg = procesar_voz(contenido)
                        if texto:
                            previo = estado.get(f"resp_{qid}", "").strip()
                            estado[f"resp_{qid}"] = f"{previo} {texto}".strip()
                        estado[f"voz_hecha_{qid}"] = huella
                        # Solo se avisa si hubo un problema; si salió bien, el texto ya está en el cuadro.
                        if nivel_msg == "ok":
                            estado.pop(f"voz_msg_{qid}", None)
                        else:
                            estado[f"voz_msg_{qid}"] = (nivel_msg, mensaje)
                respuestas[qid] = col_texto.text_area(pregunta["texto"], key=f"resp_{qid}", height=80)
                if f"voz_msg_{qid}" in estado:
                    nivel_msg, mensaje = estado[f"voz_msg_{qid}"]
                    {"alerta": st.warning, "error": st.error}[nivel_msg](mensaje)
    respondidas = sum(1 for v in respuestas.values() if v.strip())
    st.progress(respondidas / len(respuestas), text=f"{respondidas} de {len(respuestas)} preguntas respondidas")


listo = not (modo == "previos" and recuperador is None) and not (modo == "entrevista" and not any(
    v.strip() for v in (respuestas or {}).values()))
if st.button("✨ Generar propuesta", type="primary", disabled=not listo, width="stretch"):
    with st.status("Generando la propuesta…", expanded=True) as status:
        try:
            nueva = generar_propuesta(
                modo, FORMATO, reglas_tdr=reglas_tdr, texto_tdr=estado.get("tdr_texto", ""), idea=idea,
                organizacion=organizacion, respuestas=respuestas, recuperador=recuperador,
                datos_publicos=datos_publicos,
                al_avanzar=lambda paso, total, msg: status.update(label=f"[{paso}/{total}] {msg}"),
            )
            if reglas_tdr is not None:
                status.update(label="Revisando el presupuesto contra el TdR…")
                nueva["auditoria"], llamadas = auditar_presupuesto(nueva["presupuesto"], reglas_tdr)
                nueva["llamadas"] += llamadas
            nueva["convocatoria"] = conv["title"] if conv else (reglas_tdr.nombre_convocatoria if reglas_tdr else "")
            historial.guardar(nueva)
            abrir_propuesta(nueva)
            status.update(label="Propuesta lista y guardada en el historial", state="complete", expanded=False)
        except Exception as error:
            status.update(label="No se pudo generar", state="error")
            st.error(f"El modelo de IA no respondió. Intenta de nuevo en un minuto o abre una propuesta del "
                     f"historial. Detalle: {error}")

# ---------------------------------------------------------------- Paso 3: resultado
propuesta = estado.get("propuesta")
if not propuesta:
    st.stop()

version = estado.get("version", 0)
reglas_prop = propuesta.get("reglas_tdr")
reglas = reglas_efectivas(FORMATO, reglas_prop)
resumen, chequeos = calcular_presupuesto(propuesta["presupuesto"], reglas, conversor=factor)
chequeos += validar_matriz(propuesta["matriz"], reglas, resumen["solicitado"])
chequeos += chequeos_auditoria(propuesta.get("auditoria"), resumen, reglas_prop) if reglas_prop else []
hallazgos = verificar(propuesta, resumen)
simbolo = SIMBOLOS.get(resumen["moneda"], resumen["moneda"])
try:
    tc_usd = soles_por("USD")
except Exception:
    tc_usd = None
costo = resumen_costo(propuesta.get("llamadas", []), tc_usd["valor"] if tc_usd else None)


def guardar_y_recargar():
    historial.guardar(propuesta)
    estado.version = estado.get("version", 0) + 1
    st.rerun()


st.divider()
st.subheader(f"3. {propuesta['textos'].titulo_proyecto}")
st.caption(f"Modo: {MODOS[propuesta['modo']]} · Reglas: {reglas['origen']} · "
           f"Guardada en el historial: {propuesta.get('archivo', '')}")

errores = sum(1 for n, _ in chequeos if n == "error")
alertas = sum(1 for n, _ in chequeos if n == "alerta") + (1 if hallazgos else 0)
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total del proyecto", f"{simbolo} {resumen['total']:,.0f}")
m2.metric("Monto solicitado", f"{simbolo} {resumen['solicitado']:,.0f}")
m3.metric("Aporte propio", f"{resumen['pct_propio']:.1%}")
m4.metric("Semáforo", "❌ Corregir" if errores else ("⚠️ Revisar" if alertas else "✅ Cumple"),
          f"{errores} errores · {alertas} alertas", delta_color="off")
m5.metric("Puntaje estimado", f"{puntaje_total(propuesta['evaluacion']):.0%}" if propuesta.get("evaluacion") else "—")

notas = []
if resumen["moneda"] != "PEN":
    try:
        tc = soles_por(resumen["moneda"])
        notas.append(f"Total ≈ S/ {resumen['total'] * tc['valor']:,.0f} (1 {resumen['moneda']} = S/ {tc['valor']:.3f}, "
                     f"{tc['fuente']}, {tc['fecha']})")
    except Exception:
        pass
notas.append(f"Costo de IA de esta propuesta: US$ {costo['costo_usd']:.3f}"
             + (f" (S/ {costo['costo_pen']:.2f})" if costo["costo_pen"] is not None else "")
             + f" · {costo['llamadas']} llamadas · {costo['tokens_entrada'] + costo['tokens_salida']:,} tokens")
st.caption(" · ".join(notas))

d1, d2 = st.columns(2)
d1.download_button("⬇️ Propuesta técnica (Word)", a_word(propuesta, FORMATO, propuesta.get("convocatoria", ""), resumen),
                   file_name="propuesta_tecnica.docx", width="stretch",
                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
d2.download_button("⬇️ Propuesta económica (Excel)", a_excel(propuesta, resumen, reglas),
                   file_name="propuesta_economica.xlsx", width="stretch",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with st.expander("📑 Exportar en formato Fondoempleo (Formatos 02 y 03)"):
    st.caption("Adapta esta propuesta a la estructura de Fondoempleo y revisa sus reglas en soles: monto por línea, "
               "duración, equipo ≤ 25 %, contrapartida ≥ 10 %, equipamiento ≤ 2 UIT y gastos no financiables.")
    linea_fe = st.radio("Línea", ["capacitacion_laboral", "fortalecimiento_organizacional"], horizontal=True,
                        format_func=lambda x: fondoempleo.REGLAS["lineas"][x]["nombre"], key=f"linea_fe_{version}")
    if st.button("Adaptar al formato Fondoempleo" if not propuesta.get("fondoempleo") else "Volver a adaptar"):
        with st.spinner("Adaptando a los Formatos 02 y 03…"):
            try:
                propuesta["fondoempleo"], llamadas = fondoempleo.adaptar(propuesta, linea_fe)
                propuesta.setdefault("llamadas", []).extend(llamadas)
                guardar_y_recargar()
            except Exception as error:
                st.error(f"El modelo de IA no respondió: {error}")
    adaptacion = propuesta.get("fondoempleo")
    if adaptacion is not None:
        try:
            factor_soles = factor(propuesta["presupuesto"].moneda, "PEN")
        except Exception:
            factor_soles = None
        if factor_soles is None:
            st.error("No se pudo obtener el tipo de cambio para pasar el presupuesto a soles.")
        else:
            calculo_fe = fondoempleo.calcular(propuesta, adaptacion, factor_soles)
            for nivel, mensaje in fondoempleo.chequeos(calculo_fe, adaptacion):
                st.markdown(f"{ICONO[nivel]} {mensaje}")
            e1, e2 = st.columns(2)
            e1.download_button("⬇️ Formato 02 (Word)", fondoempleo.a_word_formato02(propuesta, adaptacion),
                               file_name="formato_02_fondoempleo.docx", width="stretch",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            e2.download_button("⬇️ Formato 03 (Excel)", fondoempleo.a_excel_formato03(propuesta, calculo_fe),
                               file_name="formato_03_fondoempleo.xlsx", width="stretch",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

tab_rev, tab_tecnica, tab_matriz, tab_pre, tab_huella = st.tabs(
    ["🚦 Revisión", "📝 Propuesta técnica", "🎯 Matriz de impacto", "💰 Presupuesto", "🖐️ Huella de autoría"])

# ---------- Revisión: reglas, cifras y puntaje
with tab_rev:
    st.markdown("##### Reglas del donante")
    for nivel, mensaje in sorted(chequeos, key=lambda c: ["error", "alerta", "ok"].index(c[0])):
        st.markdown(f"{ICONO[nivel]} {mensaje}")

    st.markdown("##### 🔎 Cifras a validar")
    if hallazgos:
        st.caption("Estos números no aparecen en tus respuestas, tus documentos, el TdR ni el presupuesto. "
                   "Pueden ser propuestas de la IA: confírmalos o corrígelos.")
        for h in hallazgos:
            st.markdown(f"- **{h['cifra']}** · {h['seccion']} · _{h['fragmento']}_")
    else:
        st.markdown("✅ Todas las cifras del borrador tienen respaldo en tus fuentes.")

    st.markdown("##### 📊 Puntaje estimado")
    if st.button("Calcular puntaje con los criterios del donante" if not propuesta.get("evaluacion")
                 else "Volver a calcular el puntaje"):
        with st.spinner("Evaluando como lo haría el comité del donante…"):
            try:
                propuesta["evaluacion"], llamadas = evaluar(propuesta, FORMATO, resumen)
                propuesta.setdefault("llamadas", []).extend(llamadas)
                guardar_y_recargar()
            except Exception as error:
                st.error(f"El modelo de IA no respondió: {error}")
    evaluacion = propuesta.get("evaluacion")
    if evaluacion:
        st.dataframe(pd.DataFrame([{"Criterio": c.criterio, "Puntaje": f"{c.puntaje}/4", "Por qué": c.justificacion,
                                    "Cómo subirlo": c.mejora} for c in evaluacion.criterios]),
                     hide_index=True, width="stretch")
        f1, f2 = st.columns(2)
        f1.markdown("**Fortalezas**\n" + "\n".join(f"- {x}" for x in evaluacion.fortalezas))
        f2.markdown("**Debilidades**\n" + "\n".join(f"- {x}" for x in evaluacion.debilidades))
        st.caption("Estimación de la IA con los criterios del TdR; no reemplaza la evaluación real del donante.")

# ---------- Propuesta técnica: editable y regenerable por sección
with tab_tecnica:
    titulos = {s["id"]: s["titulo"] for s in FORMATO["secciones"]}
    st.caption("Edita directamente cada sección. Separa los párrafos con una línea en blanco. "
               "Lo que guardes aquí es lo que sale en el Word.")
    ediciones = {}
    for seccion in propuesta["textos"].secciones:
        sid = seccion.seccion_id
        original = "\n\n".join(p.texto for p in seccion.parrafos)
        ediciones[sid] = st.text_area(titulos.get(sid, sid), value=original, key=f"edit_{version}_{sid}",
                                      height=max(150, min(450, len(original) // 3)))
        fuentes = dict.fromkeys(etiqueta_fuente(f) for p in seccion.parrafos for f in p.fuentes)
        st.caption("📌 " + " · ".join(fuentes))
        for pendiente in seccion.pendientes:
            st.warning(f"Pendiente: {pendiente}")
        with st.popover("🔄 Regenerar esta sección con una instrucción"):
            instruccion = st.text_input("¿Qué quieres cambiar?", key=f"instr_{version}_{sid}",
                                        placeholder="Ej.: agrega un enfoque de género y acorta a 3 párrafos")
            if st.button("Regenerar", key=f"regen_{version}_{sid}", disabled=not instruccion):
                with st.spinner("Reescribiendo…"):
                    try:
                        regenerar_seccion(propuesta, FORMATO, sid, instruccion)
                        guardar_y_recargar()
                    except Exception as error:
                        st.error(f"El modelo de IA no respondió: {error}")

    if st.button("💾 Guardar cambios de la propuesta técnica", type="primary"):
        for seccion in propuesta["textos"].secciones:
            texto = ediciones[seccion.seccion_id].strip()
            if texto == "\n\n".join(p.texto for p in seccion.parrafos):
                continue
            previos = {p.texto: p.fuentes for p in seccion.parrafos}
            seccion.parrafos = [Parrafo(texto=t.strip(), fuentes=previos.get(t.strip(), ["USUARIO"]))
                                for t in texto.split("\n\n") if t.strip()]
        guardar_y_recargar()

# ---------- Matriz de impacto: editable
with tab_matriz:
    m = propuesta["matriz"]
    sup = st.text_area("Objetivo superior", value=m.objetivo_superior or "", key=f"sup_{version}", height=70)
    obj = st.text_area("Objetivo del proyecto", value=m.objetivo_proyecto, key=f"obj_{version}", height=70)
    filas = [{"Nivel": "Proyecto", "Código": i.codigo, "Indicador": i.indicador, "Línea de base": i.linea_base,
              "Meta": i.meta, "Medio de verificación": i.medio_verificacion} for i in m.indicadores_proyecto]
    for oe in m.objetivos_especificos:
        filas += [{"Nivel": f"{oe.codigo}: {oe.texto}", "Código": i.codigo, "Indicador": i.indicador,
                   "Línea de base": i.linea_base, "Meta": i.meta, "Medio de verificación": i.medio_verificacion}
                  for i in oe.indicadores]
    tabla_ind = st.data_editor(pd.DataFrame(filas), hide_index=True, width="stretch", key=f"ind_{version}",
                               disabled=["Nivel", "Código"])
    actividades = [{"Objetivo": oe.codigo, "Código": a.codigo, "Actividad": a.descripcion, "Inicio (mes)": a.mes_inicio,
                    "Fin (mes)": a.mes_fin} for oe in m.objetivos_especificos for a in oe.actividades]
    st.markdown("**Actividades y cronograma**")
    tabla_act = st.data_editor(pd.DataFrame(actividades), hide_index=True, width="stretch", key=f"act_{version}",
                               disabled=["Objetivo", "Código"])
    if st.button("💾 Guardar cambios de la matriz", type="primary"):
        m.objetivo_superior, m.objetivo_proyecto = sup.strip() or None, obj.strip()
        por_codigo = {i.codigo: i for i in list(m.indicadores_proyecto) +
                      [i for oe in m.objetivos_especificos for i in oe.indicadores]}
        for _, fila in tabla_ind.iterrows():
            ind = por_codigo.get(fila["Código"])
            nuevos = (fila["Indicador"], fila["Línea de base"], fila["Meta"], fila["Medio de verificación"])
            if ind and nuevos != (ind.indicador, ind.linea_base, ind.meta, ind.medio_verificacion):
                ind.indicador, ind.linea_base, ind.meta, ind.medio_verificacion = nuevos
                ind.fuentes = list(dict.fromkeys(ind.fuentes + ["USUARIO"]))
        acts = {a.codigo: a for oe in m.objetivos_especificos for a in oe.actividades}
        for _, fila in tabla_act.iterrows():
            a = acts.get(fila["Código"])
            if a:
                a.descripcion = fila["Actividad"]
                a.mes_inicio, a.mes_fin = int(fila["Inicio (mes)"]), int(fila["Fin (mes)"])
        guardar_y_recargar()

# ---------- Presupuesto: editable
with tab_pre:
    pres = propuesta["presupuesto"]
    st.caption(f"Edita cantidades, costos o agrega filas (montos en {pres.moneda}). Totales, reserva, gastos "
               f"administrativos y topes se recalculan solos.")
    categorias = list(FORMATO["reglas"]["categorias_gasto"])
    tabla_lin = st.data_editor(
        pd.DataFrame([{"Objetivo": l.objetivo, "Categoría": l.categoria, "Descripción": l.descripcion,
                       "Unidad": l.unidad, "Cantidad": l.cantidad, "Costo unitario": l.costo_unitario}
                      for l in pres.lineas]),
        num_rows="dynamic", hide_index=True, width="stretch", key=f"lin_{version}",
        column_config={"Categoría": st.column_config.SelectboxColumn(options=categorias),
                       "Cantidad": st.column_config.NumberColumn(min_value=0, format="%.1f"),
                       "Costo unitario": st.column_config.NumberColumn(min_value=0, format="%.2f")})
    st.markdown("**Aportes propios** (organización, socios, municipalidad…)")
    tabla_ap = st.data_editor(
        pd.DataFrame([{"Fuente": a.fuente, "Tipo": a.tipo, "Monto": a.monto} for a in pres.aportes_propios]),
        num_rows="dynamic", hide_index=True, width="stretch", key=f"ap_{version}",
        column_config={"Tipo": st.column_config.SelectboxColumn(options=["monetario", "especie"]),
                       "Monto": st.column_config.NumberColumn(min_value=0, format="%.2f")})
    st.markdown(
        f"Gastos: **{simbolo} {resumen['gastos']:,.0f}** · Reserva: {simbolo} {resumen['reserva']:,.0f} · "
        f"Administrativos: {simbolo} {resumen['administrativos']:,.0f} · **Total: {simbolo} {resumen['total']:,.0f}** · "
        f"Solicitado: {simbolo} {resumen['solicitado']:,.0f}")
    if st.button("💾 Guardar cambios del presupuesto", type="primary"):
        previas = {(l.descripcion, l.cantidad, l.costo_unitario): l.fuentes for l in pres.lineas}
        nuevas = []
        for _, f in tabla_lin.dropna(subset=["Descripción"]).iterrows():
            clave = (str(f["Descripción"]), float(f["Cantidad"] or 0), float(f["Costo unitario"] or 0))
            nuevas.append(LineaPresupuesto(
                objetivo=str(f["Objetivo"] or "GEN"), categoria=str(f["Categoría"] or "operativos"),
                descripcion=clave[0], unidad=str(f["Unidad"] or "unidad"), cantidad=clave[1],
                costo_unitario=clave[2], fuentes=previas.get(clave, ["USUARIO"])))
        pres.lineas = nuevas
        pres.aportes_propios = [Aporte(fuente=str(f["Fuente"]), tipo=str(f["Tipo"] or "monetario"),
                                       monto=float(f["Monto"] or 0), fuentes=["USUARIO"])
                                for _, f in tabla_ap.dropna(subset=["Fuente"]).iterrows()]
        if reglas_prop is not None:
            with st.spinner("Revisando de nuevo contra el TdR…"):
                try:
                    propuesta["auditoria"], llamadas = auditar_presupuesto(pres, reglas_prop)
                    propuesta.setdefault("llamadas", []).extend(llamadas)
                except Exception:
                    st.warning("No se pudo revisar contra el TdR ahora; los topes generales sí se recalcularon.")
        guardar_y_recargar()

# ---------- Huella de autoría (solo en la app)
with tab_huella:
    st.markdown("De dónde salió cada párrafo, indicador y línea de presupuesto de este borrador:")
    st.bar_chart(pd.DataFrame({"Piezas": huella_autoria(propuesta)}), horizontal=True)
    st.caption("Mientras más pesen «Tus respuestas» y «Tus propuestas previas», más tuya es la propuesta. "
               "Las ediciones que guardas cuentan como tuyas. Esta información no aparece en el Word ni en el Excel.")
