"""Plan Pro: asistente de 2 pasos para generar la propuesta técnica y económica.

1. Tu proyecto: la convocatoria con el resumen de su TdR (se lee solo), los datos de la organización
   y el modo de redacción (TdR, propuestas previas o entrevista).
2. Revisa y descarga: qué corregir, edición por partes y descargas.
"""
import json
import sys
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from ai import enaho, fondoempleo, historial, referencias  # noqa: E402
from ai.auditor import auditar_presupuesto, chequeos_auditoria, evaluar, puntaje_total  # noqa: E402
from ai.documentos import (MARCA_OCR, MAX_CARACTERES, Recuperador, descargar_archivo_tdr,  # noqa: E402
                           leer_documento, trocear)
from ai.esquemas import Aporte, LineaPresupuesto, Parrafo  # noqa: E402
from ai.exportar import a_excel, a_word, etiqueta_fuente, huella_autoria  # noqa: E402
from ai.generador import (MAX_FRAGMENTOS_PREVIOS, MODOS, extraer_reglas, generar_propuesta,  # noqa: E402
                          paginas, preparar_documentos_apoyo, regenerar_seccion, titulos_secciones)
from ai.llm import _leer_config, resumen_costo  # noqa: E402
from ai.reglas import SIMBOLOS, calcular_presupuesto, reglas_efectivas, validar_matriz  # noqa: E402
from ai.tipo_cambio import factor, soles_por  # noqa: E402
from ai.verificador import verificar  # noqa: E402
from ai.voz import analizar_audio, transcribir  # noqa: E402


@st.cache_data
def cargar_json(ruta):
    with open(RAIZ / ruta, encoding="utf-8") as f:
        return json.load(f)


FORMATO = cargar_json("data/formatos/formato_base.json")
CASO = cargar_json("data/casos/caso_demo.json")
PREVIA = RAIZ / "data" / "casos" / "propuesta_previa_ficticia.docx"
ICONO = {"ok": "✅", "alerta": "⚠️", "error": "❌"}
PASOS = ["Tu proyecto", "Revisa y descarga"]
CLAVES_TDR = ("tdr_texto", "tdr_fuente", "tdr_leido", "reglas_tdr", "tdr_archivo", "tdr_error")
WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
estado = st.session_state

# Streamlit borra el valor de un campo cuando no se dibuja. Al volver a asignarlo, las respuestas
# del paso 2 y las ediciones sin guardar sobreviven aunque cambies de paso o de sección.
for _clave in list(estado.keys()):
    if str(_clave).startswith(("w_", "resp_", "edit_")):
        estado[_clave] = estado[_clave]


def monto(simbolo, valor):
    """Monto corto para las tarjetas: los millones se abrevian para que la cifra no se corte."""
    if abs(valor) >= 1_000_000:
        return f"{simbolo} {valor / 1_000_000:,.1f} M"
    return f"{simbolo} {valor:,.0f}"


TIPOS_DOCUMENTO = ["pdf", "docx", "xlsx", "txt", "jpg", "jpeg", "png"]


@st.cache_data(show_spinner=False, max_entries=50)
def leer_cacheado(nombre, contenido):
    """Lee un archivo una sola vez: los escaneados y las fotos pasan por OCR (cuesta una llamada a la IA)."""
    return leer_documento(nombre, contenido)


def carpeta_historial():
    """En la versión publicada, cada visitante ve solo sus propuestas; en la laptop, el historial completo."""
    if _leer_config("HISTORIAL_POR_SESION") or _leer_config("APP_CLAVE"):
        if "id_sesion" not in estado:
            estado.id_sesion = uuid.uuid4().hex[:12]
        return historial.CARPETA / "sesiones" / estado.id_sesion
    return historial.CARPETA


def ir(paso):
    estado.paso = paso
    st.rerun()


def abrir_propuesta(propuesta):
    """Pone una propuesta en pantalla y renueva las claves de los editores."""
    estado.propuesta = propuesta
    estado.version = estado.get("version", 0) + 1
    estado.paso = 2


def nueva_propuesta():
    for clave in list(estado.keys()):
        if str(clave).startswith(("w_", "resp_", "edit_", "voz_")) or clave in CLAVES_TDR + (
                "propuesta", "convocatoria", "dep_sugerido", "tdr_intentados", "enlace_tdr"):
            del estado[clave]
    estado.paso = 1


