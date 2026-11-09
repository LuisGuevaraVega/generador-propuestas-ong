"""Exporta la propuesta a Word (técnica) y Excel (económica, con fórmulas editables).

Los reportes son para el donante: no incluyen la huella de autoría, que solo se
muestra dentro de la app para el usuario. La propuesta técnica no lleva montos:
en muchas convocatorias la técnica y la económica se presentan por separado.
"""
import io
import re
from datetime import date

from docx import Document
from docx.enum.section import WD_ORIENT  # noqa: F401  (disponible para anexos apaisados)
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ai.reglas import SIMBOLOS

NOMBRES_FUENTE = {"TDR": "TdR", "IA": "Sugerencia IA", "USUARIO": "Editado por ti", "ENAHO": "ENAHO (INEI)",
                  "BID": "Proyecto similar del BID", "BMZ": "Proyecto similar de la cooperación alemana"}
VERDE = "0F6B5C"
VERDE_CLARO = "E3F1ED"
GRIS = "F3F5F4"


def etiqueta_fuente(fuente: str) -> str:
    if fuente in NOMBRES_FUENTE:
        return NOMBRES_FUENTE[fuente]
    if fuente.startswith("DOC:"):
        return "Propuesta previa: " + fuente[4:].split("#")[0]
    return f"Tu respuesta {fuente}"


def huella_autoria(propuesta):
    """Cuenta de dónde salió cada pieza: TdR, IA, propuestas previas o respuestas del usuario."""
    conteo = {"Tus respuestas": 0, "Tus propuestas previas": 0, "TdR y datos públicos": 0, "Sugerencia IA": 0}
    piezas = [p for s in propuesta["textos"].secciones for p in s.parrafos]
    m = propuesta["matriz"]
    piezas += list(m.indicadores_proyecto) + [i for oe in m.objetivos_especificos for i in oe.indicadores]
    piezas += list(propuesta["presupuesto"].lineas)
    for pieza in piezas:
        tipos = set()
        for f in pieza.fuentes:
            if f in ("TDR", "ENAHO", "BID", "BMZ"):
                tipos.add("TdR y datos públicos")
            elif f == "IA":
                tipos.add("Sugerencia IA")
            elif f.startswith("DOC:"):
                tipos.add("Tus propuestas previas")
            else:
                tipos.add("Tus respuestas")
        for t in tipos or {"Sugerencia IA"}:
            conteo[t] += 1
    return conteo


# ================================================================ Word: piezas de formato
def _sombrear(celda, color):
    propiedades = celda._tc.get_or_add_tcPr()
    for anterior in propiedades.findall(qn("w:shd")):
        propiedades.remove(anterior)
    sombra = OxmlElement("w:shd")
    sombra.set(qn("w:val"), "clear")
    sombra.set(qn("w:color"), "auto")
    sombra.set(qn("w:fill"), color)
    propiedades.append(sombra)


def _titulo(doc, texto, nivel):
    h = doc.add_heading(texto, level=nivel)
    for r in h.runs:
        r.font.name = "Arial"
        r.font.color.rgb = RGBColor(0x0F, 0x6B, 0x5C)
    return h


def _celda(celda, valor, negrita=False, tamano=9.5, color=None):
    """Escribe texto o una lista (con viñetas) en una celda."""
    celda.text = ""
    lineas = valor if isinstance(valor, (list, tuple)) else [valor]
    for i, linea in enumerate(lineas):
        par = celda.paragraphs[0] if i == 0 else celda.add_paragraph()
        par.paragraph_format.space_after = Pt(1)
        texto = f"• {linea}" if isinstance(valor, (list, tuple)) and len(lineas) > 1 else str(linea)
        run = par.add_run(texto)
        run.font.size = Pt(tamano)
        run.bold = negrita
        if color:
            run.font.color.rgb = RGBColor.from_string(color)


def _tabla(doc, encabezados, filas, anchos=None):
    """Tabla con encabezado verde y texto blanco; acepta listas en las celdas."""
    tabla = doc.add_table(rows=1, cols=len(encabezados))
    tabla.style = "Table Grid"
    tabla.alignment = WD_TABLE_ALIGNMENT.CENTER
    tabla.autofit = False
    for celda, texto in zip(tabla.rows[0].cells, encabezados):
        _celda(celda, texto, negrita=True, color="FFFFFF")
        _sombrear(celda, VERDE)
    for n, fila in enumerate(filas):
        celdas = tabla.add_row().cells
        for celda, valor in zip(celdas, fila):
            _celda(celda, valor)
            if n % 2:
                _sombrear(celda, GRIS)
    if anchos:
        for fila in tabla.rows:
            for celda, ancho in zip(fila.cells, anchos):
                celda.width = Cm(ancho)
    doc.add_paragraph()
    return tabla


