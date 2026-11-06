"""Auditoría del presupuesto y puntaje estimado según los criterios del donante.

- `auditar_presupuesto`: el modelo clasifica cada línea (¿es un gasto prohibido por el
  TdR? ¿a qué rubro con tope pertenece?) y el código suma y compara los topes.
- `evaluar`: el modelo actúa como evaluador del donante y califica de 1 a 4 cada
  criterio de evaluación del TdR (o criterios tipo BMZ si no hay TdR).
"""
import json
import unicodedata

from ai.esquemas import AuditoriaPresupuesto, Evaluacion
from ai.llm import generar_estructurado, medir_costo
from ai.reglas import ALERTA, ERROR, OK, SIMBOLOS

CRITERIOS_BASE = [
    "Relevancia: el proyecto responde a un problema concreto y bien sustentado del grupo meta",
    "Coherencia de la matriz de impacto: objetivos, indicadores SMART y actividades encadenados",
    "Eficacia: las actividades bastan para lograr los objetivos específicos",
    "Eficiencia: el presupuesto es razonable y está alineado a las actividades",
    "Sostenibilidad: qué queda funcionando después del proyecto y quién lo sostiene",
    "Capacidad de la organización y participación del grupo meta",
]


def _normal(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.lower().split())


def _pertenece(rubros_linea, codigo: str, rubro_tope: str) -> bool:
    """La línea cuenta en el tope si el modelo puso el código o una parte del nombre del rubro."""
    tope = _normal(rubro_tope)
    for r in rubros_linea:
        r = _normal(r)
        if r and (r == codigo.lower() or r in tope or tope in r):
            return True
    return False


def auditar_presupuesto(presupuesto, reglas_tdr):
    """Devuelve (AuditoriaPresupuesto, llamadas) o (None, []) si el TdR no tiene restricciones."""
    if reglas_tdr is None or not (reglas_tdr.gastos_no_elegibles or reglas_tdr.topes_por_rubro):
        return None, []
    lineas = [{"descripcion": l.descripcion, "categoria": l.categoria} for l in presupuesto.lineas]
    prompt = (
        f"GASTOS NO ELEGIBLES SEGÚN EL TdR:\n{json.dumps(reglas_tdr.gastos_no_elegibles, ensure_ascii=False)}\n\n"
        f"RUBROS CON TOPE SEGÚN EL TdR:\n{json.dumps([t.rubro for t in reglas_tdr.topes_por_rubro], ensure_ascii=False)}\n\n"
        f"LÍNEAS DEL PRESUPUESTO:\n{json.dumps(lineas, ensure_ascii=False, indent=1)}\n\n"
        "Para cada línea, indica si es elegible y en rubros_tdr los códigos (R1, R2...) de los rubros con tope "
        "a los que pertenece; una capacitación, taller, mentoría o consultoría cuenta en el rubro que la mencione. "
        "Copia la descripción exacta. Marca como no elegible solo si choca claramente con la lista del TdR."
    )
    instrucciones = "Eres un oficial de finanzas de un donante de cooperación. Eres estricto pero no inventas prohibiciones."
    with medir_costo() as llamadas:
        auditoria = generar_estructurado(prompt, AuditoriaPresupuesto, instrucciones, temperatura=0.0)
    return auditoria, llamadas


def chequeos_auditoria(auditoria, resumen, reglas_tdr):
    """Convierte la auditoría en chequeos del semáforo, con los topes calculados por código."""
    if auditoria is None:
        return []
    chequeos, simbolo = [], SIMBOLOS.get(resumen["moneda"], resumen["moneda"])
    totales = {l["descripcion"]: l["total"] for l in resumen["lineas"]}
    for revision in auditoria.lineas:
        if not revision.elegible and revision.descripcion in totales:
            chequeos.append((ERROR, f"Gasto no elegible: «{revision.descripcion}» "
                                    f"({simbolo} {totales[revision.descripcion]:,.0f}). {revision.motivo}"))
    for i, tope in enumerate(reglas_tdr.topes_por_rubro, start=1):
        codigo = f"R{i}"
        suma = sum(totales.get(r.descripcion, 0) for r in auditoria.lineas
                   if _pertenece(r.rubros_tdr, codigo, tope.rubro))
        base = resumen["solicitado"] if tope.base == "solicitado" else resumen["total"]
        pct = suma / base if base else 0
        nivel = OK if pct <= tope.max_pct else ERROR
        chequeos.append((nivel, f"Tope de «{tope.rubro}»: {pct:.1%} del monto {'solicitado' if tope.base == 'solicitado' else 'total'} "
                                f"({simbolo} {suma:,.0f}; máximo {tope.max_pct:.0%})."))
    if auditoria.lineas and all(r.elegible for r in auditoria.lineas) and reglas_tdr.gastos_no_elegibles:
        chequeos.append((OK, "Ninguna línea choca con los gastos no elegibles del TdR."))
    return chequeos


def evaluar(propuesta, formato, resumen):
    """Puntaje estimado por criterio. Devuelve (Evaluacion, llamadas)."""
    reglas_tdr = propuesta.get("reglas_tdr")
    criterios = (reglas_tdr.criterios_evaluacion if reglas_tdr and reglas_tdr.criterios_evaluacion else CRITERIOS_BASE)
    titulos = {s["id"]: s["titulo"] for s in list(formato["secciones"]) + list(formato.get("documento", []))}
    texto = "\n\n".join(f"## {titulos.get(s.seccion_id, s.seccion_id)}\n" + "\n".join(p.texto for p in s.parrafos)
                        for s in propuesta["textos"].secciones)
    diseno = propuesta.get("tecnica")
    cuadros = (f"CUADROS DE LA PROPUESTA TÉCNICA (objetivos, metodología, entregables, equipo, riesgos):\n"
               f"{diseno.model_dump_json(indent=1)}\n\n" if diseno else "")
    prompt = (
        f"CRITERIOS DE EVALUACIÓN:\n" + "\n".join(f"- {c}" for c in criterios) + "\n\n"
        f"PROPUESTA TÉCNICA:\n{texto}\n\n{cuadros}"
        f"MATRIZ DE IMPACTO:\n{propuesta['matriz'].model_dump_json(indent=1)}\n\n"
        f"PRESUPUESTO: total {resumen['total']:,.0f} {resumen['moneda']}, solicitado {resumen['solicitado']:,.0f}, "
        f"aporte propio {resumen['pct_propio']:.0%}, {len(resumen['lineas'])} líneas, {resumen['duracion_meses']} meses.\n\n"
        "Califica cada criterio de 1 a 4 como lo haría el comité del donante. Sé exigente: un borrador con "
        "[POR COMPLETAR] o cifras sin sustento no puede tener 4. Da una mejora concreta por criterio."
    )
    instrucciones = "Eres evaluador senior de propuestas de cooperación internacional para América Latina. Eres justo y exigente."
    with medir_costo() as llamadas:
        evaluacion = generar_estructurado(prompt, Evaluacion, instrucciones, temperatura=0.1)
    return evaluacion, llamadas


def puntaje_total(evaluacion) -> float:
    """Porcentaje del puntaje máximo (4 por criterio)."""
    if not evaluacion or not evaluacion.criterios:
        return 0.0
    return sum(c.puntaje for c in evaluacion.criterios) / (4 * len(evaluacion.criterios))
