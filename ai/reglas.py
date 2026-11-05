"""Validación determinística de las reglas del donante.

La IA redacta; las reglas las verifica este código, no el modelo. Así los
topes y porcentajes son exactos y explicables. Las reglas del TdR mandan;
donde el TdR no dice nada se usan las del formato base (BMZ).
"""
import re

OK, ALERTA, ERROR = "ok", "alerta", "error"

SIMBOLOS = {"EUR": "€", "PEN": "S/", "USD": "US$", "AUD": "A$"}

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


def reglas_efectivas(formato, reglas_tdr=None):
    """Combina las reglas del formato base con las del TdR. Devuelve un dict con su origen."""
    base = formato["reglas"]
    r = {
        "moneda": formato["moneda"],
        "aporte_min_pct": base["aporte_propio_min_pct"],
        "reserva_pct": base["reserva_max_pct"],
        "reserva_min_meses": base["reserva_min_meses_proyecto"],
        "admin_pct": base["administrativos_max_pct"],
        "monto_min": None,
        "monto_max": None,
        "duracion_max": None,
        "personal_max_pct": None,
        "objetivo_superior_desde": base["objetivo_superior_obligatorio_desde_eur"],
        "indicadores_por_oe": base["indicadores_por_objetivo_especifico"],
        "categorias": base["categorias_gasto"],
        "no_elegibles": [],
        "origen": "Formato base BMZ",
    }
    if reglas_tdr is None:
        return r

    t = reglas_tdr
    r.update({
        "moneda": t.moneda or r["moneda"],
        "aporte_min_pct": t.contrapartida_min_pct if t.contrapartida_min_pct is not None else 0.0,
        "reserva_pct": t.imprevistos_pct or 0.0,
        "reserva_min_meses": 0,
        "admin_pct": t.administrativos_max_pct or 0.0,
        "monto_min": t.monto_min,
        "monto_max": t.monto_max,
        "duracion_max": t.duracion_max_meses,
        "personal_max_pct": t.personal_max_pct,
        "objetivo_superior_desde": None,
        "no_elegibles": t.gastos_no_elegibles,
        "origen": f"TdR: {t.donante}",
    })
    return r


def _dinero(monto, moneda):
    return f"{SIMBOLOS.get(moneda, moneda)} {monto:,.0f}"


def calcular_presupuesto(presupuesto, reglas):
    """Calcula totales, reserva, gastos administrativos y fuentes; devuelve (resumen, chequeos)."""
    moneda = reglas["moneda"]
    lineas = [{**l.model_dump(), "total": round(l.cantidad * l.costo_unitario, 2)} for l in presupuesto.lineas]

    gastos = round(sum(l["total"] for l in lineas), 2)
    meses = presupuesto.duracion_meses
    con_reserva = reglas["reserva_pct"] > 0 and meses >= reglas["reserva_min_meses"]
    reserva = round(gastos * reglas["reserva_pct"], 2) if con_reserva else 0.0
    administrativos = round((gastos + reserva) * reglas["admin_pct"], 2)
    total = round(gastos + reserva + administrativos, 2)

    aporte_propio = round(sum(a.monto for a in presupuesto.aportes_propios), 2)
    solicitado = round(total - aporte_propio, 2)
    pct_propio = aporte_propio / total if total else 0
    personal = sum(l["total"] for l in lineas if l["categoria"] == "personal")

    por_categoria, por_objetivo = {}, {}
    for l in lineas:
        por_categoria[l["categoria"]] = por_categoria.get(l["categoria"], 0) + l["total"]
        por_objetivo[l["objetivo"]] = por_objetivo.get(l["objetivo"], 0) + l["total"]

    chequeos = []
    moneda_montos = (presupuesto.moneda or moneda).upper()
    if moneda_montos != moneda.upper():
        chequeos.append((ERROR, f"Los montos están en {moneda_montos} y la convocatoria pide {moneda}: "
                                f"convierte el presupuesto antes de comparar con los topes."))
        moneda = moneda_montos
    minimo = reglas["aporte_min_pct"]
    if minimo:
        if pct_propio >= minimo:
            chequeos.append((OK, f"Aporte propio: {pct_propio:.1%} del total (mínimo {minimo:.0%})."))
        else:
            falta = round(total * minimo - aporte_propio, 2)
            chequeos.append((ERROR, f"Aporte propio de {pct_propio:.1%} y el mínimo es {minimo:.0%}: "
                                    f"faltan {_dinero(falta, moneda)} de aporte o reducir gastos."))

    if reglas["monto_max"] and solicitado > reglas["monto_max"]:
        chequeos.append((ERROR, f"Se piden {_dinero(solicitado, moneda)} y el máximo es {_dinero(reglas['monto_max'], moneda)}."))
    elif reglas["monto_min"] and solicitado < reglas["monto_min"]:
        chequeos.append((ERROR, f"Se piden {_dinero(solicitado, moneda)} y el mínimo es {_dinero(reglas['monto_min'], moneda)}."))
    elif reglas["monto_max"] or reglas["monto_min"]:
        chequeos.append((OK, f"Monto solicitado de {_dinero(solicitado, moneda)} dentro del rango del TdR."))

    if reglas["duracion_max"]:
        if meses > reglas["duracion_max"]:
            chequeos.append((ERROR, f"El proyecto dura {meses} meses y el máximo es {reglas['duracion_max']}."))
        else:
            chequeos.append((OK, f"Duración de {meses} meses (máximo {reglas['duracion_max']})."))

    if reglas["personal_max_pct"] and solicitado:
        pct = personal / solicitado
        nivel = OK if pct <= reglas["personal_max_pct"] else ERROR
        chequeos.append((nivel, f"Personal: {pct:.1%} del monto solicitado (máximo {reglas['personal_max_pct']:.0%})."))

    if con_reserva:
        chequeos.append((OK, f"Reserva para imprevistos de {reglas['reserva_pct']:.1%} incluida."))
    elif reglas["reserva_pct"] > 0:
        chequeos.append((ALERTA, f"Sin reserva: el proyecto dura {meses} meses y la reserva solo aplica desde {reglas['reserva_min_meses']}."))
    if reglas["admin_pct"]:
        chequeos.append((OK, f"Gastos administrativos al {reglas['admin_pct']:.1%}."))

    raras = sorted({l["categoria"] for l in lineas} - set(reglas["categorias"]))
    if raras:
        chequeos.append((ALERTA, f"Categorías no reconocidas: {', '.join(raras)}."))

    resumen = {
        "moneda": moneda, "lineas": lineas, "gastos": gastos, "reserva": reserva,
        "administrativos": administrativos, "total": total, "aporte_propio": aporte_propio,
        "solicitado": solicitado, "pct_propio": pct_propio, "pct_solicitado": 1 - pct_propio if total else 0,
        "por_categoria": por_categoria, "por_objetivo": por_objetivo, "duracion_meses": meses,
    }
    return resumen, chequeos


def validar_matriz(matriz, reglas, monto_solicitado=None):
    """Revisa la matriz de impacto contra las reglas del formato."""
    chequeos = []
    minimo, maximo = reglas["indicadores_por_oe"]
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

    umbral = reglas["objetivo_superior_desde"]
    if umbral and monto_solicitado is not None and monto_solicitado > umbral and not (matriz.objetivo_superior or "").strip():
        chequeos.append((ERROR, f"Se piden más de € {umbral:,.0f}: el objetivo superior es obligatorio."))

    if not any(nivel != OK for nivel, _ in chequeos):
        chequeos.append((OK, "Matriz coherente con las reglas del formato."))
    return chequeos