def _parrafos(doc, seccion):
    """Párrafos justificados; 'Etiqueta: texto' se escribe con la etiqueta en negrita."""
    if seccion is None:
        return
    for parrafo in seccion.parrafos:
        par = doc.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        m = re.match(r"^([^:.]{2,60}):\s+(.*)$", parrafo.texto, re.S)
        if m:
            par.add_run(m.group(1) + ": ").bold = True
            par.add_run(m.group(2))
        else:
            par.add_run(parrafo.texto)


def _vinetas(doc, items):
    for item in items:
        doc.add_paragraph(item, style="List Bullet")


def _pie_de_pagina(doc, texto):
    pie = doc.sections[0].footer.paragraphs[0]
    pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = pie.add_run(f"{texto} · Página ")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    for tipo, valor in (("begin", None), (None, "PAGE"), ("end", None)):
        r = pie.add_run()
        r.font.size = Pt(8)
        if tipo:
            campo = OxmlElement("w:fldChar")
            campo.set(qn("w:fldCharType"), tipo)
            r._r.append(campo)
        else:
            instr = OxmlElement("w:instrText")
            instr.set(qn("xml:space"), "preserve")
            instr.text = valor
            r._r.append(instr)


def _portada(doc, tecnica, convocatoria):
    d = tecnica.datos
    for _ in range(3):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("PROPUESTA TÉCNICA")
    r.bold, r.font.size, r.font.color.rgb = True, Pt(24), RGBColor(0x0F, 0x6B, 0x5C)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("para el servicio de:").font.size = Pt(12)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(d.nombre_servicio.upper())
    r.bold, r.font.size = True, Pt(15)
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("Presentado a: ").bold = True
    p.add_run(d.presentado_a)
    doc.add_paragraph()
    filas = [("Nombre del servicio", d.nombre_servicio), ("Presentado a", d.presentado_a),
             ("Sistema de contratación", d.sistema_contratacion), ("Plazo de ejecución", d.plazo_ejecucion),
             ("Ámbito", d.ambito), ("Postor", d.postor)]
    if convocatoria and convocatoria != d.nombre_servicio:
        filas.insert(1, ("Convocatoria", convocatoria))
    # La propuesta técnica no lleva montos: se descartan los datos de dinero aunque el modelo los ponga.
    dinero = re.compile(r"monto|precio|presupuest|costo|tope|financ|S/|US\$|€|AUD|USD|EUR", re.I)
    filas += [(o.campo, o.valor) for o in d.otros if not dinero.search(f"{o.campo} {o.valor}")]
    tabla = _tabla(doc, ["Datos de referencia", ""], filas, anchos=[5, 11])
    for fila in tabla.rows[1:]:
        _sombrear(fila.cells[0], VERDE_CLARO)
        for run in fila.cells[0].paragraphs[0].runs:
            run.bold = True
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"Borrador — versión del {date.today():%d/%m/%Y}. Revise, complete y valide antes de presentar.")
    r.italic, r.font.size, r.font.color.rgb = True, Pt(8), RGBColor(0x88, 0x88, 0x88)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ================================================================ Word: bloques de contenido
