"""Generador de propuestas técnicas y económicas: un motor, tres modos.

Flujo: diseño técnico (cuadros y listas) -> textos -> matriz de indicadores -> presupuesto.

- "tdr":        borrador orientativo a partir del TdR de la convocatoria.
- "previos":    reutiliza ideas y estilo de propuestas anteriores (RAG) siguiendo el TdR.
- "entrevista": redacta solo con las respuestas de la organización.

Cada pieza guarda sus `fuentes`, que forman la huella de autoría:
  "TDR"           -> sale del TdR o las bases
  "ENAHO"         -> dato público de la ENAHO
  "BID", "BMZ"    -> proyecto similar financiado por el BID o la cooperación alemana (ai/referencias.py)
  "IA"            -> sugerencia del asistente, a validar
  "DOC:nombre#n"  -> fragmento n de una propuesta anterior
  "org_1", ...    -> respuesta de la organización en la entrevista
"""
import json

from ai.documentos import CARACTERES_POR_PAGINA, Recuperador, recortar, trocear
from ai.esquemas import (MatrizImpacto, Presupuesto, PropuestaTecnica, ReglasConvocatoria, SeccionGenerada,
                         TextosPropuesta)
from ai.llm import generar_estructurado, medir_costo
from ai.referencias import contexto as contexto_referencias
from ai.referencias import usadas as referencias_usadas

MODOS = {
    "tdr": "Borrador desde el TdR",
    "previos": "Desde mis propuestas anteriores",
    "entrevista": "Entrevista guiada",
}

BASE = """Eres un asistente experto en formular proyectos de desarrollo para ONG del Perú y Latinoamérica.
Escribes en español técnico, claro, en tercera persona, como en una propuesta a la cooperación internacional.
En cada párrafo, indicador, línea de presupuesto o aporte, llena `fuentes` con etiquetas exactas:
"TDR" si sale del TdR o las bases; "ENAHO" o "ENDES" si es un dato público del INEI; "BID" o "BMZ" si tomas como
referencia un proyecto similar financiado por el BID o por la cooperación alemana; "IA" si es una sugerencia tuya;
las etiquetas DOC:... de los fragmentos
de propuestas anteriores que uses; o los ids de las respuestas de la organización (p. ej. "pro_1").
Nunca inventes datos de la organización (nombre, años, resultados pasados, cifras de diagnóstico):
si no los tienes, escribe [POR COMPLETAR: qué dato] en el texto y anótalo en `pendientes`."""

POR_MODO = {
    "tdr": """Modo BORRADOR DESDE EL TdR. Tu trabajo es orientar: propone un proyecto concreto y viable que responda
a los objetivos, temas, montos, plazos y criterios de evaluación del TdR. Sugiere enfoques, actividades e
indicadores realistas para el Perú. Marca como "IA" todo lo que propones tú y como "TDR" lo que exige el TdR.""",
    "previos": """Modo DESDE PROPUESTAS ANTERIORES. La organización ya postuló a proyectos parecidos.
Reutiliza su enfoque, sus actividades probadas, su forma de escribir y su experiencia, tomados de los fragmentos
DOC:..., y adáptalos a lo que pide el nuevo TdR. Cita cada fragmento que uses. Lo que agregues tú va como "IA".
No copies cifras de proyectos anteriores como si fueran del nuevo proyecto: úsalas solo como experiencia previa.""",
    "entrevista": """Modo ENTREVISTA. Todo lo que diga de la organización, el problema, el grupo meta, sus cifras
y su experiencia sale SOLO de sus respuestas; puedes ordenar y dar formato profesional. Si algo falta, márcalo como
[POR COMPLETAR]. En el diseño técnico (metodología, componentes, entregables, cronograma, equipo, riesgos y
salvaguardas) parte de sus respuestas y completa lo que falte con propuestas tuyas, marcadas como "IA".""",
}

