"""Validación determinística de las reglas del donante.

La IA redacta; las reglas las verifica este código, no el modelo. Así los
topes y porcentajes son exactos y explicables.
"""
import re

OK, ALERTA, ERROR = "ok", "alerta", "error"

_META_ES_ACTIVIDAD = re.compile(
    r"(se (realizaron|ejecutaron|desarrollaron|dictaron)|talleres? (realizados?|ejecutados?)|n[uú]mero de (talleres|capacitaciones|sesiones))",
    re.IGNORECASE,
)
_META_ES_PRODUCTO = re.compile(
    r"\b(reciben|recibieron|completan|completaron|asisten|asistieron|participan|participaron|formad[oa]s|capacitad[oa]s|entregad[oa]s|realizad[oa]s|ejecutad[oa]s)\b",
    re.IGNORECASE,
)
_LINEA_BASE_VACIA = re.compile(
    r"^\s*(0+\s*%?(\s*\(.*\))?|ninguno|ninguna|no hay|no tienen?|n/?a|-)?\s*\.?\s*$", re.IGNORECASE
)


def calcular_presupuesto(presupuesto, reglas):
    """Calcula totales, reserva, gastos administrativos y fuentes; devuelve (resumen, chequeos)."""
    lineas = []
    for linea in presupuesto.lineas:
        total = round(linea.cantidad * linea.costo_unitario, 2)
        lineas.append({**linea.model_dump(), "total": total})

    gastos = round(sum(l["total"] for l in lineas), 2)
    meses = presupuesto.duracion_meses
    reserva_permitida = meses >= reglas["reserva_min_meses_proyecto"]
    reserva = round(gastos * reglas["reserva_max_pct"], 2) if reserva_permitida else 0.0
    administrativos = round((gastos + reserva) * reglas["administrativos_max_pct"], 2)
    total = round(gastos + reserva + administrativos, 2)

    aporte_propio = round(sum(a.monto for a in presupuesto.aportes_propios), 2)
    solicitado = round(total - aporte_propio, 2)
    pct_solicitado = solicitado / total if total else 0
    pct_propio = aporte_propio / total if total else 0

    por_categoria, por_objetivo = {}, {}
    for l in lineas:
        por_categoria[l["categoria"]] = por_categoria.get(l["categoria"], 0) + l["total"]
        por_objetivo[l["objetivo"]] = por_objetivo.get(l["objetivo"], 0) + l["total"]

    chequeos = []
    tope = reglas["financiamiento_max_pct"]
    if pct_solicitado <= tope:
        chequeos.append((OK, f"Financiamiento solicitado: {pct_solicitado:.1%} del total (máximo {tope:.0%})."))
    else:
        falta = round(total * reglas["aporte_propio_min_pct"] - aporte_propio, 2)
        chequeos.append((
            ERROR,
            f"Se pide {pct_solicitado:.1%} al donante y el máximo es {tope:.0%}. "
            f"Falta aporte propio de € {falta:,.0f} o reducir gastos.",
        ))

    if reserva_permitida:
        chequeos.append((OK, f"Reserva de {reglas['reserva_max_pct']:.1%} incluida (proyecto de {meses} meses)."))
    else:
        chequeos.append((ALERTA, f"Sin reserva: el proyecto dura {meses} meses y la reserva solo aplica a más de 12."))

    chequeos.append((OK, f"Gastos administrativos al máximo permitido ({reglas['administrativos_max_pct']:.0%})."))

    categorias_validas = set(reglas["categorias_gasto"])
    raras = sorted({l["categoria"] for l in lineas} - categorias_validas)
    if raras:
        chequeos.append((ALERTA, f"Categorías no reconocidas: {', '.join(raras)}."))

    resumen = {
        "lineas": lineas,
        "gastos": gastos,
        "reserva": reserva,
        "administrativos": administrativos,
        "total": total,
        "aporte_propio": aporte_propio,
        "solicitado": solicitado,
        "pct_solicitado": pct_solicitado,
        "pct_propio": pct_propio,
        "por_categoria": por_categoria,
        "por_objetivo": por_objetivo,
        "duracion_meses": meses,
    }
    return resumen, chequeos


def validar_matriz(matriz, reglas, monto_solicitado=None):
    """Revisa la matriz de impacto contra las reglas del formato."""
    chequeos = []
    minimo, maximo = reglas["indicadores_por_objetivo_especifico"]
    for oe in matriz.objetivos_especificos:
        n = len(oe.indicadores)
        if minimo <= n <= maximo:
            chequeos.append((OK, f"{oe.codigo}: {n} indicador(es)."))
        else:
            chequeos.append((ALERTA, f"{oe.codigo}: tiene {n} indicadores; se recomiendan entre {minimo} y {maximo}."))

    todos = list(matriz.indicadores_proyecto) + [i for oe in matriz.objetivos_especificos for i in oe.indicadores]
    for ind in todos:
        if _META_ES_ACTIVIDAD.search(ind.meta) or _META_ES_ACTIVIDAD.search(ind.indicador):
            chequeos.append((ERROR, f"{ind.codigo}: la meta mide una actividad, no un efecto. Reformúlala como cambio en las personas."))
        elif _META_ES_PRODUCTO.search(ind.indicador):
            chequeos.append((ALERTA, f"{ind.codigo}: parece medir la entrega de un servicio (producto), no el cambio que produce."))
        if _LINEA_BASE_VACIA.match(ind.linea_base or ""):
            chequeos.append((ALERTA, f"{ind.codigo}: la línea de base está vacía o en cero. Usa un valor estimado."))

    umbral = reglas["objetivo_superior_obligatorio_desde_eur"]
    if monto_solicitado is not None and monto_solicitado > umbral and not (matriz.objetivo_superior or "").strip():
        chequeos.append((ERROR, f"Se piden más de € {umbral:,.0f}: el objetivo superior es obligatorio."))

    if not any(nivel != OK for nivel, _ in chequeos):
        chequeos.append((OK, "Matriz coherente con las reglas del formato."))
    return chequeos