def _bloque(doc, nombre, ctx, nivel):
    """Escribe un bloque de contenido. `nivel` es el nivel de los subtítulos internos."""
    t, textos = ctx["tecnica"], ctx["textos"]
    if nombre in ("resumen", "antecedentes", "postor", "estrategia"):
        _parrafos(doc, textos.get(nombre))
    elif nombre == "comprension":
        _parrafos(doc, textos.get("comprension"))
        if t.aspectos_tdr:
            _tabla(doc, ["Aspecto del TdR", "Cómo lo atenderemos"],
                   [(a.aspecto, a.lectura) for a in t.aspectos_tdr], anchos=[4.5, 11.5])
    elif nombre == "objetivos":
        _titulo(doc, "Objetivo general", nivel)
        par = doc.add_paragraph(t.objetivo_general)
        par.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _titulo(doc, "Objetivos específicos", nivel)
        for o in t.objetivos_especificos:
            par = doc.add_paragraph()
            par.add_run(f"{o.codigo}. ").bold = True
            par.add_run(o.texto)
    elif nombre == "metodologia":
        if t.principios:
            doc.add_paragraph().add_run("Principios de trabajo").bold = True
            _vinetas(doc, t.principios)
        _tabla(doc, ["Momento", "Contenido técnico", "Producto principal"],
               [(f"{i}. {m.nombre}", m.contenido_tecnico, m.productos) for i, m in enumerate(t.momentos, 1)],
               anchos=[3.5, 6.5, 6])
    elif nombre == "monitoreo":
        _parrafos(doc, textos.get("monitoreo"))
        if t.palabras_clave_monitoreo:
            par = doc.add_paragraph()
            par.add_run("Palabras clave: ").bold = True
            par.add_run(" · ".join(t.palabras_clave_monitoreo))
    elif nombre == "componentes":
        objetivos = {o.codigo: o.texto for o in t.objetivos_especificos}
        for c in t.componentes:
            _titulo(doc, f"{c.codigo}. {c.nombre}", nivel)
            if c.objetivo in objetivos:
                par = doc.add_paragraph()
                par.add_run(f"Responde a {c.objetivo}: ").italic = True
                par.add_run(objetivos[c.objetivo]).italic = True
            _tabla(doc, ["Líneas de acción", "Actividades principales", "Resultados esperados"],
                   [(c.lineas_accion, c.actividades, c.resultados)], anchos=[4.5, 6.5, 5])
    elif nombre == "entregables":
        _tabla(doc, ["Código", "Entregable", "Plazo máximo", "Contenido principal"],
               [(e.codigo, e.nombre, e.plazo, e.contenido) for e in t.entregables], anchos=[1.6, 4.4, 2.6, 7.4])
    elif nombre == "cronograma":
        _tabla(doc, ["Actividad", "Periodo", "Resultado esperado"],
               [(f.actividad, f.periodo, f.resultado) for f in t.cronograma], anchos=[6, 3, 7])
    elif nombre == "equipo":
        if t.resumen_equipo:
            par = doc.add_paragraph(t.resumen_equipo)
            par.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _tabla(doc, ["Rol", "Perfil", "Dedicación", "Responsabilidades principales"],
               [(f"{r.rol} — {r.nombre}" if r.nombre else r.rol, r.perfil, r.dedicacion, r.responsabilidades)
                for r in t.equipo], anchos=[3, 5, 2.4, 5.6])
    elif nombre == "riesgos":
        _parrafos(doc, textos.get("riesgos"))
        if t.criterios_calidad:
            doc.add_paragraph().add_run("Criterios de calidad").bold = True
            _vinetas(doc, t.criterios_calidad)
        _tabla(doc, ["Riesgo identificado", "Posible efecto", "Medida de mitigación"],
               [(r.riesgo, r.efecto, r.mitigacion) for r in t.riesgos], anchos=[5, 5, 6])
    elif nombre == "salvaguardas":
        _tabla(doc, ["Salvaguarda", "Medidas"], [(s.tipo, s.medidas) for s in t.salvaguardas], anchos=[3.5, 12.5])
        _parrafos(doc, textos.get("salvaguardas"))
    elif nombre == "matriz":
        _matriz_word(doc, ctx["matriz"])


TITULOS_BLOQUE = {
    "resumen": "Resumen ejecutivo", "antecedentes": "Antecedentes", "comprension": "Comprensión del servicio",
    "postor": "Experiencia del postor", "objetivos": "Objetivos de la propuesta",
    "metodologia": "Enfoque metodológico y principios", "estrategia": "Estrategia metodológica general",
    "monitoreo": "Monitoreo y evaluación", "componentes": "Plan de trabajo por componentes",
    "entregables": "Entregables y productos verificables", "cronograma": "Cronograma general",
    "equipo": "Equipo técnico", "riesgos": "Monitoreo de la calidad y gestión de riesgos",
    "salvaguardas": "Salvaguardas", "matriz": "Matriz de indicadores",
}

