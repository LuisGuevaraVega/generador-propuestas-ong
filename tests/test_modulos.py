"""Pruebas de verificador, auditor, documentos, exportación, historial, tipo de cambio y voz (sin APIs)."""
import io
import wave

import pytest
from docx import Document
from openpyxl import load_workbook

from ai import historial, tipo_cambio, voz
from ai.auditor import _pertenece, chequeos_auditoria, puntaje_total
from ai.documentos import Recuperador, _url_descarga, leer_documento, trocear
from ai.esquemas import AuditoriaPresupuesto, Evaluacion, PuntajeCriterio, RevisionLinea, TopeRubro
from ai.exportar import a_excel, a_word
from ai.reglas import calcular_presupuesto, reglas_efectivas
from ai.verificador import numeros_en, verificar

from tests.test_reglas import _tdr


# ---------- verificador de cifras
def test_numeros_en_reconoce_miles_decimales_y_proporciones():
    valores = numeros_en("1,100 jóvenes; 6 de cada 10; seis de cada diez; 3,5 mil; OE1 y A1.2")
    assert {1100.0, 60.0, 3.5} <= valores
    assert 1.0 not in valores and 1.2 not in valores  # códigos OE1 / A1.2 no cuentan


def test_verificador_marca_cifras_sin_fuente(formato, propuesta):
    resumen, _ = calcular_presupuesto(propuesta["presupuesto"], reglas_efectivas(formato))
    cifras = [h["cifra"] for h in verificar(propuesta, resumen)]
    assert "75%" in cifras            # inventado: la fuente dice 60% mujeres
    assert "60%" not in cifras        # respaldado por "6 de cada 10"
    assert "120" not in cifras        # respaldado por la respuesta gm_1
    assert "65%" in cifras            # meta de la matriz sin fuente


# ---------- auditor
def test_pertenece_tolera_tildes_y_partes_del_rubro():
    rubro = "capacitación, consultorías, alimentación, viajes y viáticos"
    assert _pertenece(["Consultorias"], "R1", rubro)
    assert _pertenece(["R1"], "R1", rubro)
    assert not _pertenece(["inversiones"], "R1", rubro)


def test_chequeos_auditoria_suma_topes_y_marca_no_elegibles(formato, presupuesto_bmz):
    tdr = _tdr(gastos_no_elegibles=["viajes internacionales"],
               topes_por_rubro=[TopeRubro(rubro="capacitación", max_pct=0.04, base="total")])
    resumen, _ = calcular_presupuesto(presupuesto_bmz, reglas_efectivas(formato, tdr))
    auditoria = AuditoriaPresupuesto(lineas=[
        RevisionLinea(descripcion="Talleres", elegible=True, motivo="", rubros_tdr=["capacitación"]),
        RevisionLinea(descripcion="Bootcamp", elegible=True, motivo="", rubros_tdr=["R1"]),
        RevisionLinea(descripcion="Viaje del socio", elegible=False, motivo="Viaje internacional", rubros_tdr=[]),
    ])
    chequeos = chequeos_auditoria(auditoria, resumen, tdr)
    textos = " ".join(m for _, m in chequeos)
    assert "Gasto no elegible: «Viaje del socio»" in textos
    pct = (2800 + 2500) / resumen["total"]
    assert f"{pct:.1%}" in textos and any(n == "error" and "Tope" in m for n, m in chequeos)


def test_puntaje_total():
    ev = Evaluacion(criterios=[PuntajeCriterio(criterio="a", puntaje=4, justificacion="", mejora=""),
                               PuntajeCriterio(criterio="b", puntaje=2, justificacion="", mejora="")],
                    fortalezas=[], debilidades=[])
    assert puntaje_total(ev) == 0.75


# ---------- documentos y RAG
def test_trocear_y_recuperar_el_fragmento_correcto():
    texto = "\n".join(["Capital semilla entregado en bienes con plan de negocio."] * 30 +
                      ["La sostenibilidad se asegura con convenios municipales."] * 30)
    fragmentos = trocear("previa.docx", texto)
    assert len(fragmentos) > 2 and fragmentos[0].etiqueta == "DOC:previa.docx#1"
    mejor = Recuperador(fragmentos).buscar("sostenibilidad convenios municipales", k=1)[0]
    assert "sostenibilidad" in mejor.texto.lower()


