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


def test_enlace_de_google_drive_se_convierte_en_descarga():
    url = _url_descarga("https://drive.google.com/file/d/ABC123/view?usp=sharing")
    assert url == "https://drive.google.com/uc?export=download&id=ABC123"


# ---------- exportación
def test_word_sin_huella_de_autoria_y_excel_con_formulas(formato, propuesta):
    reglas = reglas_efectivas(formato)
    resumen, _ = calcular_presupuesto(propuesta["presupuesto"], reglas)
    texto = leer_documento("p.docx", a_word(propuesta, formato, "Convocatoria X", resumen)).lower()
    assert "emprende joven norte" in texto and "huella" not in texto and "autoría" not in texto
    hoja = load_workbook(io.BytesIO(a_excel(propuesta, resumen, reglas))).active
    assert hoja["G5"].value == "=E5*F5"
    assert "Origen" not in [c.value for c in hoja[4]]


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