REGLAS_DISENO = """Cómo diseñar la propuesta técnica (estructura de postor):
- Si el TdR tiene un índice o formato para la propuesta técnica, se sigue tal cual. Si no, la propuesta lleva:
  datos de referencia, resumen ejecutivo, antecedentes y comprensión del servicio, objetivos, enfoque metodológico
  y principios, estrategia metodológica general con monitoreo y evaluación, plan de trabajo por componentes,
  entregables, cronograma, equipo técnico, calidad y gestión de riesgos, y salvaguardas.
- Sé DETALLADO y ESPECÍFICO para este TdR y este territorio: el usuario ajustará después tus ideas, así que
  propón contenido concreto (nombres de instrumentos, criterios, productos, plazos), nunca frases de relleno.
- Datos de referencia: nombre del servicio, a quién se presenta, sistema de contratación, plazo de ejecución,
  ámbito y postor. Si el TdR no dice un dato, escribe [POR COMPLETAR: dato].
- Comprensión del servicio: 4 aspectos (resultados mínimos esperados, enfoques exigidos, condiciones críticas,
  gestión contractual) que muestren que el postor leyó el TdR.
- Objetivo general: un párrafo de 60 palabras como máximo. Objetivos específicos: 3 a 5, numerados OE1, OE2...
- Enfoque metodológico: 4 a 7 momentos en orden (p. ej. diagnóstico, selección, organización, formación,
  acompañamiento, evaluación y cierre), cada uno con palabras clave de contenido técnico (p. ej. levantamiento de
  información, aplicación de criterios de viabilidad, compromisos) y sus productos (p. ej. fichas de padrón,
  matrices de selección, actas, reglamentos, roles definidos, expedientes, reportes de asistencia técnica).
- Plan de trabajo: un componente por objetivo específico, con líneas de acción, actividades principales y
  resultados esperados según lo que pide el TdR; aporta ideas propias.
- Entregables con código E1, E2..., plazo máximo y contenido principal; si el TdR los define, respétalos.
- Cronograma: de la planificación al diagnóstico, las actividades y programas, y la evaluación y cierre; cada fila
  con su periodo en meses y el resultado esperado, dentro del plazo del TdR.
- Equipo técnico: roles, perfil, dedicación y responsabilidades según el TdR.
- Riesgos: 5 a 7, con su posible efecto y la medida de mitigación. Calidad: criterios como prevención,
  transparencia y mejora continua. Salvaguardas sociales, financieras, digitales e institucionales.
- Si hay DOCUMENTOS DE APOYO DE LA ORGANIZACIÓN: usa los CV para el equipo técnico (nombre de la persona, perfil
  y experiencia reales; no inventes cargos, años ni títulos que no estén en el CV) y los proyectos anteriores o
  informes para la experiencia del postor, los antecedentes y la metodología (cita lo que hicieron, con sus cifras
  como experiencia previa). Pon la etiqueta DOC:... del documento en `fuentes`.
- La propuesta técnica NO lleva montos ni precios: van en la propuesta económica."""

REGLAS_MATRIZ = """Reglas de la matriz de impacto:
- Un solo objetivo del proyecto (cambio en el uso de capacidades por el grupo meta) y 2 o 3 objetivos específicos.
- 1 o 2 indicadores por objetivo específico, y un indicador del objetivo del proyecto por cada objetivo específico.
- Indicadores SMART, con línea de base y meta en la misma unidad. La línea de base no debe ser cero ni lo opuesto de la meta.
- La meta mide el EFECTO, nunca la actividad ni la entrega de un servicio.
  Mal: "se realizaron 8 talleres", "60 emprendimientos reciben capital", "30 voluntarios formados".
  Bien: "80% de participantes lleva registro mensual de ventas", "70% de emprendimientos sigue activo al mes 12".
- Si no hay cifra de partida, usa un estimado marcado "(estimado, a validar en línea de base)".
- Incluye las actividades de cada objetivo con mes de inicio y fin, dentro de la duración del proyecto.
- Objetivo superior: beneficio de largo plazo para el grupo meta (obligatorio si el monto supera 100,000 EUR)."""

REGLAS_PRESUPUESTO = """Reglas del plan de financiamiento:
- Una línea por gasto, asignada al objetivo específico (OE1, OE2...) o 'GEN' si es transversal (personal, monitoreo, viajes).
- categoria: una de inversiones, operativos, personal, viajes, evaluacion. El capital semilla en bienes va en inversiones.
- Usa la moneda indicada. Si la organización dio sus montos en otra moneda, NO conviertas: conserva sus cifras
  y pon en `moneda` la moneda en que realmente están. cantidad x costo_unitario debe ser realista para el Perú.
- En aportes_propios va lo que aporta la organización, sus socios u otros (no el monto pedido al donante).
- Respeta los topes del TdR: monto a solicitar, duración, contrapartida mínima y gastos no elegibles.
- NO calcules reserva, gastos administrativos ni totales: los calcula el sistema."""


