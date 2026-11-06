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


def test_word_nuevo_sigue_el_indice_del_tdr(formato, propuesta, tecnica):
    from ai.esquemas import SeccionTdR
    tecnica.estructura_tdr = [SeccionTdR(titulo="Metodología", bloques=["metodologia", "estrategia"], nota=""),
                              SeccionTdR(titulo="Plan de trabajo", bloques=["cronograma"], nota=""),
                              SeccionTdR(titulo="Declaración jurada", bloques=[], nota="firma del representante")]
    doc = Document(io.BytesIO(a_word({**propuesta, "tecnica": tecnica}, formato)))
    titulos = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading 1")]
    assert titulos[:3] == ["1. Metodología", "2. Plan de trabajo", "3. Declaración jurada"]
    assert any("[POR COMPLETAR: firma del representante]" in p.text for p in doc.paragraphs)


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