# ---------------------------------------------------------------- Barra lateral
with st.sidebar:
    st.button("＋ Nueva propuesta", width="stretch", type="primary", on_click=nueva_propuesta)
    st.markdown("#### 📂 Mis propuestas")
    guardadas = historial.listar(carpeta_historial())
    if not guardadas:
        st.caption("Aún no hay propuestas guardadas.")
    else:
        opciones = {f"{titulo[:45]} · {fecha[:16].replace('T', ' ')}": ruta for ruta, titulo, fecha, _ in guardadas}
        elegida = st.selectbox("Propuestas guardadas", list(opciones), label_visibility="collapsed")
        if st.button("Abrir", width="stretch"):
            abrir_propuesta(historial.abrir(opciones[elegida]))
            st.rerun()
        donde = "en esta computadora" if carpeta_historial() == historial.CARPETA else "en esta sesión del navegador"
        st.caption(f"{len(guardadas)} guardada(s) {donde}.")

# ---------------------------------------------------------------- Cabecera y pasos
paso = estado.get("paso", 1)
if paso not in (1, 2) or (paso == 2 and not estado.get("propuesta")):
    paso = 1
# Mismo ancho en los dos pasos.
st.markdown("<style>[data-testid='stMainBlockContainer']{max-width:1000px}</style>", unsafe_allow_html=True)

st.title("✨ Generar propuesta")
st.caption("Plan Pro · Te entrega un borrador técnico y económico para revisar: la propuesta final es de tu "
           "organización.")
columnas = st.columns(len(PASOS))
for numero, nombre in enumerate(PASOS, 1):
    disponible = numero == 1 or estado.get("propuesta") is not None
    marca = "✓" if numero < paso else str(numero)
    if columnas[numero - 1].button(f"{marca} · {nombre}", key=f"ir_paso_{numero}", width="stretch",
                                   type="primary" if numero == paso else "secondary", disabled=not disponible):
        ir(numero)
st.write("")


# ---------------------------------------------------------------- Convocatoria y resumen del TdR
def enlaces_ordenados(conv):
    """Enlaces de la convocatoria, primero el que parece el TdR o las bases."""
    enlaces = {l["label"]: l["url"] for l in conv.get("links", [])} if conv else {}
    nombres = sorted(enlaces, key=lambda e: not (enlaces[e].lower().split("?")[0].endswith(".pdf") or any(
        p in e.lower() for p in ("tdr", "bases", "términos", "terminos", "convocatoria"))))
    return enlaces, nombres


def tarjeta_convocatoria():
    """Convocatoria elegida y resumen de su TdR. El TdR se lee solo al entrar."""
    conv = estado.get("convocatoria")
    enlaces, nombres = enlaces_ordenados(conv)
    with st.container(border=True):
        izq, der = st.columns([4, 1.3], vertical_alignment="center")
        with izq:
            if conv:
                st.markdown(f"**{conv['title']}**")
                st.caption(f"{conv['donor']} · cierra: {conv.get('deadline') or 'ventanilla abierta'}")
            else:
                st.markdown("**Sin convocatoria elegida**")
                st.caption("Se usa el formato base de la cooperación alemana (BMZ). Elige una convocatoria o sube "
                           "su TdR.")
        with der.popover("📄 Cambiar TdR" if conv else "📄 Subir TdR", width="stretch"):
            if not conv and st.button("📋 Elegir una convocatoria", width="stretch"):
                st.switch_page("paginas/convocatorias.py")
            if len(nombres) > 1:
                st.selectbox("Leer desde el enlace", nombres, key="enlace_tdr")
            archivo = st.file_uploader("Sube el TdR o las bases (PDF, Word, Excel)",
                                       type=TIPOS_DOCUMENTO + ["html"])
            if archivo and st.button("Leer este archivo", width="stretch"):
                with st.spinner("Leyendo el archivo (si es escaneado, con OCR)…"):
                    estado.tdr_texto = leer_cacheado(archivo.name, archivo.getvalue())
                estado.tdr_fuente = archivo.name
                estado.tdr_archivo = None
            if estado.get("reglas_tdr") and st.button("Quitar el TdR y usar el formato base", width="stretch"):
                for k in CLAVES_TDR:
                    estado.pop(k, None)
                st.rerun()

        etiqueta = estado.get("enlace_tdr") if len(nombres) > 1 else (nombres[0] if nombres else None)
        intentados = estado.setdefault("tdr_intentados", [])
        if etiqueta and etiqueta not in intentados and estado.get("tdr_fuente") != etiqueta:
            intentados.append(etiqueta)
            with st.spinner("Leyendo el TdR de la convocatoria…"):
                try:
                    archivo_tdr = descargar_archivo_tdr(enlaces[etiqueta])
                    estado.tdr_texto = archivo_tdr["texto"]
                    estado.tdr_fuente = etiqueta
                    estado.tdr_archivo = archivo_tdr if archivo_tdr["es_documento"] else None
                    estado.pop("tdr_error", None)
                except Exception:
                    estado.tdr_error = etiqueta

        if estado.get("tdr_texto") and estado.get("tdr_leido") != estado.get("tdr_fuente"):
            with st.spinner("Resumiendo las reglas del TdR…"):
                ficha = json.dumps({k: conv.get(k) for k in ["title", "donor", "type", "amount", "eligibility",
                                                             "topic"]}, ensure_ascii=False) if conv else ""
                try:
                    estado.reglas_tdr = extraer_reglas(estado.tdr_texto, ficha)
                    estado.tdr_leido = estado.tdr_fuente
                except Exception as error:
                    st.error(f"El modelo de IA no respondió al leer el TdR: {error}")

        reglas_tdr = estado.get("reglas_tdr")
        if reglas_tdr:
            simbolo = SIMBOLOS.get(reglas_tdr.moneda, reglas_tdr.moneda)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Monto máximo", monto(simbolo, reglas_tdr.monto_max) if reglas_tdr.monto_max else "No indica")
            c2.metric("Duración máxima",
                      f"{reglas_tdr.duracion_max_meses} meses" if reglas_tdr.duracion_max_meses else "No indica")
            c3.metric("Contrapartida mínima", f"{reglas_tdr.contrapartida_min_pct:.0%}"
                      if reglas_tdr.contrapartida_min_pct is not None else "No indica")
            c4.metric("Cierre", reglas_tdr.fecha_cierre or "No indica")
            st.caption(f"Resumen del TdR ({estado.tdr_fuente}, ~{paginas(len(estado.tdr_texto))} pág.). "
                       "La propuesta se ajusta a estas reglas.")
            if len(estado.tdr_texto) > MAX_CARACTERES:
                st.warning(f"El TdR es muy largo: la IA lee sus primeras ~{paginas(MAX_CARACTERES)} páginas.")
        elif estado.get("tdr_error"):
            st.warning("No se pudo leer el TdR desde el enlace. Ábrelo y súbelo con «Cambiar TdR».")
        elif conv:
            st.caption("No se encontró un TdR: la propuesta sigue el formato base (BMZ).")

        if (enlaces and etiqueta) or estado.get("tdr_archivo"):
            with st.container(horizontal=True):
                if enlaces and etiqueta:
                    st.link_button("🔗 Abrir la página original", enlaces[etiqueta])
                if estado.get("tdr_archivo"):
                    arch = estado.tdr_archivo
                    st.download_button("⬇️ Guardar el TdR", arch["contenido"], file_name=arch["nombre"],
                                       mime=arch["mime"])


