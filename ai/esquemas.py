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
    moneda: str = Field(description="Código ISO de la moneda en que están TODOS los montos: PEN, EUR, USD, AUD...")
    duracion_meses: int
    lineas: List[LineaPresupuesto]
    aportes_propios: List[Aporte]
    pendientes: List[str]


class SeccionGenerada(BaseModel):
    seccion_id: str = Field(description="Id de la sección del formato: organizacion, problema, grupo_meta, actividades, riesgos")
    parrafos: List[Parrafo]
    pendientes: List[str]


class TextosPropuesta(BaseModel):
    titulo_proyecto: str
    secciones: List[SeccionGenerada]


class TopeRubro(BaseModel):
    rubro: str = Field(description="Rubro tal como lo nombra el TdR, p. ej. 'consultorías y capacitación'")
    max_pct: float = Field(description="Tope como fracción (0.30 = 30%)")
    base: str = Field(description="'total' si el tope es sobre el costo total, 'solicitado' si es sobre el monto pedido")


class ReglasConvocatoria(BaseModel):
    """Lo que el TdR o las bases exigen, extraído por el modelo (Document AI + salida estructurada)."""

    donante: str
    nombre_convocatoria: str
    objetivo: str
    temas: List[str]
    quien_puede_postular: str
    moneda: str = Field(description="Código ISO: PEN, EUR, USD, AUD...")
    monto_min: Optional[float] = Field(None, description="Monto mínimo a solicitar al donante")
    monto_max: Optional[float] = Field(None, description="Monto máximo a solicitar al donante")
    duracion_max_meses: Optional[int] = None
    contrapartida_min_pct: Optional[float] = Field(None, description="Aporte propio mínimo como fracción (0.10 = 10%)")
    administrativos_max_pct: Optional[float] = Field(None, description="Tope de gastos administrativos como fracción")
    imprevistos_pct: Optional[float] = Field(None, description="Reserva o imprevistos como fracción")
    personal_max_pct: Optional[float] = Field(None, description="Tope del personal del proyecto como fracción del monto solicitado")
    gastos_no_elegibles: List[str]
    topes_por_rubro: List[TopeRubro] = Field(default_factory=list)
    secciones_requeridas: List[str]
    criterios_evaluacion: List[str]
    fecha_cierre: Optional[str] = None
    otras_reglas: List[str]


class RevisionLinea(BaseModel):
    descripcion: str = Field(description="Descripción exacta de la línea de presupuesto revisada")
    elegible: bool
    motivo: str = Field(description="Por qué no es elegible, citando el TdR; vacío si es elegible")
    rubros_tdr: List[str] = Field(description="Rubros con tope del TdR a los que pertenece esta línea")


class AuditoriaPresupuesto(BaseModel):
    lineas: List[RevisionLinea]


class PuntajeCriterio(BaseModel):
    criterio: str
    puntaje: int = Field(description="1 insuficiente, 2 regular, 3 bueno, 4 muy bueno")
    justificacion: str
    mejora: str = Field(description="Una mejora concreta para subir el puntaje")


class Evaluacion(BaseModel):
    criterios: List[PuntajeCriterio]
    fortalezas: List[str]
    debilidades: List[str]
