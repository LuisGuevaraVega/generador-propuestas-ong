"""Formato específico de Fondoempleo (respaldo): Formato 02 (técnica) y Formato 03 (financiera).

Parte de una propuesta ya generada en el formato base:
1. `adaptar`: el modelo produce las piezas propias de Fondoempleo (involucrados, árboles,
   alternativas, oferta y demanda de competencias, equipo, riesgos) y clasifica cada línea
   de gasto en las categorías de las bases.
2. `calcular` y `chequeos`: el código aplica las reglas de las bases en soles (monto por
   línea, duración, equipo ≤ 25 %, contrapartida ≥ 10 %, administrativos 10 %, imprevistos
   1.5 %, equipamiento ≤ 2 UIT y gastos no financiables).
3. `a_word_formato02` y `a_excel_formato03`: exportan con la estructura de los formatos.
"""
import io
import json
from pathlib import Path
from typing import List

from docx import Document
from docx.shared import Pt
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, Field

from ai.llm import generar_estructurado, medir_costo
from ai.reglas import ERROR, OK

RAIZ = Path(__file__).resolve().parent.parent
REGLAS = json.loads((RAIZ / "data" / "reglas" / "fondoempleo_eat.json").read_text(encoding="utf-8"))
CATEGORIAS = REGLAS["categorias_gasto_directo"]


class Involucrado(BaseModel):
    involucrado: str
    expectativa: int = Field(description="De -5 (se opone) a 5 (muy a favor)")
    fuerza: int = Field(description="De 1 (poca influencia) a 5 (mucha influencia)")


class Rama(BaseModel):
    texto: str
    detalle: List[str] = Field(description="Causas o medios de segundo nivel")


class Alternativa(BaseModel):
    nombre: str
    descripcion: str


class Cargo(BaseModel):
    cargo: str
    funciones: str
    competencias: str


class Riesgo(BaseModel):
    tipo: str = Field(description="operacional, contexto de cambio climático, mercado, financiero o legal")
    descripcion: str
    probabilidad: str = Field(description="baja, media o alta")
    impacto: str = Field(description="bajo, moderado o mayor")
    mitigacion: str


class LineaFE(BaseModel):
    descripcion: str = Field(description="Descripción exacta de la línea del presupuesto original")
    categoria_fe: str = Field(description="Una de las categorías de gasto directo de las bases")
    financiable: bool
    motivo: str = Field(description="Por qué no es financiable según las bases; vacío si lo es")


class AdaptacionFE(BaseModel):
    linea_fondoempleo: str = Field(description="capacitacion_laboral o fortalecimiento_organizacional")
    participantes: int = Field(description="Número de trabajadores participantes")
    fin: str = Field(description="Fin: mejora del empleo e ingresos de los beneficiarios")
    proposito: str = Field(description="Propósito: desarrollo de competencias")
    situacion_problematica: str
    involucrados: List[Involucrado]
    problema_central: str
    causas: List[Rama]
    efectos: List[str]
    objetivo_central: str
    medios: List[Rama]
    fines: List[str]
    alternativas: List[Alternativa]
    alternativa_elegida: str
    demanda_competencias: str
    oferta_competencias: str
    costos_oferta: str
    equipo: List[Cargo]
    monitoreo: str
    riesgos: List[Riesgo]
    lineas: List[LineaFE]


