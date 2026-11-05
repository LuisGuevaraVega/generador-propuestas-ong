"""Exporta la propuesta a Word (técnica) y Excel (económica, con fórmulas editables)."""
import io
from datetime import date

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ai.generador import MODOS
from ai.reglas import SIMBOLOS

NOMBRES_FUENTE = {"TDR": "TdR", "IA": "Sugerencia IA"}


def etiqueta_fuente(fuente: str) -> str:
    if fuente in NOMBRES_FUENTE:
        return NOMBRES_FUENTE[fuente]
    if fuente.startswith("DOC:"):
        return "Propuesta previa: " + fuente[4:].split("#")[0]
    return f"Tu respuesta {fuente}"


def huella_autoria(propuesta):
    """Cuenta de dónde salió cada pieza: TdR, IA, propuestas previas o respuestas del usuario."""
    conteo = {"Tus respuestas": 0, "Tus propuestas previas": 0, "TdR": 0, "Sugerencia IA": 0}
    piezas = [p for s in propuesta["textos"].secciones for p in s.parrafos]
    m = propuesta["matriz"]
    piezas += list(m.indicadores_proyecto) + [i for oe in m.objetivos_especificos for i in oe.indicadores]
    piezas += list(propuesta["presupuesto"].lineas)
    for pieza in piezas:
        tipos = set()
        for f in pieza.fuentes:
            if f == "TDR":
                tipos.add("TdR")
            elif f == "IA":
                tipos.add("Sugerencia IA")
            elif f.startswith("DOC:"):
                tipos.add("Tus propuestas previas")
            else:
                tipos.add("Tus respuestas")
        for t in tipos or {"Sugerencia IA"}:
            conteo[t] += 1
    return conteo


def _titulo(doc, texto, nivel):
    h = doc.add_heading(texto, level=nivel)
    for r in h.runs:
        r.font.name = "Arial"
        r.font.color.rgb = RGBColor(0x0F, 0x6B, 0x5C)


def _tabla(doc, encabezados, filas):
    tabla = doc.add_table(rows=1, cols=len(encabezados))
    tabla.style = "Table Grid"
    for celda, texto in zip(tabla.rows[0].cells, encabezados):
        celda.text = texto
        celda.paragraphs[0].runs[0].font.bold = True
    for fila in filas:
        celdas = tabla.add_row().cells
        for celda, texto in zip(celdas, fila):
            celda.text = str(texto)
    return tabla


def a_word(propuesta, formato, convocatoria="", resumen=None) -> bytes:
    doc = Document()
    estilo = doc.styles["Normal"]
    estilo.font.name = "Arial"
    estilo.font.size = Pt(formato["estilo"]["tamano"])

    textos, matriz = propuesta["textos"], propuesta["matriz"]
    doc.add_heading(textos.titulo_proyecto, level=0)
    p = doc.add_paragraph()
    p.add_run("BORRADOR — ").bold = True
    p.add_run(f"generado el {date.today():%d/%m/%Y} en modo «{MODOS[propuesta['modo']]}». "
              "Revise, complete y valide cada sección antes de postular.")
    if convocatoria:
        doc.add_paragraph(f"Convocatoria: {convocatoria}")

    titulos = {s["id"]: s["titulo"] for s in formato["secciones"]}
    orden = [s["id"] for s in formato["secciones"]]
    secciones = sorted(textos.secciones, key=lambda s: orden.index(s.seccion_id) if s.seccion_id in orden else 99)
    pendientes = []

    for seccion in secciones:
        if seccion.seccion_id == "actividades":
            _matriz_word(doc, matriz, titulos)
        _titulo(doc, titulos.get(seccion.seccion_id, seccion.seccion_id), 1)
        for parrafo in seccion.parrafos:
            par = doc.add_paragraph(parrafo.texto)
            par.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        pendientes += seccion.pendientes
        if seccion.seccion_id == "actividades":
            _cronograma_word(doc, matriz, propuesta["presupuesto"].duracion_meses)

    if resumen:
        _titulo(doc, titulos.get("presupuesto", "Plan de financiamiento"), 1)
        mon = SIMBOLOS.get(resumen["moneda"], resumen["moneda"])
        filas = [(oe, f"{mon} {v:,.0f}") for oe, v in sorted(resumen["por_objetivo"].items())]
        filas += [("Reserva", f"{mon} {resumen['reserva']:,.0f}"),
                  ("Gastos administrativos", f"{mon} {resumen['administrativos']:,.0f}"),
                  ("TOTAL", f"{mon} {resumen['total']:,.0f}"),
                  ("Aporte propio", f"{mon} {resumen['aporte_propio']:,.0f} ({resumen['pct_propio']:.1%})"),
                  ("Monto solicitado", f"{mon} {resumen['solicitado']:,.0f}")]
        _tabla(doc, ["Rubro", "Monto"], filas)
        doc.add_paragraph("El detalle por línea de gasto está en el archivo Excel adjunto.")

    pendientes += matriz.pendientes + propuesta["presupuesto"].pendientes
    if pendientes:
        _titulo(doc, "Pendientes por completar", 1)
        for item in dict.fromkeys(pendientes):
            doc.add_paragraph(item, style="List Bullet")

    _titulo(doc, "Anexo: huella de autoría", 1)
    doc.add_paragraph("Origen de cada párrafo, indicador y línea de presupuesto de este borrador:")
    _tabla(doc, ["Origen", "Piezas"], list(huella_autoria(propuesta).items()))

    salida = io.BytesIO()
    doc.save(salida)
    return salida.getvalue()