def test_leer_docx_incluye_tablas():
    doc = Document()
    doc.add_paragraph("Párrafo de prueba")
    tabla = doc.add_table(rows=1, cols=2)
    tabla.rows[0].cells[0].text, tabla.rows[0].cells[1].text = "Rubro", "Monto"
    salida = io.BytesIO()
    doc.save(salida)
    texto = leer_documento("x.docx", salida.getvalue())
    assert "Párrafo de prueba" in texto and "Rubro | Monto" in texto


def _pdf_de_imagen():
    """PDF escaneado de mentira: una página que es solo una imagen, sin texto seleccionable."""
    from PIL import Image, ImageDraw
    imagen = Image.new("RGB", (600, 300), "white")
    ImageDraw.Draw(imagen).text((20, 20), "Ana Perez - Economista", fill="black")
    salida = io.BytesIO()
    imagen.save(salida, format="PDF")
    return salida.getvalue(), imagen


def test_pdf_escaneado_y_fotos_pasan_por_ocr_y_los_pdf_con_texto_no(monkeypatch):
    import ai.llm
    from ai.documentos import MARCA_OCR, es_escaneado
    llamadas = []
    monkeypatch.setattr(ai.llm, "transcribir_documento",
                        lambda contenido, mime: llamadas.append(mime) or "Ana Pérez, economista")
    pdf, imagen = _pdf_de_imagen()
    assert leer_documento("cv.pdf", pdf) == f"{MARCA_OCR}\nAna Pérez, economista"
    foto = io.BytesIO()
    imagen.save(foto, format="PNG")
    assert leer_documento("cv.png", foto.getvalue()).startswith(MARCA_OCR)
    assert llamadas == ["application/pdf", "image/png"]
    assert "escaneado" in leer_documento("cv.pdf", pdf, ocr=False) and len(llamadas) == 2   # sin OCR, solo avisa
    assert not es_escaneado("texto " * 100, 2) and es_escaneado("   ", 1)


def test_enlace_de_google_drive_se_convierte_en_descarga():
    url = _url_descarga("https://drive.google.com/file/d/ABC123/view?usp=sharing")
    assert url == "https://drive.google.com/uc?export=download&id=ABC123"


# ---------- exportación
def test_word_sin_huella_de_autoria_y_excel_con_formulas(formato, propuesta):
    reglas = reglas_efectivas(formato)
    resumen, _ = calcular_presupuesto(propuesta["presupuesto"], reglas)
    texto = leer_documento("p.docx", a_word(propuesta, formato, "Convocatoria X", resumen)).lower()
    assert "emprende joven norte" in texto and "huella" not in texto and "autoría" not in texto
    libro = load_workbook(io.BytesIO(a_excel(propuesta, resumen, reglas)))
    assert libro.sheetnames == ["Resumen", "Detalle"]
    detalle = libro["Detalle"]
    assert "Origen" not in [c.value for c in detalle[4]]
    formulas = [c.value for c in detalle["G"] if isinstance(c.value, str) and c.value.startswith("=E")]
    assert len(formulas) == len(propuesta["presupuesto"].lineas)          # una fórmula por línea de gasto
    agrupado = [c.value for c in detalle["A"] if isinstance(c.value, str)]
    assert any(v.startswith("OE1 · ") for v in agrupado)                  # líneas agrupadas por objetivo
    resumen_hoja = [c.value for c in libro["Resumen"]["C"] if isinstance(c.value, str)]
    assert any(v.startswith("=Detalle!G") for v in resumen_hoja)          # el resumen lee del detalle


