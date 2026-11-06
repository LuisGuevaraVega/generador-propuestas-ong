"""Datos de prueba: una propuesta falsa construida a mano, sin llamar a ninguna API."""
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ai.esquemas import (Actividad, Aporte, Indicador, LineaPresupuesto, MatrizImpacto,  # noqa: E402
                         ObjetivoEspecifico, Parrafo, Presupuesto, SeccionGenerada, TextosPropuesta)


@pytest.fixture
def formato():
    return json.loads((RAIZ / "data" / "formatos" / "formato_base.json").read_text(encoding="utf-8"))


def _indicador(codigo, indicador, base, meta, fuentes=("gm_1",)):
    return Indicador(codigo=codigo, indicador=indicador, linea_base=base, meta=meta,
                     medio_verificacion="Encuesta", fuentes=list(fuentes))


@pytest.fixture
def presupuesto_bmz():
    """El caso de ejemplo: 114,600 EUR de gastos y 32,000 de aporte (falta aporte para el 25%)."""
    filas = [("GEN", "personal", "Coordinadora", 18, 1100), ("OE1", "personal", "Especialista", 16, 450),
             ("GEN", "personal", "Asistente", 18, 300), ("OE2", "inversiones", "Capital semilla", 60, 800),
             ("OE1", "operativos", "Talleres", 8, 350), ("OE1", "operativos", "Bootcamp", 1, 2500),
             ("OE2", "operativos", "Mentorías", 360, 25), ("OE3", "operativos", "Ferias", 6, 900),
             ("OE3", "operativos", "Formación de voluntarios", 1, 3000), ("GEN", "operativos", "Movilidad", 18, 150),
             ("GEN", "evaluacion", "Línea de base y evaluación", 1, 6000), ("GEN", "viajes", "Viaje del socio", 1, 2800)]
    lineas = [LineaPresupuesto(objetivo=o, categoria=c, descripcion=d, unidad="u", cantidad=q, costo_unitario=p,
                               fuentes=["pre_2"]) for o, c, d, q, p in filas]
    aportes = [Aporte(fuente="ONG", monto=8000, tipo="monetario", fuentes=["pre_3"]),
               Aporte(fuente="Socio", monto=20000, tipo="monetario", fuentes=["pre_3"]),
               Aporte(fuente="Municipalidad", monto=4000, tipo="especie", fuentes=["pre_3"])]
    return Presupuesto(moneda="EUR", duracion_meses=18, lineas=lineas, aportes_propios=aportes, pendientes=[])


@pytest.fixture
def matriz():
    return MatrizImpacto(
        objetivo_superior=None,
        objetivo_proyecto="Los jóvenes gestionan sus negocios con registros",
        indicadores_proyecto=[_indicador("OP.1", "% de negocios activos al mes 12", "30%", "65%")],
        objetivos_especificos=[
            ObjetivoEspecifico(codigo="OE1", texto="Capacidades de gestión", fuentes=["mat_2"],
                               indicadores=[_indicador("OE1.1", "% que lleva registro de ventas", "15%", "80%")],
                               actividades=[Actividad(codigo="A1.1", descripcion="Talleres", mes_inicio=1, mes_fin=4)]),
            ObjetivoEspecifico(codigo="OE2", texto="Capital semilla", fuentes=["mat_2"],
                               indicadores=[_indicador("OE2.1", "Número de talleres realizados", "0", "8 talleres")],
                               actividades=[Actividad(codigo="A2.1", descripcion="Concurso", mes_inicio=5, mes_fin=6)]),
        ],
        pendientes=[],
    )


@pytest.fixture
def propuesta(matriz, presupuesto_bmz):
    textos = TextosPropuesta(titulo_proyecto="Emprende Joven Norte", secciones=[
        SeccionGenerada(seccion_id="problema", pendientes=[], parrafos=[
            Parrafo(texto="El 60% de los jóvenes trabaja en la informalidad.", fuentes=["pro_2"]),
            Parrafo(texto="Atenderemos a 120 jóvenes, de los cuales 75% serán mujeres.", fuentes=["gm_1", "IA"]),
        ]),
        SeccionGenerada(seccion_id="riesgos", pendientes=["Confirmar convenio"], parrafos=[
            Parrafo(texto="Riesgo de deserción mitigado con horarios flexibles.", fuentes=["rie_1"]),
        ]),
    ])
    contexto = ("[pro_2] 6 de cada 10 trabajaban en la informalidad.\n"
                "[gm_1] 120 jóvenes de 18 a 29 años, al menos 60% mujeres.")
    return {"modo": "entrevista", "moneda": "EUR", "textos": textos, "matriz": matriz,
            "presupuesto": presupuesto_bmz, "contexto": contexto, "reglas_tdr": None, "llamadas": []}