def adaptar(propuesta, linea_preferida="capacitacion_laboral"):
    """Devuelve (AdaptacionFE, llamadas)."""
    textos = "\n\n".join(f"[{s.seccion_id}] " + "\n".join(p.texto for p in s.parrafos)
                         for s in propuesta["textos"].secciones)
    lineas = [{"descripcion": l.descripcion, "categoria": l.categoria} for l in propuesta["presupuesto"].lineas]
    prompt = (
        f"PROPUESTA EN FORMATO BASE:\n{textos}\n\nMATRIZ:\n{propuesta['matriz'].model_dump_json(indent=1)}\n\n"
        f"LÍNEAS DE PRESUPUESTO:\n{json.dumps(lineas, ensure_ascii=False, indent=1)}\n\n"
        f"BASES DE FONDOEMPLEO (resumen):\n- Líneas: {json.dumps(REGLAS['lineas'], ensure_ascii=False)}\n"
        f"- Categorías de gasto directo: {CATEGORIAS}\n- No financiable: {REGLAS['no_financiable']}\n"
        f"- Indicadores obligatorios: {json.dumps(REGLAS['indicadores_obligatorios'], ensure_ascii=False)}\n\n"
        f"Adapta la propuesta a los Formatos 02 y 03 de Fondoempleo. Línea preferida: {linea_preferida}. "
        "El fin habla de empleo e ingresos y el propósito de competencias. Usa solo información de la propuesta; "
        "si falta algo, escribe [POR COMPLETAR]. Clasifica cada línea de presupuesto (copia la descripción exacta). "
        "El personal que gestiona el proyecto (coordinación, especialistas, asistentes) va en 'Equipo del proyecto'; "
        "'Servicios profesionales especializados' es solo para consultores o capacitadores contratados a todo costo."
    )
    instrucciones = ("Eres formulador experto en proyectos de Fondoempleo (Perú). Conoces sus bases y su rúbrica. "
                     "Escribes en español técnico y conciso.")
    with medir_costo() as llamadas:
        adaptacion = generar_estructurado(prompt, AdaptacionFE, instrucciones, temperatura=0.2)
    return adaptacion, llamadas


def calcular(propuesta, adaptacion, factor_a_soles: float):
    """Presupuesto en soles con la estructura del Formato 03."""
    clasif = {l.descripcion: l for l in adaptacion.lineas}
    aportes = sum(a.monto for a in propuesta["presupuesto"].aportes_propios) * factor_a_soles
    filas = []
    for l in propuesta["presupuesto"].lineas:
        c = clasif.get(l.descripcion)
        costo = round(l.costo_unitario * factor_a_soles, 2)
        categoria = c.categoria_fe if c else ""
        if l.categoria == "personal":  # el personal de gestión es "Equipo del proyecto" (tope 25%), no un servicio
            categoria = "Equipo del proyecto"
        filas.append({"componente": l.objetivo, "descripcion": l.descripcion, "categoria": categoria,
                      "financiable": c.financiable if c else True, "motivo": c.motivo if c else "",
                      "unidad": l.unidad, "cantidad": l.cantidad, "costo_unitario": costo,
                      "total": round(costo * l.cantidad, 2)})
    directos = sum(f["total"] for f in filas)
    contrapartida_pct = min(1.0, aportes / directos) if directos else 0
    for f in filas:  # la contrapartida se reparte en proporción; el usuario puede ajustarla en el Excel
        f["institucion"] = round(f["total"] * contrapartida_pct, 2)
        f["fondoempleo"] = round(f["total"] - f["institucion"], 2)
    directos_fe = sum(f["fondoempleo"] for f in filas)
    rp = REGLAS["reglas_presupuesto"]
    administrativos = round(directos_fe * rp["administrativos_pct"], 2)
    imprevistos = round(directos_fe * rp["imprevistos_pct"], 2)
    solicitado = round(directos_fe + administrativos + imprevistos, 2)
    return {"filas": filas, "directos": directos, "directos_fe": directos_fe, "contrapartida": round(aportes, 2),
            "administrativos": administrativos, "imprevistos": imprevistos, "solicitado": solicitado,
            "total": round(solicitado + aportes, 2), "participantes": adaptacion.participantes,
            "duracion": propuesta["presupuesto"].duracion_meses, "factor": factor_a_soles}