# Estructura mínima cuando el TdR no fija un formato: (título, [(subtítulo o None, bloque), ...]).
ESTRUCTURA_BASE = [
    ("Resumen ejecutivo", [(None, "resumen")]),
    ("Antecedentes y comprensión del servicio", [("Antecedentes", "antecedentes"),
                                                 ("Comprensión del servicio", "comprension"),
                                                 ("Experiencia del postor", "postor")]),
    ("Objetivos de la propuesta", [(None, "objetivos")]),
    ("Enfoque metodológico y principios", [(None, "metodologia")]),
    ("Estrategia metodológica general", [(None, "estrategia"), ("Monitoreo y evaluación", "monitoreo")]),
    ("Plan de trabajo por componentes", [(None, "componentes")]),
    ("Entregables y productos verificables", [(None, "entregables")]),
    ("Cronograma general", [(None, "cronograma")]),
    ("Equipo técnico y roles", [(None, "equipo")]),
    ("Monitoreo de la calidad y gestión de riesgos", [(None, "riesgos")]),
    ("Salvaguardas", [(None, "salvaguardas")]),
]


def a_word(propuesta, formato, convocatoria="", resumen=None) -> bytes:
    """Propuesta técnica en Word: sigue el índice del TdR si lo hay; si no, la estructura base."""
    if propuesta.get("tecnica") is None:
        return _a_word_anterior(propuesta, formato, convocatoria, resumen)

    doc = Document()
    estilo = doc.styles["Normal"]
    estilo.font.name = "Arial"
    estilo.font.size = Pt(formato["estilo"]["tamano"])
    seccion = doc.sections[0]
    seccion.left_margin = seccion.right_margin = Cm(2.5)
    seccion.top_margin = seccion.bottom_margin = Cm(2.2)

    tecnica = propuesta["tecnica"]
    ctx = {"tecnica": tecnica, "textos": {s.seccion_id: s for s in propuesta["textos"].secciones},
           "matriz": propuesta["matriz"]}
    _pie_de_pagina(doc, f"Propuesta técnica — {tecnica.datos.nombre_servicio[:70]}")
    _portada(doc, tecnica, convocatoria)

    usados = set()
    if tecnica.estructura_tdr:
        for n, sec in enumerate(tecnica.estructura_tdr, 1):
            _titulo(doc, sec.titulo if re.match(r"^\d", sec.titulo) else f"{n}. {sec.titulo}", 1)
            bloques = [b for b in sec.bloques if b in TITULOS_BLOQUE and b not in usados]
            for b in bloques:
                if len(bloques) > 1:
                    _titulo(doc, TITULOS_BLOQUE[b], 2)
                _bloque(doc, b, ctx, 3 if len(bloques) > 1 else 2)
                usados.add(b)
            if not bloques:
                doc.add_paragraph(f"[POR COMPLETAR: {sec.nota or 'contenido que pide el TdR para esta sección'}]")
    else:
        for n, (titulo, partes) in enumerate(ESTRUCTURA_BASE, 1):
            _titulo(doc, f"{n}. {titulo}", 1)
            for m, (subtitulo, b) in enumerate(partes, 1):
                if subtitulo:
                    _titulo(doc, f"{n}.{m}. {subtitulo}", 2)
                _bloque(doc, b, ctx, 3 if subtitulo else 2)
                usados.add(b)

    if "matriz" not in usados:
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        _titulo(doc, "Anexo. Matriz de indicadores", 1)
        _matriz_word(doc, propuesta["matriz"])

    if propuesta.get("referencias"):
        _titulo(doc, "Anexo. Proyectos de referencia", 1)
        _referencias_word(doc, propuesta["referencias"])

    pendientes = list(tecnica.pendientes) + [p for s in propuesta["textos"].secciones for p in s.pendientes]
    if pendientes:
        _titulo(doc, "Pendientes por completar (borrar antes de presentar)", 1)
        _vinetas(doc, dict.fromkeys(pendientes))

    salida = io.BytesIO()
    doc.save(salida)
    return salida.getvalue()


FINANCIADORES = {"BID": "BID", "BMZ": "Cooperación alemana (BMZ)"}


def _hipervinculo(parrafo, url, texto, tamano=9):
    """Enlace clicable en Word (python-docx no trae uno propio)."""
    rel = parrafo.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
                                 is_external=True)
    enlace = OxmlElement("w:hyperlink")
    enlace.set(qn("r:id"), rel)
    run = OxmlElement("w:r")
    props = OxmlElement("w:rPr")
    for etiqueta, valor in (("w:color", "0563C1"), ("w:u", "single"), ("w:sz", str(tamano * 2))):
        el = OxmlElement(etiqueta)
        el.set(qn("w:val"), valor)
        props.append(el)
    run.append(props)
    texto_el = OxmlElement("w:t")
    texto_el.text = texto
    run.append(texto_el)
    enlace.append(run)
    parrafo._p.append(enlace)