def extraer_reglas(texto_tdr: str, ficha: str = "") -> ReglasConvocatoria:
    """Lee el TdR/bases y devuelve sus reglas en forma estructurada."""
    prompt = (
        f"Ficha de la convocatoria (resumen del boletín):\n{ficha}\n\n"
        f"Texto del TdR o de las bases:\n{recortar(texto_tdr)}\n\n"
        "Extrae las reglas de la convocatoria. Usa null cuando el documento no diga un dato; no lo supongas. "
        "Los porcentajes van como fracción (10% = 0.10). En topes_por_rubro pon cada límite por tipo de gasto "
        "(p. ej. 'consultorías y capacitación hasta 30% del monto') con su base: 'total' o 'solicitado'."
    )
    instrucciones = "Eres un analista que lee bases y términos de referencia de convocatorias para ONG. Eres preciso y literal."
    return generar_estructurado(prompt, ReglasConvocatoria, instrucciones, temperatura=0.0)


MAX_POR_DOCUMENTO = 40_000        # ~15 páginas por archivo
MAX_DOCUMENTOS_APOYO = 150_000    # ~60 páginas entre todos los archivos
COMIENZO_DOCUMENTO_LARGO = 8_000  # de un documento largo siempre va el comienzo (presentación, resumen)
MINIMO_UTIL = 2_000
MAX_FRAGMENTOS_PREVIOS = 40

# Qué buscar en un informe largo o en propuestas anteriores: lo que alimenta la propuesta técnica.
CONSULTAS_RELEVANCIA = [
    "experiencia de la organización proyectos ejecutados resultados logros cifras beneficiarios",
    "lecciones aprendidas recomendaciones buenas prácticas sostenibilidad",
    "metodología enfoque etapas momentos actividades instrumentos herramientas",
    "equipo técnico perfil profesional experiencia formación coordinador especialista",
    "población beneficiaria grupo meta participantes territorio distritos",
    "indicadores línea de base metas monitoreo evaluación medios de verificación",
    "riesgos dificultades problemas medidas de mitigación",
    "alianzas socios gobiernos locales articulación actores",
    "productos entregables informes cronograma plazos",
]


def seleccionar_texto(nombre, texto, limite):
    """Texto que entra al contexto y una descripción de cuánto se usó.

    Si el documento cabe, va completo. Si no, va su comienzo más los fragmentos más relevantes
    para la propuesta (resultados, metodología, equipo, lecciones…), en el orden en que aparecen.
    """
    texto = texto.strip()
    if len(texto) <= limite:
        return texto, "completo"
    comienzo = texto[:COMIENZO_DOCUMENTO_LARGO]
    fragmentos = trocear(nombre, texto[COMIENZO_DOCUMENTO_LARGO:])
    puntajes = Recuperador(fragmentos).puntajes(CONSULTAS_RELEVANCIA)
    separador = "\n[...]\n"
    elegidos, usados = [], len(comienzo)
    for i in puntajes.argsort()[::-1]:
        if puntajes[i] <= 0:
            break
        costo = len(separador) + len(fragmentos[i].texto)
        if usados + costo <= limite:
            elegidos.append(i)
            usados += costo
    partes = [comienzo] + [fragmentos[i].texto for i in sorted(elegidos)]
    usado = separador.join(partes)
    return usado, (f"comienzo + {len(elegidos)} fragmentos relevantes de {len(fragmentos)} "
                   f"({len(usado) / len(texto):.0%} del documento)")


def preparar_documentos_apoyo(documentos):
    """Arma el bloque de documentos de apoyo y un informe de cuánto de cada archivo se usa.

    Devuelve (bloque, informe); el informe es una lista de dicts con nombre, caracteres, usados y detalle.
    """
    bloques, informe, usados = [], [], 0
    for nombre, texto in documentos or []:
        if not texto.strip():
            continue
        disponible = min(MAX_POR_DOCUMENTO, MAX_DOCUMENTOS_APOYO - usados)
        if disponible < MINIMO_UTIL:
            informe.append({"nombre": nombre, "caracteres": len(texto), "usados": 0,
                            "detalle": "no entra: se llegó al límite total de ~60 páginas"})
            continue
        elegido, detalle = seleccionar_texto(nombre, texto, disponible)
        usados += len(elegido)
        bloques.append(f"[DOC:{nombre}]\n{elegido}")
        informe.append({"nombre": nombre, "caracteres": len(texto), "usados": len(elegido), "detalle": detalle})
    if not bloques:
        return "", informe
    bloque = ("DOCUMENTOS DE APOYO DE LA ORGANIZACIÓN (CV del equipo, proyectos anteriores u otro contexto; "
              "cita su etiqueta DOC:... en fuentes):\n\n" + "\n\n".join(bloques))
    return bloque, informe