def chequeos(calculo, adaptacion):
    linea = REGLAS["lineas"].get(adaptacion.linea_fondoempleo, REGLAS["lineas"]["capacitacion_laboral"])
    rp, salida = REGLAS["reglas_presupuesto"], []
    s = calculo["solicitado"]
    nivel = OK if linea["monto_min"] <= s <= linea["monto_max"] else ERROR
    salida.append((nivel, f"Monto solicitado a Fondoempleo: S/ {s:,.0f} ({linea['nombre']}: "
                          f"S/ {linea['monto_min']:,.0f} a S/ {linea['monto_max']:,.0f})."))
    nivel = OK if calculo["duracion"] <= linea["duracion_max_meses"] else ERROR
    salida.append((nivel, f"Duración: {calculo['duracion']} meses (máximo {linea['duracion_max_meses']})."))
    equipo = sum(f["fondoempleo"] for f in calculo["filas"] if f["categoria"] == "Equipo del proyecto")
    pct = equipo / s if s else 0
    salida.append((OK if pct <= rp["equipo_proyecto_max_pct"] else ERROR,
                   f"Equipo del proyecto: {pct:.1%} del monto solicitado (máximo {rp['equipo_proyecto_max_pct']:.0%})."))
    contra = calculo["contrapartida"] / calculo["directos_fe"] if calculo["directos_fe"] else 0
    salida.append((OK if contra >= rp["contrapartida_min_pct"] else ERROR,
                   f"Contrapartida: {contra:.1%} de los costos directos pedidos (mínimo {rp['contrapartida_min_pct']:.0%})."))
    equip = sum(f["fondoempleo"] for f in calculo["filas"] if f["categoria"] == "Equipamiento básico")
    tope = rp["equipamiento_max_uit"] * rp["uit_soles"]
    salida.append((OK if equip <= tope else ERROR,
                   f"Equipamiento: S/ {equip:,.0f} (máximo {rp['equipamiento_max_uit']} UIT = S/ {tope:,.0f})."))
    for f in calculo["filas"]:
        if not f["financiable"]:
            salida.append((ERROR, f"No financiable por Fondoempleo: «{f['descripcion']}» (S/ {f['total']:,.0f}). {f['motivo']}"))
    if calculo["participantes"]:
        costo = s / calculo["participantes"]
        lo, hi = linea["inversion_promedio_por_beneficiario"]
        salida.append((OK, f"Costo por participante: S/ {costo:,.0f} (referencia de las bases: S/ {lo:,} a S/ {hi:,})."))
    return salida


def _tabla(doc, encabezados, filas):
    t = doc.add_table(rows=1, cols=len(encabezados))
    t.style = "Table Grid"
    for celda, texto in zip(t.rows[0].cells, encabezados):
        celda.text = texto
        celda.paragraphs[0].runs[0].font.bold = True
    for fila in filas:
        for celda, texto in zip(t.add_row().cells, fila):
            celda.text = str(texto)