def _referencias_word(doc, referencias):
    """Tabla de los proyectos financiados por la cooperación que sirvieron de base al diseño."""
    from ai.referencias import anio, monto

    intro = doc.add_paragraph("El diseño toma como referencia proyectos similares financiados por la cooperación "
                              "internacional en el Perú, según los datos abiertos del BID y del BMZ.")
    intro.paragraph_format.keep_with_next = True
    filas = [[f"{r['nombre']} ({r['codigo']})",
              f"{FINANCIADORES.get(r['fuente'], r['fuente'])}, {anio(r)}" + (f". Ejecutor: {r['ejecutor']}"
                                                                           if r.get("ejecutor") else ""),
              monto(r), r.get("aporte", "")] for r in referencias]
    tabla = _tabla(doc, ["Proyecto", "Financiador y año", "Monto", "Qué se tomó para esta propuesta"], filas,
                   anchos=[5.5, 3.5, 2.5, 4.5])
    for celda in tabla.rows[0].cells:  # que el encabezado no quede solo al pie de una página
        for par in celda.paragraphs:
            par.paragraph_format.keep_with_next = True
    for fila, r in zip(tabla.rows[1:], referencias):
        if r.get("enlace"):
            _hipervinculo(fila.cells[0].add_paragraph(), r["enlace"], "Ver ficha del proyecto")


def _matriz_word(doc, matriz):
    """Matriz de indicadores: cada objetivo en una fila de ancho completo y sus indicadores debajo."""
    encabezados = ["Código", "Indicador", "Línea de base", "Meta", "Medio de verificación"]
    anchos = [1.8, 5.2, 2.8, 3.2, 3.0]
    tabla = _tabla(doc, encabezados, [], anchos=anchos)

    def objetivo(etiqueta, texto):
        celdas = tabla.add_row().cells
        unida = celdas[0].merge(celdas[-1])
        unida.text = ""
        par = unida.paragraphs[0]
        r = par.add_run(f"{etiqueta}: ")
        r.bold, r.font.size = True, Pt(9.5)
        par.add_run(texto).font.size = Pt(9.5)
        _sombrear(unida, VERDE_CLARO)

    def indicadores(lista):
        for i in lista:
            celdas = tabla.add_row().cells
            for celda, valor, ancho in zip(celdas, (i.codigo, i.indicador, i.linea_base, i.meta,
                                                    i.medio_verificacion), anchos):
                _celda(celda, valor)
                celda.width = Cm(ancho)

    if matriz.objetivo_superior:
        objetivo("Objetivo superior", matriz.objetivo_superior)
    objetivo("Objetivo general", matriz.objetivo_proyecto)
    indicadores(matriz.indicadores_proyecto)
    for oe in matriz.objetivos_especificos:
        objetivo(oe.codigo, oe.texto)
        indicadores(oe.indicadores)


# ================================================================ Word: formato anterior (propuestas viejas)
def _a_word_anterior(propuesta, formato, convocatoria="", resumen=None) -> bytes:
    doc = Document()
    estilo = doc.styles["Normal"]
    estilo.font.name = "Arial"
    estilo.font.size = Pt(formato["estilo"]["tamano"])

    textos, matriz = propuesta["textos"], propuesta["matriz"]
    doc.add_heading(textos.titulo_proyecto, level=0)
    p = doc.add_paragraph()
    p.add_run("BORRADOR — ").bold = True
    p.add_run(f"versión del {date.today():%d/%m/%Y}. Revise, complete y valide cada sección antes de postular.")
    if convocatoria:
        doc.add_paragraph(f"Convocatoria: {convocatoria}")

    titulos = {s["id"]: s["titulo"] for s in formato["secciones"]}
    orden = [s["id"] for s in formato["secciones"]]
    secciones = sorted(textos.secciones, key=lambda s: orden.index(s.seccion_id) if s.seccion_id in orden else 99)
    pendientes = []

    for seccion in secciones:
        if seccion.seccion_id == "actividades":
            _titulo(doc, titulos.get("matriz", "Matriz de impacto"), 1)
            _matriz_word(doc, matriz)
        _titulo(doc, titulos.get(seccion.seccion_id, seccion.seccion_id), 1)
        _parrafos(doc, seccion)
        pendientes += seccion.pendientes
        if seccion.seccion_id == "actividades":
            _cronograma_anterior(doc, matriz, propuesta["presupuesto"].duracion_meses)

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
        _vinetas(doc, dict.fromkeys(pendientes))

    salida = io.BytesIO()
    doc.save(salida)
    return salida.getvalue()