# ---------------------------------------------------------------- Paso 1: tu proyecto
DESCRIPCION_MODO = {
    "tdr": "La IA arma un primer borrador completo con el TdR. Puedes sumar CVs y proyectos anteriores.",
    "previos": "Subes propuestas anteriores y la IA reutiliza tus ideas y tu estilo.",
    "entrevista": "Respondes preguntas cortas, escribiendo o hablando, y la IA redacta con tus respuestas.",
}


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


def rellenar_ejemplo():
    for qid, texto in CASO["respuestas"].items():
        estado[f"resp_{qid}"] = texto


def pregunta_con_voz(pregunta):
    """Cuadro de texto con botón de micrófono; la voz se escribe dentro del cuadro."""
    qid = pregunta["id"]
    col_texto, col_voz = st.columns([9, 1], vertical_alignment="bottom")
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
            if nivel_msg == "ok":
                estado.pop(f"voz_msg_{qid}", None)
            else:
                estado[f"voz_msg_{qid}"] = (nivel_msg, mensaje)
    respuesta = col_texto.text_area(pregunta["texto"], key=f"resp_{qid}", height=80)
    if f"voz_msg_{qid}" in estado:
        nivel_msg, mensaje = estado[f"voz_msg_{qid}"]
        {"alerta": st.warning, "error": st.error}[nivel_msg](mensaje)
    return respuesta


def panel_entrevista():
    preguntas = [p for s in FORMATO["secciones"] for p in s["preguntas"]]
    respondidas = sum(1 for p in preguntas if estado.get(f"resp_{p['id']}", "").strip())
    st.progress(respondidas / len(preguntas), text=f"{respondidas} de {len(preguntas)} preguntas respondidas · "
                                                    "no hace falta responder todas")
    with st.container(horizontal=True):
        st.button("Rellenar con el caso de ejemplo", on_click=rellenar_ejemplo,
                  help="Respuestas de una ONG ficticia, para probar")
        with st.popover("🎙️ Probar micrófono"):
            st.caption("Graba 3 a 5 segundos. Verás el volumen y lo que entendió Whisper. El audio se transcribe "
                       "en esta computadora y no se envía a internet.")
            prueba = st.audio_input("Prueba de micrófono", key="voz_prueba")
            if prueba is not None:
                datos = analizar_audio(prueba.getvalue())
                with st.spinner("Transcribiendo con Whisper…"):
                    _, mensaje, nivel_msg = procesar_voz(prueba.getvalue())
                st.metric("Volumen máximo", f"{datos['pico'] or 0:.0%}",
                          help="Por debajo de 1 % es silencio: el micrófono elegido en Chrome no te escucha.")
                {"ok": st.success, "alerta": st.warning, "error": st.error}[nivel_msg](mensaje)

    secciones = FORMATO["secciones"]
    etiquetas = []
    for seccion in secciones:
        hechas = sum(1 for p in seccion["preguntas"] if estado.get(f"resp_{p['id']}", "").strip())
        marca = "✓ " if hechas == len(seccion["preguntas"]) else ""
        corto = seccion["titulo"].split(" y ")[0]
        etiquetas.append(f"{marca}{corto} ({hechas}/{len(seccion['preguntas'])})")
    respuestas = {}
    for pestana, seccion in zip(st.tabs(etiquetas), secciones):
        with pestana:
            st.markdown(f"**{seccion['titulo']}** · {seccion['proposito']}")
            for pregunta in seccion["preguntas"]:
                respuestas[pregunta["id"]] = pregunta_con_voz(pregunta)
    return respuestas