def a_word_formato02(propuesta, adaptacion) -> bytes:
    doc = Document()
    estilo = doc.styles["Normal"]
    estilo.font.name, estilo.font.size = "Arial", Pt(10)
    doc.add_heading("FORMATO N° 02 — PROPUESTA TÉCNICA DEL PROYECTO", level=1)
    linea = REGLAS["lineas"].get(adaptacion.linea_fondoempleo, {}).get("nombre", adaptacion.linea_fondoempleo)
    doc.add_paragraph(f"Nombre del proyecto: {propuesta['textos'].titulo_proyecto}")
    doc.add_paragraph(f"Línea de proyecto: {linea}")
    doc.add_paragraph("BORRADOR: revise y complete antes de postular.").runs[0].bold = True

    doc.add_heading("1. Situación problemática", level=2)
    doc.add_paragraph(adaptacion.situacion_problematica)
    doc.add_heading("2. Análisis de involucrados", level=2)
    _tabla(doc, ["Involucrado", "Expectativa", "Fuerza", "Resultante"],
           [(i.involucrado, i.expectativa, i.fuerza, i.expectativa * i.fuerza) for i in adaptacion.involucrados])
    doc.add_heading("3. Análisis de problemas", level=2)
    doc.add_paragraph(f"Problema central: {adaptacion.problema_central}")
    for causa in adaptacion.causas:
        doc.add_paragraph(causa.texto, style="List Bullet")
        for d in causa.detalle:
            doc.add_paragraph(d, style="List Bullet 2")
    doc.add_paragraph("Efectos: " + "; ".join(adaptacion.efectos))
    doc.add_heading("4. Análisis de objetivos", level=2)
    doc.add_paragraph(f"Objetivo central: {adaptacion.objetivo_central}")
    for medio in adaptacion.medios:
        doc.add_paragraph(medio.texto, style="List Bullet")
        for d in medio.detalle:
            doc.add_paragraph(d, style="List Bullet 2")
    doc.add_paragraph("Fines: " + "; ".join(adaptacion.fines))
    doc.add_heading("5. Análisis e identificación de alternativas", level=2)
    for a in adaptacion.alternativas:
        doc.add_paragraph(f"{a.nombre}: {a.descripcion}", style="List Bullet")
    doc.add_heading("6. Análisis de alternativas para la selección de la solución óptima", level=2)
    doc.add_paragraph(f"Alternativa seleccionada: {adaptacion.alternativa_elegida}")
    _tabla(doc, ["Aspecto", "Análisis"], [
        ("Identificación de la demanda de desarrollo de competencias", adaptacion.demanda_competencias),
        ("Identificación de la oferta de desarrollo de competencias", adaptacion.oferta_competencias),
        ("Costos de la oferta de desarrollo de competencias", adaptacion.costos_oferta)])
    doc.add_heading("7. Estructura analítica del proyecto", level=2)
    m = propuesta["matriz"]
    doc.add_paragraph(f"Fin: {adaptacion.fin}")
    doc.add_paragraph(f"Propósito: {adaptacion.proposito}")
    for oe in m.objetivos_especificos:
        doc.add_paragraph(f"Componente {oe.codigo}: {oe.texto}", style="List Bullet")
        for a in oe.actividades:
            doc.add_paragraph(f"{a.codigo} {a.descripcion}", style="List Bullet 2")
    doc.add_heading("8. Árbol de problemas y soluciones", level=2)
    _tabla(doc, ["Problema / causa", "Solución / medio"],
           [(adaptacion.problema_central, adaptacion.objetivo_central)] +
           [(c.texto, md.texto) for c, md in zip(adaptacion.causas, adaptacion.medios)])

    doc.add_heading("9. Matriz de marco lógico", level=2)
    ind = REGLAS["indicadores_obligatorios"]
    filas = [("Fin", adaptacion.fin, "; ".join(ind["fin"]), "Ficha socioeconómica inicial y final", "")]
    filas.append(("Propósito", adaptacion.proposito, "; ".join(ind["proposito"]), "Actas de evaluación y certificados", ""))
    for oe in m.objetivos_especificos:
        filas.append((f"Componente {oe.codigo}", oe.texto, "; ".join(f"{i.indicador} (LB: {i.linea_base}; meta: {i.meta})"
                                                                    for i in oe.indicadores),
                      "; ".join(i.medio_verificacion for i in oe.indicadores), ""))
        for a in oe.actividades:
            filas.append(("Actividad", f"{a.codigo} {a.descripcion}", f"Meses {a.mes_inicio} a {a.mes_fin}", "", ""))
    _tabla(doc, ["Nivel", "Objetivos", "Indicadores", "Medios de verificación", "Supuestos"], filas)
    doc.add_heading("10. Equipo del proyecto", level=2)
    _tabla(doc, ["Cargo", "Funciones a realizar", "Competencias exigibles"],
           [(c.cargo, c.funciones, c.competencias) for c in adaptacion.equipo])
    doc.add_heading("11. Sistema de seguimiento y monitoreo", level=2)
    doc.add_paragraph(adaptacion.monitoreo)
    doc.add_heading("12. Mapeo de riesgos", level=2)
    _tabla(doc, ["Tipo de riesgo", "Descripción", "Probabilidad", "Impacto", "Medidas de mitigación"],
           [(r.tipo, r.descripcion, r.probabilidad, r.impacto, r.mitigacion) for r in adaptacion.riesgos])
    salida = io.BytesIO()
    doc.save(salida)
    return salida.getvalue()