def test_word_nuevo_sigue_la_estructura_base_y_no_lleva_montos(formato, propuesta, tecnica):
    propuesta = {**propuesta, "tecnica": tecnica}
    reglas = reglas_efectivas(formato)
    resumen, _ = calcular_presupuesto(propuesta["presupuesto"], reglas)
    doc = Document(io.BytesIO(a_word(propuesta, formato, "Convocatoria X", resumen)))
    titulos = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading 1")]
    assert titulos[:3] == ["1. Resumen ejecutivo", "2. Antecedentes y comprensión del servicio",
                           "3. Objetivos de la propuesta"]
    assert "7. Entregables y productos verificables" in titulos and "11. Salvaguardas" in titulos
    texto = leer_documento("p.docx", a_word(propuesta, formato, "Convocatoria X", resumen))
    assert "PROPUESTA TÉCNICA" in texto and "Presentado a" in texto and "E1 | Plan de trabajo" in texto
    assert "€" not in texto and "Monto solicitado" not in texto           # la técnica no lleva precios


def _informe_largo(paginas_relleno=40):
    """Informe largo de mentira: portada, mucho relleno y, al final, los resultados que importan."""
    relleno = "\n".join(f"Anexo {i}: listado de asistencia y fotografías del taller número {i}."
                        for i in range(paginas_relleno * 30))
    final = ("Resultados del proyecto: 85 mujeres instalaron biohuertos y 62% aumentó sus ingresos.\n"
             "Lecciones aprendidas: el acompañamiento quincenal redujo la deserción.")
    return "INFORME FINAL Mujeres que Cosechan\n" + relleno + "\n" + final


def test_documentos_de_apoyo_cortos_van_completos_y_los_largos_por_relevancia():
    from ai.generador import MAX_POR_DOCUMENTO, bloque_documentos_apoyo, preparar_documentos_apoyo
    largo = _informe_largo()
    assert len(largo) > MAX_POR_DOCUMENTO
    bloque, informe = preparar_documentos_apoyo([("cv_ana.pdf", "Ana Pérez, economista, 10 años en DEL."),
                                                 ("vacio.docx", "   "), ("informe.pdf", largo)])
    assert "[DOC:cv_ana.pdf]\nAna Pérez" in bloque and "DOC:vacio.docx" not in bloque
    assert informe[0]["detalle"] == "completo"
    assert "fragmentos relevantes" in informe[1]["detalle"] and informe[1]["usados"] <= MAX_POR_DOCUMENTO
    assert "INFORME FINAL Mujeres que Cosechan" in bloque            # el comienzo siempre va
    assert "62% aumentó sus ingresos" in bloque                       # y los resultados del final también
    assert bloque_documentos_apoyo([]) == ""


def test_documentos_de_apoyo_avisan_cuando_ya_no_entran():
    from ai.generador import MAX_DOCUMENTOS_APOYO, MAX_POR_DOCUMENTO, preparar_documentos_apoyo
    cantidad = MAX_DOCUMENTOS_APOYO // MAX_POR_DOCUMENTO + 2
    _, informe = preparar_documentos_apoyo([(f"informe_{i}.pdf", _informe_largo()) for i in range(cantidad)])
    assert sum(d["usados"] for d in informe) <= MAX_DOCUMENTOS_APOYO
    assert informe[-1]["usados"] == 0 and "no entra" in informe[-1]["detalle"]


def test_propuestas_anteriores_aportan_hasta_40_fragmentos_de_todos_los_temas(formato):
    from ai.generador import MAX_FRAGMENTOS_PREVIOS, fragmentos_previos
    texto = _informe_largo(10)
    recuperador = Recuperador(trocear("previa.docx", texto))
    elegidos = fragmentos_previos(recuperador, formato, "biohuertos")
    assert 0 < len(elegidos) <= MAX_FRAGMENTOS_PREVIOS
    assert len({f.etiqueta for f in elegidos}) == len(elegidos)      # sin repetidos
    assert any("62% aumentó" in f.texto for f in elegidos)