def panel_previos():
    previas = st.file_uploader("Sube propuestas anteriores (PDF, Word, Excel o fotos)", type=TIPOS_DOCUMENTO,
                               accept_multiple_files=True)
    usar_ejemplo = st.checkbox("Usar también la propuesta anterior de ejemplo (ficticia)", value=not previas)
    fragmentos = []
    for f in previas or []:
        fragmentos += trocear(f.name, leer_cacheado(f.name, f.getvalue()))
    if usar_ejemplo:
        fragmentos += trocear(PREVIA.name, leer_documento(PREVIA.name, PREVIA.read_bytes()))
    if not fragmentos:
        return None
    documentos = len({f.doc for f in fragmentos})
    st.caption(f"📚 {documentos} documento(s) leídos completos, en {len(fragmentos)} fragmentos. A la IA van hasta "
               f"{MAX_FRAGMENTOS_PREVIOS}: los más útiles para cada parte de la propuesta (experiencia, metodología, "
               "equipo, resultados, riesgos…). Cada idea reutilizada cita su documento.")
    return Recuperador(fragmentos)




def panel_documentos_apoyo():
    """Archivos opcionales para enriquecer el borrador: CVs, proyectos anteriores u otro contexto."""
    st.markdown("**📎 Documentos de apoyo (opcional)**")
    st.caption("Sube CVs del equipo, proyectos o informes anteriores, o cualquier contexto de tu organización. "
               "La IA usa los CVs para el equipo técnico (con nombres y experiencia reales) y los proyectos para la "
               "experiencia del postor y los antecedentes. Los PDF escaneados y las fotos se leen con OCR. Se envían "
               "al modelo de IA solo para redactar.")
    archivos = st.file_uploader("Documentos de apoyo", type=TIPOS_DOCUMENTO,
                                accept_multiple_files=True, label_visibility="collapsed", key="apoyo_tdr")
    documentos = []
    for archivo in archivos or []:
        with st.spinner(f"Leyendo «{archivo.name}» (si es escaneado o una foto, con OCR)…"):
            texto = leer_cacheado(archivo.name, archivo.getvalue())
        if texto.strip():
            documentos.append((archivo.name, texto))
        else:
            st.warning(f"No se pudo leer texto de «{archivo.name}».")
    if documentos:
        _, informe = preparar_documentos_apoyo(documentos)
        ocr = {n for n, t in documentos if t.startswith(MARCA_OCR)}
        lineas = []
        for d in informe:
            icono = "⚠️" if not d["usados"] else "✅"
            extra = ", leído con OCR" if d["nombre"] in ocr else ""
            lineas.append(f"{icono} **{d['nombre']}** · ~{paginas(d['caracteres'])} pág.{extra} · {d['detalle']}")
        st.markdown("\n".join(f"- {linea}" for linea in lineas))
        if any(not d["usados"] for d in informe):
            st.warning("Algunos archivos no entran: el total para la IA es de ~60 páginas. Quita los menos útiles "
                       "o sube solo las partes que importan.")
    elif not archivos:
        st.caption("Sin documentos, la IA propone el equipo y la experiencia como sugerencias para que los completes.")
    return documentos


def proyectos_referencia(idea, conv, reglas_tdr):
    """Proyectos del BID y del BMZ en Perú más parecidos a la idea y a la convocatoria (la idea pesa doble)."""
    textos = [idea, idea]
    if conv:
        textos += [conv.get("title", ""), conv.get("topic", "")]
    if reglas_tdr is not None:
        textos += [reglas_tdr.nombre_convocatoria, reglas_tdr.objetivo, " ".join(reglas_tdr.temas)]
    return referencias.similares(*textos)


