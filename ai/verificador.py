"""Verificador de cifras: detecta números del borrador que no aparecen en ninguna fuente.

Es una defensa contra las "alucinaciones" hecha con código, no con el prompt:
cada porcentaje, monto, año o cantidad que escribió el modelo debe existir en
el material de partida (respuestas, TdR, propuestas anteriores, datos públicos)
o en el presupuesto calculado. Si no, se marca para que el usuario lo valide.
"""
import re

_NUMERO = re.compile(r"(?<![\w.,/])(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)(?![\w])\s*(%|por\s*ciento)?", re.IGNORECASE)
_CADA = re.compile(r"(\d+)\s+de\s+cada\s+(\d+)", re.IGNORECASE)
_PALABRAS = {"uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
             "ocho": 8, "nueve": 9, "diez": 10}
_CADA_PALABRAS = re.compile(r"\b(" + "|".join(_PALABRAS) + r")\s+de\s+cada\s+(diez|10)\b", re.IGNORECASE)
_PENDIENTE = re.compile(r"\[POR COMPLETAR[^\]]*\]", re.IGNORECASE)
MINIMO_RELEVANTE = 13  # números chicos (meses, componentes, sesiones) generan mucho ruido


def _a_numero(texto: str) -> float:
    """'1,100' -> 1100 · '1.100' -> 1100 · '3,5' -> 3.5 · '3.5' -> 3.5"""
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", texto):
        return float(re.sub(r"[.,]", "", texto))
    return float(texto.replace(",", "."))


def numeros_en(texto: str) -> set:
    """Todos los valores numéricos de un texto, incluidos los de 'N de cada M' como porcentaje."""
    valores = {_a_numero(m.group(1)) for m in _NUMERO.finditer(texto or "")}
    for m in _CADA.finditer(texto or ""):
        valores.add(round(int(m.group(1)) / int(m.group(2)) * 100, 1))
    for m in _CADA_PALABRAS.finditer(texto or ""):
        valores.add(_PALABRAS[m.group(1).lower()] * 10.0)
    return valores


def _respaldado(valor: float, fuentes: set) -> bool:
    return any(abs(valor - f) <= max(0.5, abs(f) * 0.005) for f in fuentes)


def _fragmento(texto: str, inicio: int, fin: int, margen: int = 45) -> str:
    a, b = max(0, inicio - margen), min(len(texto), fin + margen)
    return ("…" if a else "") + texto[a:b].replace("\n", " ") + ("…" if b < len(texto) else "")


def verificar(propuesta: dict, resumen_presupuesto: dict = None) -> list:
    """Devuelve [{'seccion', 'cifra', 'fragmento'}] con las cifras sin respaldo."""
    fuentes = numeros_en(propuesta.get("contexto", ""))
    if propuesta.get("reglas_tdr") is not None:
        fuentes |= numeros_en(propuesta["reglas_tdr"].model_dump_json())
    if resumen_presupuesto:
        for linea in resumen_presupuesto["lineas"]:
            fuentes |= {linea["cantidad"], linea["costo_unitario"], linea["total"]}
        fuentes |= {resumen_presupuesto[k] for k in ("gastos", "reserva", "administrativos", "total",
                                                     "aporte_propio", "solicitado")}
        fuentes.add(round(resumen_presupuesto["pct_propio"] * 100, 1))
        fuentes.add(float(resumen_presupuesto["duracion_meses"]))

    piezas = [(s.seccion_id, p.texto) for s in propuesta["textos"].secciones for p in s.parrafos]
    matriz = propuesta["matriz"]
    for ind in list(matriz.indicadores_proyecto) + [i for oe in matriz.objetivos_especificos for i in oe.indicadores]:
        for campo in (ind.linea_base, ind.meta):
            if "estimad" not in campo.lower():  # los estimados ya están declarados como tales
                piezas.append(("matriz", f"{ind.codigo}: {campo}"))

    hallazgos, vistos = [], set()
    for seccion, texto in piezas:
        limpio = _PENDIENTE.sub(" ", texto)
        for m in _NUMERO.finditer(limpio):
            valor = _a_numero(m.group(1))
            if valor < MINIMO_RELEVANTE and not m.group(2):
                continue
            if _respaldado(valor, fuentes) or (seccion, valor) in vistos:
                continue
            vistos.add((seccion, valor))
            hallazgos.append({"seccion": seccion, "cifra": m.group(0).strip(),
                              "fragmento": _fragmento(limpio, m.start(), m.end())})
    return hallazgos