def fragmentos_previos(recuperador, formato, idea="", maximo=MAX_FRAGMENTOS_PREVIOS):
    """Los fragmentos de propuestas anteriores más útiles para cada parte de la propuesta.

    Busca con los temas de la entrevista, las secciones del documento nuevo y las consultas de relevancia, y
    los toma por turnos (el mejor de cada consulta, luego el segundo…) para que todas las partes tengan material.
    """
    temas = list(formato["secciones"]) + list(formato.get("documento", []))
    consultas = [f"{s['titulo']} {s['proposito']} {idea or ''}" for s in temas] + CONSULTAS_RELEVANCIA
    resultados = [recuperador.buscar(c, k=5) for c in consultas]
    elegidos, vistos = [], set()
    for turno in range(5):
        for lista in resultados:
            if turno < len(lista) and lista[turno].etiqueta not in vistos and len(elegidos) < maximo:
                vistos.add(lista[turno].etiqueta)
                elegidos.append(lista[turno])
    return elegidos


def bloque_documentos_apoyo(documentos):
    return preparar_documentos_apoyo(documentos)[0]


def paginas(caracteres):
    return max(1, round(caracteres / CARACTERES_POR_PAGINA))


def _contexto(modo, formato, reglas_tdr, texto_tdr, idea, organizacion, respuestas, recuperador, datos_publicos="",
              documentos_apoyo=None, referencias=None):
    partes = []
    if datos_publicos:
        partes.append(datos_publicos)
    if referencias:
        partes.append(contexto_referencias(referencias))
    if reglas_tdr is not None:
        partes.append("REGLAS DEL TdR:\n" + reglas_tdr.model_dump_json(indent=1))
    if texto_tdr and modo in ("tdr", "previos"):
        partes.append("TEXTO DEL TdR (fuente 'TDR'):\n" + recortar(texto_tdr))
    if organizacion:
        partes.append(f"ORGANIZACIÓN QUE POSTULA (dato del usuario):\n{organizacion}")
    if idea:
        partes.append(f"IDEA INICIAL DEL USUARIO:\n{idea}")
    apoyo = bloque_documentos_apoyo(documentos_apoyo)
    if apoyo:
        partes.append(apoyo)
    if modo == "previos" and recuperador is not None:
        bloques = [f"[{f.etiqueta}]\n{f.texto}" for f in fragmentos_previos(recuperador, formato, idea)]
        partes.append("FRAGMENTOS DE PROPUESTAS ANTERIORES DE LA ORGANIZACIÓN:\n\n" + "\n\n".join(bloques))
    if modo == "entrevista" and respuestas:
        preguntas = {p["id"]: p["texto"] for s in formato["secciones"] for p in s["preguntas"]}
        bloques = [f"[{k}] {preguntas.get(k, '')}\nRespuesta: {v}" for k, v in respuestas.items() if v.strip()]
        partes.append("RESPUESTAS DE LA ORGANIZACIÓN:\n\n" + "\n\n".join(bloques))
    return "\n\n=====\n\n".join(partes)


def generar_propuesta(modo, formato, reglas_tdr=None, texto_tdr="", idea="", organizacion="",
                      respuestas=None, recuperador=None, al_avanzar=None, datos_publicos="", documentos_apoyo=None,
                      referencias=None):
    """Genera textos, matriz y presupuesto. `al_avanzar(paso, total, mensaje)` informa el progreso.

    Devuelve también el contexto usado (para regenerar secciones después) y el
    registro de tokens de cada llamada (para calcular el costo).
    """
    contexto = _contexto(modo, formato, reglas_tdr, texto_tdr, idea, organizacion, respuestas, recuperador,
                         datos_publicos, documentos_apoyo, referencias)
    with medir_costo() as llamadas:
        propuesta = _generar(modo, formato, reglas_tdr, contexto, al_avanzar)
    propuesta.update({"contexto": contexto, "reglas_tdr": reglas_tdr, "llamadas": llamadas,
                      "organizacion": organizacion, "idea": idea,
                      "referencias": referencias_usadas(propuesta["tecnica"].referencias, referencias or [])})
    return propuesta


def secciones_texto(formato):
    """Secciones de texto del documento (las que se redactan y se editan en la app)."""
    return formato.get("documento") or [s for s in formato["secciones"] if s["tipo"] == "texto"]


