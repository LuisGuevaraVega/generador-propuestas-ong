"""Esquemas de salida estructurada (sesión 08: LLMs con salidas estructuradas).

Cada pieza redactada guarda `fuentes`: los ids de las respuestas de la
organización que la respaldan. Es la "huella de autoría" de la propuesta.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class Parrafo(BaseModel):
    texto: str
    fuentes: List[str] = Field(description="Ids de las respuestas usadas, p. ej. ['pro_1', 'pro_2']")


class SeccionTexto(BaseModel):
    parrafos: List[Parrafo]
    pendientes: List[str] = Field(description="Datos que faltan y que la organización debe completar")


class Indicador(BaseModel):
    codigo: str = Field(description="p. ej. 'OP.1' o 'OE1.1'")
    indicador: str
    linea_base: str
    meta: str
    medio_verificacion: str
    fuentes: List[str]


class Actividad(BaseModel):
    codigo: str = Field(description="p. ej. 'A1.1'")
    descripcion: str
    mes_inicio: int
    mes_fin: int


class ObjetivoEspecifico(BaseModel):
    codigo: str = Field(description="p. ej. 'OE1'")
    texto: str
    indicadores: List[Indicador]
    actividades: List[Actividad]
    fuentes: List[str]


class MatrizImpacto(BaseModel):
    objetivo_superior: Optional[str] = None
    objetivo_proyecto: str
    indicadores_proyecto: List[Indicador]
    objetivos_especificos: List[ObjetivoEspecifico]
    pendientes: List[str]


class LineaPresupuesto(BaseModel):
    objetivo: str = Field(description="Código del objetivo específico (OE1, OE2...) o 'GEN' si es transversal")
    categoria: str = Field(description="inversiones, operativos, personal, viajes o evaluacion")
    descripcion: str
    unidad: str
    cantidad: float
    costo_unitario: float
    fuentes: List[str]


class Aporte(BaseModel):
    fuente: str = Field(description="Quién aporta: organización local, socio, municipalidad, etc.")
    monto: float
    tipo: str = Field(description="monetario o especie")
    fuentes: List[str]


class Presupuesto(BaseModel):
    duracion_meses: int
    lineas: List[LineaPresupuesto]
    aportes_propios: List[Aporte]
    pendientes: List[str]