def test_word_fusiona_indice_del_tdr_con_la_estructura_base(formato, propuesta, tecnica):
    from ai.esquemas import SeccionTdR
    tecnica.estructura_tdr = [SeccionTdR(titulo="II. Metodología", bloques=["metodologia", "estrategia"], nota=""),
                              SeccionTdR(titulo="3.1 Plan de trabajo", bloques=["cronograma"], nota=""),
                              SeccionTdR(titulo="Declaración jurada", bloques=[], nota="firma del representante")]
    doc = Document(io.BytesIO(a_word({**propuesta, "tecnica": tecnica}, formato)))
    titulos = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading 1")]
    # lo que pide el TdR, con su título y en su orden, más lo que la base exige y el TdR no cubre
    assert titulos[:4] == ["1. Resumen ejecutivo", "2. Antecedentes y comprensión del servicio",
                           "3. Objetivos de la propuesta", "4. Metodología"]
    assert titulos.index("5. Monitoreo y evaluación") < titulos.index("8. Plan de trabajo")
    i = titulos.index("10. Monitoreo de la calidad y gestión de riesgos")
    assert titulos[i:i + 3] == ["10. Monitoreo de la calidad y gestión de riesgos", "11. Salvaguardas",
                                "12. Declaración jurada"]
    assert any("[POR COMPLETAR: firma del representante]" in p.text for p in doc.paragraphs)


def test_indice_fusionado_sin_tdr_es_la_base_y_no_repite_bloques():
    from ai.esquemas import SeccionTdR
    from ai.exportar import ESTRUCTURA_BASE, indice_fusionado
    assert [t for t, _, _ in indice_fusionado([])] == [t for t, _ in ESTRUCTURA_BASE]
    fusion = indice_fusionado([SeccionTdR(titulo="Resumen", bloques=["resumen", "resumen", "objetivos"], nota="")])
    bloques = [b for _, partes, _ in fusion for _, b in partes]
    assert len(bloques) == len(set(bloques)) == sum(len(p) for _, p in ESTRUCTURA_BASE)


# ---------- historial
def test_historial_guarda_y_abre_igual(tmp_path, propuesta):
    ruta = historial.guardar(propuesta, carpeta=tmp_path)
    abierta = historial.abrir(ruta)
    assert abierta["textos"].titulo_proyecto == "Emprende Joven Norte"
    assert abierta["presupuesto"].lineas[0].costo_unitario == 1100
    historial.guardar(abierta, carpeta=tmp_path)            # re-guardar usa el mismo archivo
    assert len(historial.listar(carpeta=tmp_path)) == 1


# ---------- tipo de cambio (sin internet)
def test_convertir_pasa_por_soles(monkeypatch):
    tasas = {"EUR": 4.0, "AUD": 2.5, "PEN": 1.0}
    monkeypatch.setattr(tipo_cambio, "soles_por", lambda m: {"valor": tasas[m.upper()]})
    assert tipo_cambio.convertir(100, "EUR", "AUD") == pytest.approx(160)
    assert tipo_cambio.convertir(100, "EUR", "EUR") == 100


def test_tipo_cambio_usa_la_ultima_tasa_si_la_api_falla(monkeypatch, tmp_path):
    monkeypatch.setattr(tipo_cambio, "CACHE", tmp_path / "tc.json")
    tipo_cambio._escribir_cache({"USD": {"valor": 3.45, "fecha": "01.Nov.26", "fuente": "BCRP",
                                         "consultado": "2026-11-01T10:00:00"}})

    def falla(*_a, **_k):
        raise ConnectionError("sin internet")
    monkeypatch.setattr(tipo_cambio, "_bcrp", falla)
    dato = tipo_cambio.soles_por("USD")
    assert dato["valor"] == 3.45 and "última tasa guardada" in dato["fuente"]


