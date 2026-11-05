"""Redacta cada sección de la propuesta SOLO con las respuestas de la organización.

La IA no inventa: si falta un dato, lo deja en `pendientes`. Cada párrafo,
indicador o línea de presupuesto indica de qué respuestas salió (`fuentes`).
"""
import json

from ai.esquemas import MatrizImpacto, Presupuesto, SeccionTexto
from ai.llm import generar_estructurado

INSTRUCCIONES = """Eres un asistente de redacción de propuestas para ONG de desarrollo en el Perú.
Redactas en español técnico, claro y en tercera persona, como en una propuesta a la cooperación alemana (BMZ).
Reglas estrictas:
1. Usa SOLO la información de las respuestas de la organización. No inventes cifras, nombres ni hechos.
2. Si un dato necesario falta, no lo supongas: anótalo en `pendientes`.
3. En `fuentes` pon los ids exactos de las respuestas que usaste (p. ej. "pro_1").
4. Puedes ordenar, conectar y dar formato profesional a las ideas, pero el contenido es de la organización."""

REGLAS_MATRIZ = """Reglas del formato para la matriz de impacto:
- Un solo objetivo del proyecto (cambio en el uso de capacidades por el grupo meta) y 2 o 3 objetivos específicos (capacidades nuevas).
- 1 o 2 indicadores por objetivo específico y un indicador del objetivo del proyecto por cada objetivo específico.
- Indicadores SMART, con línea de base y meta en la misma unidad. La línea de base no debe ser cero ni lo opuesto de la meta.
- La meta mide el EFECTO, nunca la actividad ni la entrega de un servicio.
  Mal: "se realizaron 8 talleres", "60 emprendimientos reciben capital", "% que completa la formación", "30 voluntarios formados".
  Bien: "80% de participantes lleva registro mensual de ventas y costos", "70% de emprendimientos con capital sigue activo al mes 12",
  "25 mentores voluntarios acompañan al menos a 3 jóvenes cada uno".
- Los indicadores de objetivos específicos miden capacidades que el grupo meta ya domina o usa; los del objetivo del proyecto miden el cambio en sus negocios o vidas.
- Usa como línea de base las cifras de partida que dio la organización (p. ej. "15% lleva registros"). Si no hay cifra, escribe un estimado razonable marcado "(estimado, a validar en línea de base)" y anótalo en pendientes.
- Incluye las actividades de cada objetivo con mes de inicio y fin.
- Objetivo superior solo si la organización describe un beneficio de largo plazo; si no, déjalo vacío."""

REGLAS_PRESUPUESTO = """Reglas para el plan de financiamiento:
- Extrae las líneas de gasto tal como las dio la organización. No agregues gastos que no mencionó.
- Asigna cada línea al objetivo específico (OE1, OE2, ...) de la matriz, o 'GEN' si es transversal (personal, monitoreo, viajes).
- categoria debe ser una de: inversiones, operativos, personal, viajes, evaluacion. El capital semilla en bienes va en inversiones.
- cantidad x costo_unitario debe reproducir el monto que dio la organización. Moneda: euros.
- En aportes_propios pon lo que aportan la organización, el socio u otros (no el monto pedido al donante).
- NO calcules reserva, gastos administrativos ni totales: eso lo hace el sistema."""


def _bloque_respuestas(seccion, respuestas):
    lineas = []
    for pregunta in seccion["preguntas"]:
        texto = respuestas.get(pregunta["id"], "").strip() or "(sin respuesta)"
        lineas.append(f"[{pregunta['id']}] Pregunta: {pregunta['texto']}\nRespuesta: {texto}")
    return "\n\n".join(lineas)


def redactar(seccion, respuestas, convocatoria=None, matriz=None, extra_respuestas=None):
    """Devuelve el objeto estructurado de la sección según su tipo."""
    contexto = f"Convocatoria: {convocatoria}\n\n" if convocatoria else ""
    prompt = (
        f"{contexto}Sección a redactar: {seccion['titulo']}\n"
        f"Propósito: {seccion['proposito']}\n\n"
        f"Respuestas de la organización:\n{_bloque_respuestas(seccion, respuestas)}"
    )
    if extra_respuestas:
        prompt += f"\n\nContexto adicional de otras secciones:\n{extra_respuestas}"

    if seccion["tipo"] == "matriz":
        return generar_estructurado(prompt + "\n\n" + REGLAS_MATRIZ, MatrizImpacto, INSTRUCCIONES)
    if seccion["tipo"] == "presupuesto":
        if matriz is not None:
            resumen = [{"codigo": oe.codigo, "objetivo": oe.texto} for oe in matriz.objetivos_especificos]
            prompt += "\n\nObjetivos específicos de la matriz:\n" + json.dumps(resumen, ensure_ascii=False)
        return generar_estructurado(prompt + "\n\n" + REGLAS_PRESUPUESTO, Presupuesto, INSTRUCCIONES, temperatura=0.1)
    return generar_estructurado(prompt, SeccionTexto, INSTRUCCIONES)