def _cronograma_anterior(doc, matriz, meses):
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


# ================================================================ Excel: propuesta económica
_FINO = Side(style="thin", color="C9D3D0")
_BORDE = Border(left=_FINO, right=_FINO, top=_FINO, bottom=_FINO)
_NUM = "#,##0.00"


def _estilo(celda, negrita=False, relleno=None, color="1F2933", tamano=10, formato=None, ajustar=False,
            horizontal=None):
    celda.font = Font(name="Arial", bold=negrita, color=color, size=tamano)
    if relleno:
        celda.fill = PatternFill("solid", fgColor=relleno)
    if formato:
        celda.number_format = formato
    celda.alignment = Alignment(wrap_text=ajustar, vertical="center", horizontal=horizontal)
    celda.border = _BORDE


def _banda(hoja, fila, texto, columnas, relleno=VERDE, color="FFFFFF", tamano=12):
    hoja.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=columnas)
    celda = hoja.cell(row=fila, column=1, value=texto)
    _estilo(celda, negrita=True, relleno=relleno, color=color, tamano=tamano, ajustar=True)
    for c in range(2, columnas + 1):
        hoja.cell(row=fila, column=c).fill = PatternFill("solid", fgColor=relleno)
    hoja.row_dimensions[fila].height = 22 if tamano >= 12 else 18