def lista_referencias(proyectos, con_aporte=False):
    for p in proyectos:
        detalle = " · ".join(x for x in (p["fuente"], referencias.anio(p), p["estado"], referencias.monto(p),
                                         p.get("ejecutor", "")) if x)
        st.markdown(f"**[{p['nombre']}]({p['enlace']})**  \n:gray[{detalle}]"
                    + (f"  \n↳ {p['aporte']}" if con_aporte and p.get("aporte") else ""))
    st.caption("Fuentes: datos abiertos del BID y de la cooperación alemana (BMZ, IATI), actualizados cada mes. "
               "La IA los usa como base de enfoques, componentes y montos; no copia su texto ni los presenta "
               "como experiencia tuya.")


def paso_proyecto():
    conv = estado.get("convocatoria")
    tarjeta_convocatoria()
    reglas_tdr = estado.get("reglas_tdr")
    st.subheader("Cuéntanos de tu proyecto")
    c1, c2 = st.columns(2)
    organizacion = c1.text_input("Tu organización", key="w_org", help="Nombre y en qué trabaja",
                                 placeholder="Asociación Juventud Emprende Norte (ficticia), ONG de Chiclayo")
    idea = c2.text_input("Tu idea en una línea (opcional)", key="w_idea",
                         placeholder="Emprendimiento juvenil con capital semilla y voluntariado")

    datos_publicos = ""
    lista_dep = enaho.departamentos()
    if lista_dep:
        sugerido = enaho.detectar(idea, organizacion, conv.get("scope", "") if conv else "")
        codigos = [""] + [c for c, _ in lista_dep]
        nombres = dict(lista_dep)
        if estado.get("dep_sugerido") != sugerido:
            estado.dep_sugerido = sugerido
            estado.w_dep = sugerido if sugerido in codigos else ""
        dep = c1.selectbox("Departamento del proyecto", codigos, key="w_dep",
                           format_func=lambda c: nombres.get(c, "— Elige un departamento —"),
                           help=f"Con él se citan datos de pobreza y empleo juvenil de la ENAHO {enaho.ANIO} (INEI) "
                                "en la sección del problema.")
        datos_publicos = enaho.contexto(dep)
        if datos_publicos:
            with c2.popover(f"📊 Ver datos de la ENAHO {enaho.ANIO}", width="stretch"):
                st.text(datos_publicos)

    similares = proyectos_referencia(idea, conv, reglas_tdr)
    if similares:
        etiqueta = "1 proyecto similar" if len(similares) == 1 else f"{len(similares)} proyectos similares"
        with c2.popover(f"🏦 {etiqueta} (BID y BMZ)", width="stretch"):
            lista_referencias(similares)

    st.markdown("##### ¿Cómo quieres redactarla?")
    if "w_modo" not in estado:
        estado.w_modo = "tdr"
    modo = st.radio("Modo", list(MODOS), key="w_modo", format_func=lambda m: MODOS[m], horizontal=True,
                    captions=[DESCRIPCION_MODO[m] for m in MODOS], label_visibility="collapsed")

    recuperador, respuestas, documentos_apoyo = None, None, []
    with st.container(border=True):
        if modo == "tdr":
            if reglas_tdr:
                st.markdown(f"✅ Se usará el TdR leído (**{estado.tdr_fuente}**) y sus reglas.")
            else:
                st.markdown("ℹ️ No hay TdR: el borrador seguirá el formato base. Puedes subir uno arriba, en "
                            "«Cambiar TdR».")
            documentos_apoyo = panel_documentos_apoyo()
        elif modo == "previos":
            recuperador = panel_previos()
        else:
            respuestas = panel_entrevista()

    listo = not (modo == "previos" and recuperador is None) and not (
        modo == "entrevista" and not any(v.strip() for v in (respuestas or {}).values()))
    st.divider()
    _, der = st.columns([3, 1])
    generar = der.button("✨ Generar propuesta", type="primary", width="stretch", disabled=not listo,
                         help=None if listo else "Sube un documento o responde al menos una pregunta")
    if not generar:
        return
    with st.status("Generando la propuesta… (toma 1 a 2 minutos)", expanded=True) as status:
        try:
            nueva = generar_propuesta(
                modo, FORMATO, reglas_tdr=reglas_tdr, texto_tdr=estado.get("tdr_texto", ""), idea=idea,
                organizacion=organizacion, respuestas=respuestas, recuperador=recuperador,
                datos_publicos=datos_publicos, documentos_apoyo=documentos_apoyo,
                referencias=similares,
                al_avanzar=lambda paso_, total, msg: status.update(label=f"[{paso_}/{total}] {msg}"),
            )
            if reglas_tdr is not None:
                status.update(label="Revisando el presupuesto contra el TdR…")
                nueva["auditoria"], llamadas = auditar_presupuesto(nueva["presupuesto"], reglas_tdr)
                nueva["llamadas"] += llamadas
            nueva["convocatoria"] = conv["title"] if conv else (reglas_tdr.nombre_convocatoria if reglas_tdr else "")
            historial.guardar(nueva, carpeta_historial())
            status.update(label="Propuesta lista", state="complete", expanded=False)
        except Exception as error:
            status.update(label="No se pudo generar", state="error")
            st.error(f"El modelo de IA no respondió. Intenta de nuevo en un minuto o abre una propuesta guardada. "
                     f"Detalle: {error}")
            return
    abrir_propuesta(nueva)
    st.rerun()