def _matriz_word(doc, matriz, titulos):
    _titulo(doc, titulos.get("matriz", "Matriz de impacto"), 1)
    filas = []
    if matriz.objetivo_superior:
        filas.append(("Objetivo superior", matriz.objetivo_superior, "", "", "", ""))
    filas.append(("Objetivo del proyecto", matriz.objetivo_proyecto, "", "", "", ""))
    for i in matriz.indicadores_proyecto:
        filas.append(("", "", f"{i.codigo} {i.indicador}", i.linea_base, i.meta, i.medio_verificacion))
    for oe in matriz.objetivos_especificos:
        filas.append((oe.codigo, oe.texto, "", "", "", ""))
        for i in oe.indicadores:
            filas.append(("", "", f"{i.codigo} {i.indicador}", i.linea_base, i.meta, i.medio_verificacion))
    _tabla(doc, ["Nivel", "Objetivo", "Indicador", "Línea de base", "Meta", "Medio de verificación"], filas)


def _cronograma_word(doc, matriz, meses):
    doc.add_paragraph().add_run("Cronograma").bold = True
    meses = max(1, min(meses or 12, 36))
    filas = []
    for oe in matriz.objetivos_especificos:
        for a in oe.actividades:
            marcas = ["■" if a.mes_inicio <= m <= a.mes_fin else "" for m in range(1, meses + 1)]
            filas.append([f"{a.codigo} {a.descripcion}"] + marcas)
    tabla = _tabla(doc, ["Actividad"] + [str(m) for m in range(1, meses + 1)], filas)
    for fila in tabla.rows:
        for celda in fila.cells[1:]:
            for par in celda.paragraphs:
                for run in par.runs:
                    run.font.size = Pt(7)


def a_excel(propuesta, resumen, reglas) -> bytes:
    """Presupuesto con fórmulas: si el usuario cambia cantidades o costos, todo se recalcula."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Presupuesto"
    verde = PatternFill("solid", fgColor="E2F0EC")
    negrita = Font(bold=True)
    moneda = resumen["moneda"]

    hoja.append([f"Presupuesto — {propuesta['textos'].titulo_proyecto}"])
    hoja["A1"].font = Font(bold=True, size=13)
    hoja.append([f"Moneda: {moneda} · Duración: {resumen['duracion_meses']} meses · Reglas: {reglas['origen']}"])
    hoja.append([])
    encabezados = ["Objetivo", "Categoría", "Descripción", "Unidad", "Cantidad", "Costo unitario", "Total", "Origen"]
    hoja.append(encabezados)
    for celda in hoja[4]:
        celda.font, celda.fill = negrita, verde

    inicio = 5
    for l in resumen["lineas"]:
        fila = hoja.max_row + 1
        hoja.append([l["objetivo"], l["categoria"], l["descripcion"], l["unidad"], l["cantidad"],
                     l["costo_unitario"], f"=E{fila}*F{fila}", ", ".join(etiqueta_fuente(f) for f in l["fuentes"])])
    fin = hoja.max_row

    def fila_total(etiqueta, formula):
        hoja.append(["", "", etiqueta, "", "", "", formula])
        hoja.cell(row=hoja.max_row, column=3).font = negrita
        hoja.cell(row=hoja.max_row, column=7).font = negrita
        return hoja.max_row

    hoja.append([])
    f_gastos = fila_total("Subtotal gastos del proyecto", f"=SUM(G{inicio}:G{fin})")
    meses_ok = resumen["reserva"] > 0
    f_reserva = fila_total(f"Reserva ({reglas['reserva_pct']:.1%})",
                           f"=G{f_gastos}*{reglas['reserva_pct'] if meses_ok else 0}")
    f_admin = fila_total(f"Gastos administrativos ({reglas['admin_pct']:.1%})",
                         f"=(G{f_gastos}+G{f_reserva})*{reglas['admin_pct']}")
    f_total = fila_total("TOTAL DEL PROYECTO", f"=G{f_gastos}+G{f_reserva}+G{f_admin}")
    hoja.append([])
    hoja.append(["", "", "Aportes propios", "", "", "", ""])
    hoja.cell(row=hoja.max_row, column=3).font = negrita
    ini_ap = hoja.max_row + 1
    for a in propuesta["presupuesto"].aportes_propios:
        hoja.append(["", "", f"{a.fuente} ({a.tipo})", "", "", "", a.monto])
    fin_ap = hoja.max_row
    f_aporte = fila_total("Total aporte propio", f"=SUM(G{ini_ap}:G{fin_ap})" if fin_ap >= ini_ap else "=0")
    f_sol = fila_total("MONTO SOLICITADO AL DONANTE", f"=G{f_total}-G{f_aporte}")
    fila_total("% aporte propio", f"=IF(G{f_total}=0,0,G{f_aporte}/G{f_total})")
    hoja.cell(row=hoja.max_row, column=7).number_format = "0.0%"

    for fila in hoja.iter_rows(min_row=inicio, max_row=f_sol, min_col=6, max_col=7):
        for celda in fila:
            celda.number_format = "#,##0.00"
    anchos = [9, 13, 48, 12, 10, 14, 15, 30]
    for i, ancho in enumerate(anchos, start=1):
        hoja.column_dimensions[get_column_letter(i)].width = ancho
    for fila in hoja.iter_rows(min_row=inicio, max_row=fin, min_col=3, max_col=3):
        fila[0].alignment = Alignment(wrap_text=True, vertical="top")

    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()
