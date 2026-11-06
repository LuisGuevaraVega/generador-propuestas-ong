"""Generador de propuestas técnicas y económicas: un motor, tres modos.

- "tdr":        borrador orientativo a partir del TdR de la convocatoria.
- "previos":    reutiliza ideas y estilo de propuestas anteriores (RAG) siguiendo el TdR.
- "entrevista": redacta solo con las respuestas de la organización.

Cada pieza guarda sus `fuentes`, que forman la huella de autoría:
  "TDR"           -> sale del TdR o las bases
  "IA"            -> sugerencia del asistente, a validar
  "DOC:nombre#n"  -> fragmento n de una propuesta anterior
  "org_1", ...    -> respuesta de la organización en la entrevista
"""
import json

from ai.documentos import recortar
from ai.esquemas import MatrizImpacto, Presupuesto, ReglasConvocatoria, SeccionGenerada, TextosPropuesta
from ai.llm import generar_estructurado, medir_costo

MODOS = {
    "tdr": "Borrador desde el TdR",
    "previos": "Desde mis propuestas anteriores",
    "entrevista": "Entrevista guiada",
}

BASE = """Eres un asistente experto en formular proyectos de desarrollo para ONG del Perú y Latinoamérica.
Escribes en español técnico, claro, en tercera persona, como en una propuesta a la cooperación internacional.
En cada párrafo, indicador, línea de presupuesto o aporte, llena `fuentes` con etiquetas exactas:
"TDR" si sale del TdR o las bases; "IA" si es una sugerencia tuya; las etiquetas DOC:... de los fragmentos
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
    "entrevista": """Modo ENTREVISTA. Usa SOLO las respuestas de la organización; puedes ordenar y dar formato
profesional, pero no agregues ideas nuevas. Si algo falta, márcalo como [POR COMPLETAR].""",
}

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
        "Los porcentajes van como fracción (10% = 0.10)."
    )
    instrucciones = "Eres un analista que lee bases y términos de referencia de convocatorias para ONG. Eres preciso y literal."
    return generar_estructurado(prompt, ReglasConvocatoria, instrucciones, temperatura=0.0)


def _contexto(modo, formato, reglas_tdr, texto_tdr, idea, organizacion, respuestas, recuperador):
    partes = []
    if reglas_tdr is not None:
        partes.append("REGLAS DEL TdR:\n" + reglas_tdr.model_dump_json(indent=1))
    if texto_tdr and modo in ("tdr", "previos"):
        partes.append("TEXTO DEL TdR (fuente 'TDR'):\n" + recortar(texto_tdr, 25000))
    if organizacion:
        partes.append(f"ORGANIZACIÓN QUE POSTULA (dato del usuario):\n{organizacion}")
    if idea:
        partes.append(f"IDEA INICIAL DEL USUARIO:\n{idea}")
    if modo == "previos" and recuperador is not None:
        vistos, bloques = set(), []
        for seccion in formato["secciones"]:
            consulta = seccion["titulo"] + " " + seccion["proposito"] + " " + (idea or "")
            for frag in recuperador.buscar(consulta, k=3):
                if frag.etiqueta not in vistos:
                    vistos.add(frag.etiqueta)
                    bloques.append(f"[{frag.etiqueta}]\n{frag.texto}")
        partes.append("FRAGMENTOS DE PROPUESTAS ANTERIORES DE LA ORGANIZACIÓN:\n\n" + "\n\n".join(bloques[:18]))
    if modo == "entrevista" and respuestas:
        preguntas = {p["id"]: p["texto"] for s in formato["secciones"] for p in s["preguntas"]}
        bloques = [f"[{k}] {preguntas.get(k, '')}\nRespuesta: {v}" for k, v in respuestas.items() if v.strip()]
        partes.append("RESPUESTAS DE LA ORGANIZACIÓN:\n\n" + "\n\n".join(bloques))
    return "\n\n=====\n\n".join(partes)


def generar_propuesta(modo, formato, reglas_tdr=None, texto_tdr="", idea="", organizacion="",
                      respuestas=None, recuperador=None, al_avanzar=None):
    """Genera textos, matriz y presupuesto. `al_avanzar(paso, total, mensaje)` informa el progreso.

    Devuelve también el contexto usado (para regenerar secciones después) y el
    registro de tokens de cada llamada (para calcular el costo).
    """
    contexto = _contexto(modo, formato, reglas_tdr, texto_tdr, idea, organizacion, respuestas, recuperador)
    with medir_costo() as llamadas:
        propuesta = _generar(modo, formato, reglas_tdr, contexto, al_avanzar)
    propuesta.update({"contexto": contexto, "reglas_tdr": reglas_tdr, "llamadas": llamadas,
                      "organizacion": organizacion, "idea": idea})
    return propuesta


def regenerar_seccion(propuesta, formato, seccion_id, instruccion):
    """Reescribe una sección de texto siguiendo una instrucción del usuario."""
    seccion_formato = next(s for s in formato["secciones"] if s["id"] == seccion_id)
    actual = next(s for s in propuesta["textos"].secciones if s.seccion_id == seccion_id)
    texto_actual = "\n\n".join(p.texto for p in actual.parrafos)
    prompt = (
        f"{propuesta['contexto']}\n\n=====\n\n"
        f"SECCIÓN A REESCRIBIR: {seccion_formato['titulo']} (id: {seccion_id}) — {seccion_formato['proposito']}\n\n"
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


def _generar(modo, formato, reglas_tdr, contexto, al_avanzar):
    avisar = al_avanzar or (lambda *a: None)
    instrucciones = BASE + "\n\n" + POR_MODO[modo]
    moneda = reglas_tdr.moneda if reglas_tdr is not None else formato["moneda"]
    textos_ids = [s for s in formato["secciones"] if s["tipo"] == "texto"]

    avisar(1, 3, "Redactando la propuesta técnica…")
    guia = "\n".join(f"- {s['id']}: {s['titulo']} — {s['proposito']}" for s in textos_ids)
    textos = generar_estructurado(
        f"{contexto}\n\n=====\n\nRedacta estas secciones (una SeccionGenerada por id, 2 a 4 párrafos cada una):\n{guia}",
        TextosPropuesta, instrucciones,
    )

    avisar(2, 3, "Armando la matriz de impacto…")
    resumen_textos = "\n".join(
        f"[{s.seccion_id}] " + " ".join(p.texto for p in s.parrafos)[:1500] for s in textos.secciones
    )
    matriz = generar_estructurado(
        f"{contexto}\n\n=====\n\nPROPUESTA TÉCNICA YA REDACTADA:\n{resumen_textos}\n\n{REGLAS_MATRIZ}",
        MatrizImpacto, instrucciones,
    )

    avisar(3, 3, "Calculando el presupuesto…")
    objetivos = [{"codigo": oe.codigo, "objetivo": oe.texto,
                  "actividades": [a.descripcion for a in oe.actividades]} for oe in matriz.objetivos_especificos]
    presupuesto = generar_estructurado(
        f"{contexto}\n\n=====\n\nMoneda: {moneda}\nOBJETIVOS Y ACTIVIDADES:\n"
        f"{json.dumps(objetivos, ensure_ascii=False, indent=1)}\n\n{REGLAS_PRESUPUESTO}",
        Presupuesto, instrucciones, temperatura=0.2,
    )
    return {"modo": modo, "moneda": moneda, "textos": textos, "matriz": matriz, "presupuesto": presupuesto}