def titulos_secciones(formato):
    """Títulos de las secciones de texto, incluidas las del formato anterior (propuestas viejas)."""
    titulos = {s["id"]: s["titulo"] for s in formato["secciones"]}
    titulos.update({s["id"]: s["titulo"] for s in formato.get("documento", [])})
    return titulos


def regenerar_seccion(propuesta, formato, seccion_id, instruccion):
    """Reescribe una sección de texto siguiendo una instrucción del usuario."""
    todas = list(formato.get("documento", [])) + list(formato["secciones"])
    seccion_formato = next(s for s in todas if s["id"] == seccion_id)
    actual = next(s for s in propuesta["textos"].secciones if s.seccion_id == seccion_id)
    texto_actual = "\n\n".join(p.texto for p in actual.parrafos)
    diseno = propuesta.get("tecnica")
    prompt = (
        f"{propuesta['contexto']}\n\n=====\n\n"
        + (f"DISEÑO DE LA PROPUESTA TÉCNICA:\n{diseno.model_dump_json(indent=1)}\n\n=====\n\n" if diseno else "")
        + f"SECCIÓN A REESCRIBIR: {seccion_formato['titulo']} (id: {seccion_id}) — {seccion_formato['proposito']}\n\n"
        f"VERSIÓN ACTUAL (puede incluir ediciones del usuario, respétalas salvo que la instrucción diga otra cosa):\n"
        f"{texto_actual}\n\n"
        f"INSTRUCCIÓN DEL USUARIO: {instruccion}\n\n"
        f"Devuelve la sección completa reescrita, con seccion_id='{seccion_id}'. "
        f"Lo que venga de la instrucción del usuario lleva la fuente 'USUARIO'."
    )
    with medir_costo() as llamadas:
        nueva = generar_estructurado(prompt, SeccionGenerada, BASE + "\n\n" + POR_MODO[propuesta["modo"]])
    nueva.seccion_id = seccion_id
    propuesta["textos"].secciones = [nueva if s.seccion_id == seccion_id else s for s in propuesta["textos"].secciones]
    propuesta.setdefault("llamadas", []).extend(llamadas)
    return nueva


def _guia_citas(tecnica):
    """Pide citar en el texto los proyectos de referencia que el diseño declaró haber usado."""
    if not tecnica.referencias:
        return ""
    codigos = ", ".join(r.codigo for r in tecnica.referencias)
    return ("\nEn antecedentes (o comprensión del servicio) y en la estrategia metodológica, menciona en una frase "
            "cada uno de estos proyectos de referencia que inspiraron el diseño, citándolo como «BID, proyecto "
            f"<código>» o «cooperación alemana (BMZ), proyecto <código>», y pon \"BID\" o \"BMZ\" en fuentes: "
            f"{codigos}. Preséntalos como experiencias de la cooperación en el país, no de la organización. Di solo qué "
            "buscaba o hacía cada uno (su objetivo o enfoque): no tenemos sus resultados, así que nunca escribas que "
            "demostró, logró, fue exitoso o fortaleció algo.")


def _estructura_base_texto():
    from ai.exportar import ESTRUCTURA_BASE

    return "\n".join(f"- {titulo}: {', '.join(b for _, b in partes)}" for titulo, partes in ESTRUCTURA_BASE)


def _guia_formato_tdr(reglas_tdr):
    """Cómo armar el índice: la estructura base de referencia, fusionada con el que pida el TdR o la organización."""
    base = "ESTRUCTURA BASE (referencia mínima; sección: bloques que lleva):\n" + _estructura_base_texto()
    fusion = ("Arma estructura_tdr como un índice FUSIONADO: (1) incluye TODAS las secciones que exige el TdR o el "
              "formato, con su título tal cual y en su orden, asignando a cada una SOLO los bloques que responden a lo "
              "que esa sección pide por su tema (p. ej., «Plan de trabajo con cronograma» lleva componentes y "
              "cronograma, no equipo ni salvaguardas); (2) agrega como secciones propias, con su título de la base y "
              "donde encajen con lógica, las secciones de la ESTRUCTURA BASE cuyos bloques no calzan en ninguna "
              "sección del TdR (p. ej., Resumen ejecutivo al inicio, Equipo técnico, Riesgos y Salvaguardas al final). Cada bloque una sola vez y todos los bloques deben aparecer (la "
              "matriz puede ir como anexo). Si una sección del TdR no calza con ningún bloque, deja bloques vacío y "
              "explica en nota qué debe completar el postor.")
    if reglas_tdr is not None and reglas_tdr.secciones_requeridas:
        indice = "\n".join(f"{i}. {s}" for i, s in enumerate(reglas_tdr.secciones_requeridas, 1))
        return f"{base}\n\nEl TdR EXIGE este índice para la propuesta técnica:\n{indice}\n\n{fusion}"
    return (f"{base}\n\nEl TdR no fija un índice. Si los DOCUMENTOS DE APOYO traen un formato o índice de la "
            f"organización o del donante, fusiónalo con la base así: {fusion} Si no hay ningún formato que "
            "fusionar, deja estructura_tdr como lista vacía (se usará la estructura base).")