def a_excel(propuesta, resumen, reglas) -> bytes:
    """Propuesta económica con dos hojas: Resumen (por objetivo y por rubro) y Detalle (líneas por objetivo).

    Todo se calcula con fórmulas: si el usuario cambia cantidades o costos, los totales se actualizan.
    """
    libro = Workbook()
    hoja_res = libro.active
    hoja_res.title = "Resumen"
    hoja = libro.create_sheet("Detalle")
    moneda = resumen["moneda"]
    categorias = reglas.get("categorias", {})
    titulo = (propuesta.get("tecnica").datos.nombre_servicio if propuesta.get("tecnica")
              else propuesta["textos"].titulo_proyecto)
    nombres_oe = {oe.codigo: oe.texto for oe in propuesta["matriz"].objetivos_especificos}

    # ---------- Detalle: líneas agrupadas por objetivo, con subtotales
    # Se escribe celda por celda con un contador de filas explícito (hoja.append no cuenta las filas vacías).
    columnas = 7
    _banda(hoja, 1, "PROPUESTA ECONÓMICA — DETALLE DE GASTOS", columnas, tamano=13)
    _banda(hoja, 2, titulo, columnas, relleno=VERDE_CLARO, color="1F2933", tamano=10)
    encabezados = ["N°", "Rubro", "Descripción", "Unidad", "Cantidad", f"Costo unitario ({moneda})",
                   f"Total ({moneda})"]
    for c, texto in enumerate(encabezados, 1):
        _estilo(hoja.cell(row=4, column=c, value=texto), negrita=True, relleno=VERDE, color="FFFFFF", ajustar=True,
                horizontal="center")
    hoja.row_dimensions[4].height = 30

    def escribir(fila, valores, **estilo):
        for c, valor in enumerate(valores, 1):
            celda = hoja.cell(row=fila, column=c, value=valor if valor != "" else None)
            _estilo(celda, **{k: (v(c) if callable(v) else v) for k, v in estilo.items()})

    grupos = {}
    for l in resumen["lineas"]:
        grupos.setdefault(l["objetivo"] or "GEN", []).append(l)
    orden = [c for c in nombres_oe if c in grupos] + sorted(c for c in grupos if c not in nombres_oe and c != "GEN")
    orden += ["GEN"] if "GEN" in grupos else []

    fila, numero, subtotales, filas_lineas = 4, 0, {}, []
    for codigo in orden:
        fila += 1
        nombre = nombres_oe.get(codigo, "Gastos transversales (gestión, personal, monitoreo)" if codigo == "GEN"
                                else codigo)
        _banda(hoja, fila, f"{codigo} · {nombre}" if codigo != "GEN" else nombre, columnas, relleno=VERDE_CLARO,
               color="0F6B5C", tamano=10)
        inicio = fila + 1
        for l in grupos[codigo]:
            fila += 1
            numero += 1
            escribir(fila, [numero, categorias.get(l["categoria"], l["categoria"]), l["descripcion"], l["unidad"],
                            l["cantidad"], l["costo_unitario"], f"=E{fila}*F{fila}"],
                     ajustar=lambda c: c in (2, 3),
                     formato=lambda c: _NUM if c in (6, 7) else ("General" if c == 5 else None),
                     horizontal=lambda c: "center" if c in (1, 4) else None)
            filas_lineas.append(fila)
        fila += 1
        escribir(fila, ["", "", f"Subtotal {codigo}", "", "", "", f"=SUM(G{inicio}:G{fila - 1})"],
                 negrita=True, relleno=GRIS, formato=lambda c: _NUM if c == 7 else None)
        subtotales[codigo] = fila
        fila += 1                                   # fila en blanco entre grupos

    def fila_total(etiqueta, formula, relleno=GRIS, color="1F2933", formato=_NUM):
        nonlocal fila
        fila += 1
        escribir(fila, ["", "", etiqueta, "", "", "", formula], negrita=True, relleno=relleno, color=color,
                 formato=lambda c: formato if c == 7 else None)
        return fila

    suma_sub = "+".join(f"G{f}" for f in subtotales.values()) or "0"
    f_gastos = fila_total("SUBTOTAL GASTOS DIRECTOS", f"={suma_sub}")
    reserva_pct = reglas["reserva_pct"] if resumen["reserva"] > 0 else 0
    f_reserva = fila_total(f"Reserva / imprevistos ({reserva_pct:.1%})", f"=G{f_gastos}*{reserva_pct}")
    f_admin = fila_total(f"Gastos administrativos ({reglas['admin_pct']:.1%})",
                         f"=(G{f_gastos}+G{f_reserva})*{reglas['admin_pct']}")
    f_total = fila_total("COSTO TOTAL DEL PROYECTO", f"=G{f_gastos}+G{f_reserva}+G{f_admin}", relleno=VERDE,
                         color="FFFFFF")
    fila += 2
    _banda(hoja, fila, "Aportes propios y de terceros (contrapartida)", columnas, relleno=VERDE_CLARO,
           color="0F6B5C", tamano=10)
    ini_ap = fila + 1
    for a in propuesta["presupuesto"].aportes_propios:
        fila += 1
        escribir(fila, ["", a.tipo.capitalize(), a.fuente, "", "", "",
                        round(a.monto * resumen.get("tasa_conversion", 1.0), 2)],
                 formato=lambda c: _NUM if c == 7 else None, ajustar=lambda c: c == 3)
    fin_ap = fila
    f_aporte = fila_total("TOTAL APORTE PROPIO", f"=SUM(G{ini_ap}:G{fin_ap})" if fin_ap >= ini_ap else "=0")
    f_sol = fila_total("MONTO SOLICITADO AL DONANTE", f"=G{f_total}-G{f_aporte}", relleno=VERDE, color="FFFFFF")
    fila_total("% de aporte propio", f"=IF(G{f_total}=0,0,G{f_aporte}/G{f_total})", formato="0.0%")
    primera_linea = filas_lineas[0] if filas_lineas else 5
    ultima_linea = filas_lineas[-1] if filas_lineas else 5

    for i, ancho in enumerate([6, 22, 46, 12, 11, 16, 17], start=1):
        hoja.column_dimensions[get_column_letter(i)].width = ancho
    hoja.freeze_panes = "A5"
    hoja.page_setup.orientation = "landscape"
    hoja.page_setup.fitToWidth, hoja.page_setup.fitToHeight = 1, 0
    hoja.sheet_properties.pageSetUpPr.fitToPage = True
    hoja.print_title_rows = "4:4"

    # ---------- Resumen: por objetivo y por rubro, con referencias al detalle
    r = hoja_res
    _banda(r, 1, "PROPUESTA ECONÓMICA", 4, tamano=14)
    _banda(r, 2, titulo, 4, relleno=VERDE_CLARO, color="1F2933", tamano=10)
    datos = [("Moneda", moneda), ("Duración", f"{resumen['duracion_meses']} meses"),
             ("Reglas aplicadas", reglas["origen"]), ("Fecha", f"{date.today():%d/%m/%Y}")]
    if propuesta.get("tecnica"):
        d = propuesta["tecnica"].datos
        datos = [("Presentado a", d.presentado_a), ("Postor", d.postor)] + datos
    fila = 4
    for campo, valor in datos:
        _estilo(r.cell(row=fila, column=1, value=campo), negrita=True, relleno=GRIS)
        r.merge_cells(start_row=fila, start_column=2, end_row=fila, end_column=4)
        _estilo(r.cell(row=fila, column=2, value=valor), ajustar=True)
        fila += 1

    def encabezado(fila, textos):
        for c, texto in enumerate(textos, 1):
            _estilo(r.cell(row=fila, column=c, value=texto), negrita=True, relleno=VERDE, color="FFFFFF",
                    horizontal="center", ajustar=True)

    fila += 1
    _banda(r, fila, "1. Resumen por objetivo", 4, relleno=VERDE_CLARO, color="0F6B5C", tamano=11)
    fila += 1
    encabezado(fila, ["Código", "Objetivo / concepto", f"Monto ({moneda})", "% del total"])
    total_ref = f"Detalle!G{f_total}"
    filas_obj = []
    for codigo, fila_sub in subtotales.items():
        fila += 1
        nombre = nombres_oe.get(codigo, "Gastos transversales" if codigo == "GEN" else codigo)
        valores = [codigo, nombre, f"=Detalle!G{fila_sub}", f"=IF({total_ref}=0,0,C{fila}/{total_ref})"]
        for c, v in enumerate(valores, 1):
            _estilo(r.cell(row=fila, column=c, value=v), ajustar=c == 2,
                    formato=_NUM if c == 3 else ("0.0%" if c == 4 else None))
        filas_obj.append(fila)
    for etiqueta, ref, relleno, color in (("Subtotal gastos directos", f_gastos, GRIS, "1F2933"),
                                         ("Reserva / imprevistos", f_reserva, None, "1F2933"),
                                         ("Gastos administrativos", f_admin, None, "1F2933"),
                                         ("COSTO TOTAL DEL PROYECTO", f_total, VERDE, "FFFFFF"),
                                         ("Aporte propio y de terceros", f_aporte, GRIS, "1F2933"),
                                         ("MONTO SOLICITADO AL DONANTE", f_sol, VERDE, "FFFFFF")):
        fila += 1
        valores = ["", etiqueta, f"=Detalle!G{ref}", f"=IF({total_ref}=0,0,C{fila}/{total_ref})"]
        for c, v in enumerate(valores, 1):
            _estilo(r.cell(row=fila, column=c, value=v), negrita=True, relleno=relleno, color=color,
                    formato=_NUM if c == 3 else ("0.0%" if c == 4 else None))

    fila += 2
    _banda(r, fila, "2. Resumen por rubro de gasto", 4, relleno=VERDE_CLARO, color="0F6B5C", tamano=11)
    fila += 1
    encabezado(fila, ["", "Rubro", f"Monto ({moneda})", "% de gastos directos"])
    rango_rubro = f"Detalle!B{primera_linea}:B{ultima_linea}"
    rango_total = f"Detalle!G{primera_linea}:G{ultima_linea}"
    usadas = list(dict.fromkeys(categorias.get(l["categoria"], l["categoria"]) for l in resumen["lineas"]))
    for nombre in usadas:
        fila += 1
        valores = ["", nombre, f'=SUMIF({rango_rubro},"{nombre}",{rango_total})',
                   f"=IF(Detalle!G{f_gastos}=0,0,C{fila}/Detalle!G{f_gastos})"]
        for c, v in enumerate(valores, 1):
            _estilo(r.cell(row=fila, column=c, value=v), formato=_NUM if c == 3 else ("0.0%" if c == 4 else None))
    fila += 2
    nota = r.cell(row=fila, column=1, value="Los montos se calculan con fórmulas desde la hoja «Detalle»: cambie "
                                              "cantidades o costos allí y este resumen se actualiza.")
    nota.font = Font(name="Arial", italic=True, size=8, color="666666")
    r.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=4)

    for i, ancho in enumerate([18, 52, 18, 14], start=1):
        r.column_dimensions[get_column_letter(i)].width = ancho
    r.page_setup.fitToWidth, r.page_setup.fitToHeight = 1, 0
    r.sheet_properties.pageSetUpPr.fitToPage = True

    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()