def a_excel_formato03(propuesta, calculo) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Formato 03"
    negrita, verde = Font(bold=True), PatternFill("solid", fgColor="E2F0EC")
    hoja.append(["FORMATO N° 03 — Propuesta Financiera del Proyecto"])
    hoja["A1"].font = Font(bold=True, size=13)
    hoja.append([f"Nombre del proyecto: {propuesta['textos'].titulo_proyecto}"])
    hoja.append([f"Montos en soles (factor de conversión {calculo['factor']:.4f}, tipo de cambio BCRP). "
                 "La contrapartida se repartió en proporción a cada línea: ajústela."])
    hoja.append([])
    hoja.append(["1. Análisis de los costos del proyecto — COSTOS DIRECTOS"])
    hoja.cell(row=hoja.max_row, column=1).font = negrita
    enc = ["Componente / actividad", "Categoría (ver bases)", "Unidad", "Cantidad", "Costo unitario", "Costo total",
           "FONDOEMPLEO", "INSTITUCIÓN PROPONENTE", "ALIADO 1", "BENEFICIARIOS"]
    hoja.append(enc)
    for c in hoja[hoja.max_row]:
        c.font, c.fill = negrita, verde
    inicio = hoja.max_row + 1
    for f in calculo["filas"]:
        r = hoja.max_row + 1
        hoja.append([f"{f['componente']} — {f['descripcion']}", f["categoria"] + ("" if f["financiable"] else " (NO FINANCIABLE)"),
                     f["unidad"], f["cantidad"], f["costo_unitario"], f"=D{r}*E{r}", f"=F{r}-H{r}", f["institucion"], 0, 0])
    fin = hoja.max_row
    hoja.append(["Total costos directos", "", "", "", "", f"=SUM(F{inicio}:F{fin})", f"=SUM(G{inicio}:G{fin})",
                 f"=SUM(H{inicio}:H{fin})", f"=SUM(I{inicio}:I{fin})", f"=SUM(J{inicio}:J{fin})"])
    f_dir = hoja.max_row
    hoja.append([])
    hoja.append(["COSTOS INDIRECTOS"])
    hoja.cell(row=hoja.max_row, column=1).font = negrita
    rp = REGLAS["reglas_presupuesto"]
    hoja.append(["Administrativos", f"{rp['administrativos_pct']:.0%} de costos directos FONDOEMPLEO", "", "", "",
                 f"=G{f_dir}*{rp['administrativos_pct']}", f"=G{f_dir}*{rp['administrativos_pct']}"])
    f_adm = hoja.max_row
    hoja.append(["Imprevistos", f"{rp['imprevistos_pct']:.1%} de costos directos FONDOEMPLEO", "", "", "",
                 f"=G{f_dir}*{rp['imprevistos_pct']}", f"=G{f_dir}*{rp['imprevistos_pct']}"])
    f_imp = hoja.max_row
    hoja.append(["Costo total del proyecto", "", "", "", "", f"=F{f_dir}+F{f_adm}+F{f_imp}", f"=G{f_dir}+G{f_adm}+G{f_imp}",
                 f"=H{f_dir}", f"=I{f_dir}", f"=J{f_dir}"])
    f_tot = hoja.max_row
    hoja.append([])
    hoja.append(["2. Análisis Costo / Beneficio (C/B)"])
    hoja.cell(row=hoja.max_row, column=1).font = negrita
    hoja.append(["N° de participantes", calculo["participantes"]])
    f_par = hoja.max_row
    hoja.append(["Costo promedio por trabajador con financiamiento de FONDOEMPLEO (A)", f"=G{f_tot}/B{f_par}"])
    hoja.append(["Costo promedio por trabajador participante (B)", f"=F{f_tot}/B{f_par}"])
    hoja.append([])
    hoja.append(["4. Fuente de financiamiento", "Monto"])
    hoja.cell(row=hoja.max_row, column=1).font = negrita
    for nombre, col in [("FONDOEMPLEO", "G"), ("Institución proponente", "H"), ("Aliado 1", "I"), ("Beneficiarios", "J")]:
        hoja.append([nombre, f"={col}{f_tot}"])
    hoja.append(["TOTAL", f"=F{f_tot}"])
    for fila in hoja.iter_rows(min_row=inicio, max_row=hoja.max_row, min_col=2, max_col=10):
        for c in fila:
            c.number_format = "#,##0.00"
    for i, ancho in enumerate([48, 30, 10, 10, 14, 14, 14, 16, 12, 14], start=1):
        hoja.column_dimensions[get_column_letter(i)].width = ancho
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()