# ---------- voz
def _wav(muestras: bytes) -> bytes:
    salida = io.BytesIO()
    with wave.open(salida, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(muestras)
    return salida.getvalue()


def test_silencio_no_se_transcribe():
    audio = _wav(b"\x00\x00" * 16000)
    assert voz.analizar_audio(audio)["pico"] == 0
    assert voz.transcribir(audio) == ""          # no llama a Whisper: evita textos inventados


# ---------- ENAHO
def test_enaho_detecta_departamento_y_arma_contexto():
    from ai import enaho
    assert enaho.detectar("Proyecto con jóvenes de Chiclayo") == "14"
    assert enaho.detectar("Trabajamos en San Martín") == "22"
    # Solo palabras completas: "agroecológicas" contiene "ica", pero no es Ica.
    assert enaho.detectar("Biohuertos y ferias agroecológicas con mujeres en Lambayeque") == "14"
    assert enaho.detectar("Proyecto en Huancavelica") == "09"
    assert enaho.detectar("Idea en Piura", "ONG de Chiclayo") == "20"          # manda lo que se menciona primero
    bloque = enaho.contexto("14")
    assert "Lambayeque: pobreza monetaria 14.0%" in bloque and "Perú (nacional)" in bloque
    assert enaho.contexto("") == ""


# ---------- feed de convocatorias
def test_actualizar_feed_acumula_sin_borrar_dias(tmp_path):
    import json as _json
    from scripts.actualizar_feed import main as actualizar
    item = {"title": "T", "donor": "D", "type": "Subvención", "deadline": "", "links": []}
    destino = tmp_path / "reportes.json"
    destino.write_text(_json.dumps({"reports": [{"date": "2026-11-04", "summary": "a", "items": [item]}]}), encoding="utf-8")
    html = tmp_path / "artefacto.html"
    nuevo = {"reports": [{"date": "2026-11-05", "summary": "b", "items": [item]},
                         {"date": "mal", "summary": "x", "items": []}]}
    html.write_text('<p>x</p><script id="report-data" type="application/json">' + _json.dumps(nuevo) + "</script>",
                    encoding="utf-8")
    actualizar([html], destino=destino)
    fechas = [r["date"] for r in _json.loads(destino.read_text(encoding="utf-8"))["reports"]]
    assert fechas == ["2026-11-05", "2026-11-04"]          # agrega el nuevo, conserva el viejo, omite el inválido


# ---------- Fondoempleo
def test_fondoempleo_personal_cuenta_como_equipo_y_aplica_topes(propuesta):
    from ai import fondoempleo as fe
    from ai.fondoempleo import AdaptacionFE, LineaFE
    lineas = [LineaFE(descripcion=l.descripcion, categoria_fe="Servicios profesionales especializados",
                      financiable=l.descripcion != "Viaje del socio", motivo="")
              for l in propuesta["presupuesto"].lineas]
    ad = AdaptacionFE(linea_fondoempleo="capacitacion_laboral", participantes=120, fin="f", proposito="p",
                      situacion_problematica="s", involucrados=[], problema_central="pc", causas=[], efectos=[],
                      objetivo_central="oc", medios=[], fines=[], alternativas=[], alternativa_elegida="a",
                      demanda_competencias="d", oferta_competencias="o", costos_oferta="c", equipo=[], monitoreo="m",
                      riesgos=[], lineas=lineas)
    calc = fe.calcular(propuesta, ad, factor_a_soles=4.0)
    assert calc["administrativos"] == round(calc["directos_fe"] * 0.10, 2)
    assert calc["imprevistos"] == round(calc["directos_fe"] * 0.015, 2)
    textos = " ".join(m for _, m in fe.chequeos(calc, ad))
    assert "Equipo del proyecto:" in textos and "0.0%" not in textos.split("Equipo del proyecto:")[1][:8]
    assert "Duración: 18 meses (máximo 10)" in textos
    assert "No financiable por Fondoempleo: «Viaje del socio»" in textos


# ---------- proyectos similares del BID
CSV_BID = """\ufeffoper_num,oper_nm,apprvl_dt,cntry_cd,publc_sts_nm,sector_nm,subsector_nm,opertyp_nm,objtv,orig_apprvd_useq_amnt,totl_cost_orig,loc_cntrprt
PE-T1,Inclusión financiera de mujeres microempresarias rurales,2020-05-01T00:00,PE,Cerrado,MERCADOS FINANCIEROS,MICROFINANZAS,Cooperación Técnica,Ampliar el crédito y el ahorro de mujeres microempresarias rurales.,500000.0,600000.0,100000.0
PE-L2,Carretera regional,2021-01-01T00:00,PE,Implementación,TRANSPORTE,CARRETERAS,Operación de Préstamo,Mejorar la carretera.,90000000.0,90000000.0,
PE-T3,Empleo juvenil y emprendimiento,NULL,PE,Cancelado,INVERSIONES SOCIALES,EMPLEO,Cooperación Técnica,Promover el empleo juvenil.,300000.0,300000.0,
CO-T4,Microfinanzas en Colombia,2020-01-01T00:00,CO,Cerrado,MERCADOS FINANCIEROS,MICROFINANZAS,Cooperación Técnica,Crédito rural.,100.0,100.0,
PE-T5,Capacitación laboral de jóvenes,2019-03-01T00:00,PE,Cerrado,INVERSIONES SOCIALES,EMPLEO,Cooperación Técnica,Formar a jóvenes en oficios con empleo.,200000.0,200000.0,
"""


XML_BMZ = b"""<iati-activities>
<iati-activity default-currency="EUR"><iati-identifier>DE-1-1</iati-identifier>
 <title><narrative xml:lang="EN">Savings groups for rural women microentrepreneurs</narrative></title>
 <description type="1"><narrative xml:lang="EN">Rural women microentrepreneurs improve credit and savings.</narrative></description>
 <participating-org role="3"><narrative xml:lang="EN">Caritas International e.V.</narrative></participating-org>
 <activity-status code="2"/><activity-date iso-date="2024-03-01" type="2"/>
 <transaction><transaction-type code="2"/><value>250000</value></transaction></iati-activity>
<iati-activity><iati-identifier>DE-1-2</iati-identifier>
 <title><narrative xml:lang="EN">Water supply</narrative></title>
 <participating-org role="3"><narrative xml:lang="EN">KfW Bankengruppe (KfW)</narrative></participating-org>
 <activity-status code="4"/><activity-date iso-date="2015-01-01" type="2"/></iati-activity>
<iati-activity><iati-identifier>DE-1-3</iati-identifier>
 <title><narrative xml:lang="EN">Old project</narrative></title>
 <activity-status code="4"/><activity-date iso-date="2003-01-01" type="2"/></iati-activity>
</iati-activities>"""


def test_bid_filtra_peru_vigente_sin_infraestructura(tmp_path):
    from scripts.actualizar_referencias import filtrar_bid, guardar
    filas = filtrar_bid(CSV_BID)
    assert [f["codigo"] for f in filas] == ["PE-T1", "PE-T5"]  # sin Colombia, carreteras ni cancelados
    assert filas[0]["monto"] == "500000" and filas[0]["aprobacion"] == "2020-05-01" and filas[0]["fuente"] == "BID"
    guardar(filas, tmp_path / "bid.csv")
    assert (tmp_path / "bid.csv").read_text(encoding="utf-8").startswith("fuente,codigo,nombre,")


def test_bmz_filtra_ong_y_reutiliza_traducciones():
    from scripts.actualizar_referencias import filtrar_bmz, traducir
    filas = filtrar_bmz(XML_BMZ)
    assert [f["codigo"] for f in filas] == ["DE-1-1"]  # sin KfW ni proyectos anteriores a 2010
    assert filas[0]["monto"] == "250000" and filas[0]["moneda"] == "EUR" and filas[0]["ejecutor"].startswith("Caritas")
    previas = {"DE-1-1": {"codigo": "DE-1-1", "nombre": "Grupos de ahorro de mujeres rurales", "idioma": "es",
                          "objetivo": "Mujeres rurales microempresarias mejoran su ahorro.", "sector": "Microfinanzas"}}
    traducidas = traducir(filas, previas)  # ya traducido: no llama a la IA
    assert traducidas[0]["nombre"] == "Grupos de ahorro de mujeres rurales" and traducidas[0]["idioma"] == "es"


@pytest.fixture
def tablas_referencia(monkeypatch, tmp_path):
    from ai import referencias
    from scripts.actualizar_referencias import filtrar_bid, filtrar_bmz, guardar, traducir
    guardar(filtrar_bid(CSV_BID), tmp_path / "bid.csv")
    previas = {"DE-1-1": {"codigo": "DE-1-1", "nombre": "Grupos de ahorro de mujeres microempresarias rurales",
                          "idioma": "es", "objetivo": "Crédito y ahorro para mujeres microempresarias rurales.",
                          "sector": "Microfinanzas"}}
    guardar(traducir(filtrar_bmz(XML_BMZ), previas), tmp_path / "bmz.csv")
    monkeypatch.setattr(referencias, "TABLAS", {"BID": tmp_path / "bid.csv", "BMZ": tmp_path / "bmz.csv"})
    referencias._cache.clear()
    yield referencias
    referencias._cache.clear()


def test_referencias_similares_de_ambas_fuentes(tablas_referencia):
    r = tablas_referencia
    encontrados = r.similares("Crédito para mujeres microempresarias en Lambayeque", minimo=0.05)
    assert {p["codigo"] for p in encontrados[:2]} == {"PE-T1", "DE-1-1"}
    assert {p["fuente"] for p in encontrados} == {"BID", "BMZ"}
    assert r.similares("Lambayeque") == []  # el lugar solo no basta para parecerse
    texto = r.contexto(encontrados[:2])
    assert "[PE-T1]" in texto and "US$ 500,000" in texto and "€ 250,000" in texto and "No copies" in texto
    assert r.contexto([]) == ""


def test_referencias_usadas_descarta_codigos_inventados(tablas_referencia):
    from ai.esquemas import ReferenciaUsada
    candidatos = tablas_referencia.similares("microempresarias rurales crédito ahorro", minimo=0.01)
    usadas = tablas_referencia.usadas([ReferenciaUsada(codigo="[PE-T1]", aporte="Componente de ahorro"),
                                       ReferenciaUsada(codigo="PE-X999", aporte="inventado")], candidatos)
    assert [(u["codigo"], u["aporte"]) for u in usadas] == [("PE-T1", "Componente de ahorro")]


def test_word_anexo_de_proyectos_de_referencia(formato, propuesta, tecnica, tablas_referencia):
    candidatos = tablas_referencia.similares("microempresarias rurales crédito ahorro", minimo=0.01)
    propuesta = {**propuesta, "tecnica": tecnica,
                 "referencias": [{**candidatos[0], "aporte": "Enfoque de ahorro grupal"}]}
    doc = Document(io.BytesIO(a_word(propuesta, formato, "Convocatoria X")))
    titulos = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    assert "Anexo. Proyectos de referencia" in titulos
    celdas = [c.text for tabla in doc.tables for fila in tabla.rows for c in fila.cells]
    assert any("Enfoque de ahorro grupal" in c for c in celdas)


# ---------- datos públicos del INEI por tema (skill datos-publicos-propuesta)
PAGINA_ENDES = "\n".join(["Departamento", "Total", "12.2", "12.1", "11.5", "11.7", "11.5", "12.1", "11.5", "12.8", "2.8",
                          "19,511", "-0.1", "Amazonas", "17.9", "17.6", "19.2", "21.7", "19.9", "20.4", "16.4", "24.4",
                          "10.0", "816", "2.5", "Arequipa", "(6,1)", "(6,0)", "(4,9)", "(4,8)", "(4,7)", "(5,6)", "3.7",
                          "7.5", "20.1", "380", "Lima Metropolitana  1/", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-"])


def test_endes_lee_ultimo_anio_y_marca_referenciales():
    import importlib.util
    spec = importlib.util.spec_from_file_location("endes", ".claude/skills/datos-publicos-propuesta/scripts/endes.py")
    endes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(endes)
    valores = endes.leer_cuadro(PAGINA_ENDES)
    assert valores["00"] == (12.1, False) and valores["01"] == (20.4, False)
    assert valores["04"] == (5.6, True)       # entre paréntesis en el informe: referencial
    assert "15" not in valores                # fila sin datos ("-")


def test_contexto_publico_elige_indicadores_por_tema():
    from ai import contexto_publico
    assert contexto_publico.temas("Biohuertos con madres para combatir la anemia infantil")[:3] == [
        "pobreza", "territorio", "nutrición e infancia"]
    assert "educación" not in contexto_publico.temas("Crédito para microempresas")
    texto = contexto_publico.contexto("06", "Programa contra la anemia y la desnutrición infantil")
    assert "Anemia" in texto and "Desnutrición" in texto and "INEI, ENDES 2024" in texto and "(Perú:" in texto
    assert "Desnutrición" not in contexto_publico.contexto("06", "Crédito para microempresas")
    assert contexto_publico.contexto("", "anemia") == ""