# ---------------------------------------------------------------- Paso 2: revisar y descargar
def paso_resultado(propuesta):
    version = estado.get("version", 0)
    reglas_prop = propuesta.get("reglas_tdr")
    reglas = reglas_efectivas(FORMATO, reglas_prop)
    resumen, chequeos = calcular_presupuesto(propuesta["presupuesto"], reglas, conversor=factor)
    chequeos += validar_matriz(propuesta["matriz"], reglas, resumen["solicitado"])
    chequeos += chequeos_auditoria(propuesta.get("auditoria"), resumen, reglas_prop) if reglas_prop else []
    hallazgos = verificar(propuesta, resumen)
    simbolo = SIMBOLOS.get(resumen["moneda"], resumen["moneda"])

    def guardar_y_recargar():
        historial.guardar(propuesta, carpeta_historial())
        estado.version = estado.get("version", 0) + 1
        st.rerun()

    st.subheader(propuesta["textos"].titulo_proyecto)
    st.caption(f"{propuesta.get('convocatoria') or 'Formato base'} · {MODOS[propuesta['modo']]}")

    errores = [m for n, m in chequeos if n == "error"]
    alertas = [m for n, m in chequeos if n == "alerta"]
    if errores:
        st.error(f"**Hay {len(errores)} cosa(s) por corregir antes de enviar.** Míralas en «Qué revisar».",
                 icon="❌")
    elif alertas or hallazgos:
        st.warning(f"**Cumple las reglas, pero revisa {len(alertas) + len(hallazgos)} punto(s)** en «Qué revisar».",
                   icon="⚠️")
    else:
        st.success("**Cumple las reglas del donante.** Revisa el texto y descárgala.", icon="✅")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total del proyecto", monto(simbolo, resumen["total"]), border=True)
    m2.metric("Pides al donante", monto(simbolo, resumen["solicitado"]), border=True)
    m3.metric("Aporte propio", f"{resumen['pct_propio']:.1%}", border=True)
    m4.metric("Puntaje estimado", f"{puntaje_total(propuesta['evaluacion']):.0%}" if propuesta.get("evaluacion")
              else "Sin calcular", border=True)

    tab_rev, tab_texto, tab_matriz, tab_pre, tab_desc = st.tabs(
        ["✅ Qué revisar", "📝 Texto", "🎯 Matriz", "💰 Presupuesto", "⬇️ Descargar"])

    # ---------- Qué revisar
    with tab_rev:
        izq, der = st.columns(2, gap="large")
        with izq:
            st.markdown("##### Reglas del donante")
            if not errores and not alertas:
                st.markdown("✅ No hay nada por corregir.")
            for mensaje in errores:
                st.markdown(f"❌ {mensaje}")
            for mensaje in alertas:
                st.markdown(f"⚠️ {mensaje}")
            cumplen = [m for n, m in chequeos if n == "ok"]
            if cumplen:
                with st.expander(f"Ver lo que ya cumple ({len(cumplen)})"):
                    for mensaje in cumplen:
                        st.markdown(f"✅ {mensaje}")

            st.markdown("##### 🔎 Cifras a validar")
            if hallazgos:
                st.caption("Estos números no salen de tus respuestas, tus documentos, el TdR ni el presupuesto. "
                           "Confírmalos o corrígelos en «Texto».")
                for h in hallazgos:
                    st.markdown(f"- **{h['cifra']}** · {h['seccion']} · _{h['fragmento']}_")
            else:
                st.markdown("✅ Todas las cifras tienen respaldo en tus fuentes.")
        with der:
            st.markdown("##### 📊 Puntaje estimado")
            st.caption("La IA califica la propuesta como lo haría el comité, con los criterios del TdR o del "
                       "formato base. Es una estimación, no la evaluación real.")
            if st.button("Calcular puntaje" if not propuesta.get("evaluacion") else "Volver a calcular"):
                with st.spinner("Evaluando como el comité del donante…"):
                    try:
                        propuesta["evaluacion"], llamadas = evaluar(propuesta, FORMATO, resumen)
                        propuesta.setdefault("llamadas", []).extend(llamadas)
                        guardar_y_recargar()
                    except Exception as error:
                        st.error(f"El modelo de IA no respondió: {error}")
            evaluacion = propuesta.get("evaluacion")
            if evaluacion:
                for c in evaluacion.criterios:
                    with st.expander(f"{c.criterio} · **{c.puntaje}/4**"):
                        st.markdown(f"**Por qué:** {c.justificacion}")
                        st.markdown(f"**Cómo subirlo:** {c.mejora}")
                st.markdown("**Fortalezas**\n" + "\n".join(f"- {x}" for x in evaluacion.fortalezas))
                st.markdown("**Debilidades**\n" + "\n".join(f"- {x}" for x in evaluacion.debilidades))

            if propuesta.get("referencias"):
                with st.expander(f"🏦 Proyectos de referencia usados ({len(propuesta['referencias'])})"):
                    lista_referencias(propuesta["referencias"], con_aporte=True)
                    st.caption("También van como anexo en el Word.")

            with st.expander("🖐️ ¿Cuánto de esta propuesta es tuyo?"):
                st.bar_chart(pd.DataFrame({"Piezas": huella_autoria(propuesta)}), horizontal=True)
                st.caption("De dónde salió cada párrafo, indicador y línea de presupuesto. Mientras más pesen tus "
                           "respuestas y tus propuestas previas, más tuya es. Lo que editas cuenta como tuyo. "
                           "Esto no aparece en el Word ni en el Excel.")

    # ---------- Texto: una sección a la vez
    with tab_texto:
        titulos = titulos_secciones(FORMATO)
        secciones = {s.seccion_id: s for s in propuesta["textos"].secciones}
        nav, editor = st.columns([1, 3], gap="large")
        sid = nav.radio("Sección", list(secciones), format_func=lambda s: titulos.get(s, s), key=f"sec_{version}")
        nav.caption("Tus cambios se conservan al pasar de una sección a otra. Pulsa «Guardar» al terminar. "
                    "Los cuadros (objetivos, metodología, componentes, entregables, cronograma, equipo, riesgos "
                    "y salvaguardas) van en el Word: ajústalos allí.")
        with editor:
            seccion = secciones[sid]
            clave = f"edit_{version}_{sid}"
            if clave not in estado:
                estado[clave] = "\n\n".join(p.texto for p in seccion.parrafos)
            st.text_area(titulos.get(sid, sid), key=clave, height=420,
                         help="Separa los párrafos con una línea en blanco. Esto es lo que sale en el Word.")
            fuentes = dict.fromkeys(etiqueta_fuente(f) for p in seccion.parrafos for f in p.fuentes)
            st.caption("📌 Fuentes: " + " · ".join(fuentes))
            for pendiente in seccion.pendientes:
                st.warning(f"Pendiente: {pendiente}")
            with st.container(horizontal=True):
                if st.button("💾 Guardar cambios", type="primary", key=f"guardar_texto_{version}"):
                    for s in propuesta["textos"].secciones:
                        original = "\n\n".join(p.texto for p in s.parrafos)
                        texto = estado.get(f"edit_{version}_{s.seccion_id}", original).strip()
                        if texto == original:
                            continue
                        previos = {p.texto: p.fuentes for p in s.parrafos}
                        s.parrafos = [Parrafo(texto=t.strip(), fuentes=previos.get(t.strip(), ["USUARIO"]))
                                      for t in texto.split("\n\n") if t.strip()]
                    guardar_y_recargar()
                with st.popover("🔄 Pedir a la IA que la reescriba"):
                    instruccion = st.text_input("¿Qué quieres cambiar?", key=f"instr_{version}_{sid}",
                                                placeholder="Ej.: agrega enfoque de género y acorta a 3 párrafos")
                    if st.button("Reescribir", key=f"regen_{version}_{sid}", disabled=not instruccion):
                        with st.spinner("Reescribiendo…"):
                            try:
                                regenerar_seccion(propuesta, FORMATO, sid, instruccion)
                                guardar_y_recargar()
                            except Exception as error:
                                st.error(f"El modelo de IA no respondió: {error}")

    # ---------- Matriz de impacto
    with tab_matriz:
        m = propuesta["matriz"]
        o1, o2 = st.columns(2)
        sup = o1.text_area("Objetivo superior", value=m.objetivo_superior or "", key=f"sup_{version}", height=90)
        obj = o2.text_area("Objetivo del proyecto", value=m.objetivo_proyecto, key=f"obj_{version}", height=90)
        filas = [{"Nivel": "Proyecto", "Código": i.codigo, "Indicador": i.indicador, "Línea de base": i.linea_base,
                  "Meta": i.meta, "Medio de verificación": i.medio_verificacion} for i in m.indicadores_proyecto]
        for oe in m.objetivos_especificos:
            filas += [{"Nivel": f"{oe.codigo}: {oe.texto}", "Código": i.codigo, "Indicador": i.indicador,
                       "Línea de base": i.linea_base, "Meta": i.meta, "Medio de verificación": i.medio_verificacion}
                      for i in oe.indicadores]
        st.markdown("**Indicadores**")
        tabla_ind = st.data_editor(pd.DataFrame(filas), hide_index=True, width="stretch", key=f"ind_{version}",
                                   disabled=["Nivel", "Código"])
        actividades = [{"Objetivo": oe.codigo, "Código": a.codigo, "Actividad": a.descripcion,
                        "Inicio (mes)": a.mes_inicio, "Fin (mes)": a.mes_fin}
                       for oe in m.objetivos_especificos for a in oe.actividades]
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

    # ---------- Presupuesto
    with tab_pre:
        pres = propuesta["presupuesto"]
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Gastos directos", monto(simbolo, resumen["gastos"]))
        r2.metric("Reserva", monto(simbolo, resumen["reserva"]))
        r3.metric("Administrativos", monto(simbolo, resumen["administrativos"]))
        r4.metric("Total", monto(simbolo, resumen["total"]))
        st.caption(f"Montos en {pres.moneda}. Cambia cantidades o costos, o agrega filas: los totales, la reserva, "
                   "los gastos administrativos y los topes se recalculan al guardar.")
        categorias = list(FORMATO["reglas"]["categorias_gasto"])
        st.markdown("**Líneas de gasto**")
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

    # ---------- Descargar
    with tab_desc:
        with st.container(border=True):
            st.markdown("##### Propuesta técnica y económica")
            st.caption("La técnica sigue el índice del TdR si lo tiene; si no, la estructura base (datos de "
                       "referencia, resumen, comprensión del servicio, objetivos, metodología, componentes, "
                       "entregables, cronograma, equipo, riesgos y salvaguardas). No lleva montos. La económica "
                       "trae un resumen por objetivo y por rubro y el detalle con fórmulas. Sin huella de autoría.")
            d1, d2 = st.columns(2)
            d1.download_button("⬇️ Propuesta técnica (Word)",
                               a_word(propuesta, FORMATO, propuesta.get("convocatoria", ""), resumen),
                               file_name="propuesta_tecnica.docx", width="stretch", mime=WORD, type="primary")
            d2.download_button("⬇️ Propuesta económica (Excel)", a_excel(propuesta, resumen, reglas),
                               file_name="propuesta_economica.xlsx", width="stretch", mime=EXCEL, type="primary")

        with st.container(border=True):
            st.markdown("##### Formato Fondoempleo (Formatos 02 y 03)")
            st.caption("Adapta la propuesta a Fondoempleo y revisa sus reglas en soles: monto por línea, duración, "
                       "equipo ≤ 25 %, contrapartida ≥ 10 %, equipamiento ≤ 2 UIT y gastos no financiables.")
            linea_fe = st.radio("Línea", ["capacitacion_laboral", "fortalecimiento_organizacional"], horizontal=True,
                                format_func=lambda x: fondoempleo.REGLAS["lineas"][x]["nombre"],
                                key=f"linea_fe_{version}")
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
                                       file_name="formato_02_fondoempleo.docx", width="stretch", mime=WORD)
                    e2.download_button("⬇️ Formato 03 (Excel)", fondoempleo.a_excel_formato03(propuesta, calculo_fe),
                                       file_name="formato_03_fondoempleo.xlsx", width="stretch", mime=EXCEL)

        with st.expander("Detalles técnicos"):
            try:
                tc_usd = soles_por("USD")
            except Exception:
                tc_usd = None
            costo = resumen_costo(propuesta.get("llamadas", []), tc_usd["valor"] if tc_usd else None)
            if resumen["moneda"] != "PEN":
                try:
                    tc = soles_por(resumen["moneda"])
                    st.markdown(f"- Total en soles: ≈ S/ {resumen['total'] * tc['valor']:,.0f} "
                                f"(1 {resumen['moneda']} = S/ {tc['valor']:.3f}, {tc['fuente']}, {tc['fecha']})")
                except Exception:
                    pass
            st.markdown(f"- Costo de IA de esta propuesta: US$ {costo['costo_usd']:.3f}"
                        + (f" (S/ {costo['costo_pen']:.2f})" if costo["costo_pen"] is not None else "")
                        + f" · {costo['llamadas']} llamadas · {costo['tokens_entrada'] + costo['tokens_salida']:,} "
                          "tokens")
            st.markdown(f"- Reglas aplicadas: {reglas['origen']}")
            st.markdown(f"- Archivo en el historial: `{propuesta.get('archivo', '')}`")

    st.write("")
    if st.button("← Volver a tu proyecto"):
        ir(1)


# ---------------------------------------------------------------- Mostrar el paso actual
if paso == 1:
    paso_proyecto()
else:
    paso_resultado(estado.propuesta)