def _generar(modo, formato, reglas_tdr, contexto, al_avanzar):
    avisar = al_avanzar or (lambda *a: None)
    instrucciones = BASE + "\n\n" + POR_MODO[modo] + "\n\n" + REGLAS_DISENO
    moneda = reglas_tdr.moneda if reglas_tdr is not None else formato["moneda"]

    avisar(1, 4, "Diseñando la propuesta técnica: objetivos, metodología, entregables y equipo…")
    tecnica = generar_estructurado(
        f"{contexto}\n\n=====\n\nDiseña la propuesta técnica completa.\n{_guia_formato_tdr(reglas_tdr)}",
        PropuestaTecnica, instrucciones,
    )

    avisar(2, 4, "Redactando el resumen, los antecedentes y la estrategia…")
    guia = "\n".join(f"- {s['id']}: {s['titulo']} — {s['proposito']}" for s in secciones_texto(formato))
    textos = generar_estructurado(
        f"{contexto}\n\n=====\n\nDISEÑO DE LA PROPUESTA TÉCNICA (síguelo; no lo contradigas):\n"
        f"{tecnica.model_dump_json(indent=1)}\n\n=====\n\n"
        f"Redacta estas secciones (una SeccionGenerada por id). Usa como titulo_proyecto el nombre del servicio "
        f"del diseño. Sé concreto y específico: nada de frases genéricas.{_guia_citas(tecnica)}\n{guia}",
        TextosPropuesta, instrucciones,
    )
    textos.titulo_proyecto = tecnica.datos.nombre_servicio or textos.titulo_proyecto

    avisar(3, 4, "Armando la matriz de indicadores…")
    componentes = [{"objetivo": c.objetivo, "componente": c.nombre, "actividades": c.actividades}
                   for c in tecnica.componentes]
    matriz = generar_estructurado(
        f"{contexto}\n\n=====\n\nOBJETIVO GENERAL (úsalo como objetivo del proyecto): {tecnica.objetivo_general}\n"
        f"OBJETIVOS ESPECÍFICOS (usa EXACTAMENTE estos códigos y textos):\n"
        + "\n".join(f"- {o.codigo}: {o.texto}" for o in tecnica.objetivos_especificos)
        + f"\nCOMPONENTES Y ACTIVIDADES (las actividades de cada OE salen de aquí):\n"
        f"{json.dumps(componentes, ensure_ascii=False, indent=1)}\n"
        f"CRONOGRAMA: {json.dumps([f.model_dump() for f in tecnica.cronograma], ensure_ascii=False)}\n\n"
        f"{REGLAS_MATRIZ}",
        MatrizImpacto, instrucciones,
    )

    avisar(4, 4, "Calculando la propuesta económica…")
    objetivos = [{"codigo": oe.codigo, "objetivo": oe.texto,
                  "actividades": [a.descripcion for a in oe.actividades]} for oe in matriz.objetivos_especificos]
    equipo = [{"rol": r.rol, "dedicacion": r.dedicacion} for r in tecnica.equipo]
    presupuesto = generar_estructurado(
        f"{contexto}\n\n=====\n\nMoneda: {moneda}\nOBJETIVOS Y ACTIVIDADES:\n"
        f"{json.dumps(objetivos, ensure_ascii=False, indent=1)}\n"
        f"EQUIPO TÉCNICO PROPUESTO: {json.dumps(equipo, ensure_ascii=False)}\n\n{REGLAS_PRESUPUESTO}",
        Presupuesto, instrucciones, temperatura=0.2,
    )
    return {"modo": modo, "moneda": moneda, "tecnica": tecnica, "textos": textos, "matriz": matriz,
            "presupuesto": presupuesto}
