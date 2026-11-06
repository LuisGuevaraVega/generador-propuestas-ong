from ai.esquemas import ReglasConvocatoria, TopeRubro
from ai.reglas import ALERTA, ERROR, OK, calcular_presupuesto, reglas_efectivas, validar_matriz


def _niveles(chequeos):
    return [n for n, _ in chequeos]


def _tdr(**cambios):
    datos = dict(donante="Donante X", nombre_convocatoria="Fondo", objetivo="Empleo", temas=[], quien_puede_postular="ONG",
                 moneda="EUR", monto_min=None, monto_max=None, duracion_max_meses=None, contrapartida_min_pct=None,
                 administrativos_max_pct=None, imprevistos_pct=None, personal_max_pct=None, gastos_no_elegibles=[],
                 topes_por_rubro=[], secciones_requeridas=[], criterios_evaluacion=[], otras_reglas=[])
    datos.update(cambios)
    return ReglasConvocatoria(**datos)


def test_formato_base_calcula_reserva_administrativos_y_detecta_falta_de_aporte(formato, presupuesto_bmz):
    resumen, chequeos = calcular_presupuesto(presupuesto_bmz, reglas_efectivas(formato))
    assert resumen["gastos"] == 114600
    assert resumen["reserva"] == round(114600 * 0.035, 2)               # 18 meses: sí hay reserva
    assert resumen["administrativos"] == round((114600 + 4011) * 0.12, 2)
    assert resumen["total"] == round(114600 + 4011 + 14233.32, 2)
    mensajes = [m for n, m in chequeos if n == ERROR]
    assert any("Aporte propio de 24.1%" in m and "el mínimo es 25%" in m for m in mensajes)


def test_sin_reserva_si_el_proyecto_dura_un_año(formato, presupuesto_bmz):
    presupuesto_bmz.duracion_meses = 12
    resumen, chequeos = calcular_presupuesto(presupuesto_bmz, reglas_efectivas(formato))
    assert resumen["reserva"] == 0
    assert ALERTA in _niveles(chequeos)


def test_reglas_del_tdr_reemplazan_al_formato_base(formato, presupuesto_bmz):
    reglas = reglas_efectivas(formato, _tdr(monto_max=50000, duracion_max_meses=12, personal_max_pct=0.25))
    resumen, chequeos = calcular_presupuesto(presupuesto_bmz, reglas)
    assert resumen["administrativos"] == 0 and resumen["reserva"] == 0   # el TdR no los permite
    textos = " ".join(m for _, m in chequeos)
    assert "máximo es € 50,000" in textos
    assert "dura 18 meses y el máximo es 12" in textos
    assert "Personal:" in textos


def test_convierte_moneda_con_el_conversor(formato, presupuesto_bmz):
    reglas = reglas_efectivas(formato, _tdr(moneda="AUD"))
    resumen, chequeos = calcular_presupuesto(presupuesto_bmz, reglas, conversor=lambda de, a: 1.6)
    assert resumen["gastos"] == round(114600 * 1.6, 2)
    assert resumen["aporte_propio"] == 32000 * 1.6
    assert any("se convirtieron a AUD" in m for _, m in chequeos)


def test_sin_conversor_la_moneda_distinta_es_error(formato, presupuesto_bmz):
    reglas = reglas_efectivas(formato, _tdr(moneda="AUD"))
    _, chequeos = calcular_presupuesto(presupuesto_bmz, reglas)
    assert any(n == ERROR and "convierte el presupuesto" in m for n, m in chequeos)


def test_matriz_detecta_metas_de_actividad_y_lineas_de_base_en_cero(formato, matriz):
    chequeos = validar_matriz(matriz, reglas_efectivas(formato), monto_solicitado=90000)
    textos = " ".join(m for _, m in chequeos)
    assert "OE2.1: la meta mide una actividad" in textos
    assert "OE2.1: la línea de base está vacía o en cero" in textos
    assert "OE1.1: la meta mide" not in textos


def test_objetivo_superior_obligatorio_sobre_100_mil_euros(formato, matriz):
    chequeos = validar_matriz(matriz, reglas_efectivas(formato), monto_solicitado=120000)
    assert any("objetivo superior es obligatorio" in m for _, m in chequeos)
    chequeos = validar_matriz(matriz, reglas_efectivas(formato), monto_solicitado=80000)
    assert not any("objetivo superior" in m for _, m in chequeos)


def test_tope_por_rubro_se_lee_en_el_esquema():
    tdr = _tdr(topes_por_rubro=[TopeRubro(rubro="capacitación", max_pct=0.3, base="solicitado")])
    assert tdr.topes_por_rubro[0].max_pct == 0.3
    assert OK == "ok"
