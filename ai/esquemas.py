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
    seccion_id: str = Field(description="Id de la sección de texto: resumen, antecedentes, comprension, postor, "
                                        "estrategia, monitoreo, riesgos o salvaguardas")
    parrafos: List[Parrafo]
    pendientes: List[str]


class TextosPropuesta(BaseModel):
    titulo_proyecto: str
    secciones: List[SeccionGenerada]


# ---------------------------------------------------------------- Propuesta técnica (estructura de postor)
class Dato(BaseModel):
    campo: str
    valor: str


class DatosReferencia(BaseModel):
    nombre_servicio: str = Field(description="Nombre de la consultoría, servicio o proyecto, tal como lo llama el TdR")
    presentado_a: str = Field(description="Organización convocante o donante a la que se presenta la propuesta")
    sistema_contratacion: str = Field(description="P. ej. 'Suma alzada', 'Subvención', 'Contrato de servicios'; "
                                                  "[POR COMPLETAR] si el TdR no lo dice")
    plazo_ejecucion: str = Field(description="P. ej. '120 días calendario' o '12 meses'")
    ambito: str = Field(description="Ámbito geográfico de intervención")
    postor: str = Field(description="Organización que postula")
    otros: List[Dato] = Field(description="Otros datos útiles del TdR: código del proceso, población objetivo, "
                                          "fecha de presentación. NO incluyas montos ni precios.")


class AspectoTdR(BaseModel):
    aspecto: str = Field(description="Uno de: Resultados mínimos esperados, Enfoques exigidos, Condiciones "
                                     "críticas, Gestión contractual")
    lectura: str = Field(description="Qué exige el TdR y cómo lo atenderá el postor, en 2 a 3 frases concretas")


class ObjetivoTecnico(BaseModel):
    codigo: str = Field(description="OE1, OE2, ...")
    texto: str


class Momento(BaseModel):
    nombre: str = Field(description="Etapa de la metodología, p. ej. 'Diagnóstico', 'Selección', 'Organización', "
                                    "'Formación', 'Acompañamiento', 'Cierre'")
    contenido_tecnico: List[str] = Field(description="3 a 5 palabras clave del trabajo técnico, p. ej. "
                                                     "'levantamiento de información', 'criterios de viabilidad'")
    productos: List[str] = Field(description="Productos verificables, p. ej. 'fichas de padrón', 'matriz de "
                                             "selección', 'actas', 'reglamentos', 'reportes de asistencia técnica'")


class Componente(BaseModel):
    codigo: str = Field(description="C1, C2, ...")
    nombre: str
    objetivo: str = Field(description="Código del objetivo específico al que responde (OE1, OE2, ...)")
    lineas_accion: List[str]
    actividades: List[str] = Field(description="4 a 6 actividades principales, concretas")
    resultados: List[str] = Field(description="2 a 4 resultados esperados, medibles cuando sea posible")


class Entregable(BaseModel):
    codigo: str = Field(description="E1, E2, ...")
    nombre: str
    plazo: str = Field(description="Fecha o plazo máximo de entrega, p. ej. 'Día 30' o 'Mes 3'")
    contenido: str = Field(description="Resumen del contenido principal del entregable, en 1 a 2 frases")


class FilaCronograma(BaseModel):
    actividad: str
    periodo: str = Field(description="P. ej. 'Mes 1' o 'Meses 2 a 4'")
    mes_inicio: int
    mes_fin: int
    resultado: str = Field(description="Resultado esperado de esa actividad")


class Rol(BaseModel):
    rol: str
    nombre: str = Field("", description="Nombre de la persona propuesta, solo si viene en un CV subido; si no, vacío")
    perfil: str = Field(description="Formación y experiencia mínima, según el TdR")
    dedicacion: str = Field(description="P. ej. 'Tiempo completo', '50%', 'Por producto'")
    responsabilidades: List[str]


class Riesgo(BaseModel):
    riesgo: str
    efecto: str = Field(description="Posible efecto sobre el servicio o el grupo meta")
    mitigacion: str = Field(description="Medida concreta de prevención o mitigación")


class Salvaguarda(BaseModel):
    tipo: str = Field(description="Social, Financiera, Digital o Institucional")
    medidas: List[str]


BLOQUES = ["resumen", "antecedentes", "comprension", "postor", "objetivos", "metodologia", "estrategia",
           "monitoreo", "componentes", "entregables", "cronograma", "equipo", "riesgos", "salvaguardas", "matriz"]


class SeccionTdR(BaseModel):
    titulo: str = Field(description="Título de la sección tal como lo pide el TdR")
    bloques: List[str] = Field(description="Bloques de contenido que van en esta sección, en orden, elegidos de: "
                                           + ", ".join(BLOQUES))
    nota: str = Field(description="Si ningún bloque calza, qué debe completar el postor en esta sección; si no, vacío")


class PropuestaTecnica(BaseModel):
    """Diseño de la propuesta técnica: lo que va en cuadros y listas del documento."""

    datos: DatosReferencia
    aspectos_tdr: List[AspectoTdR] = Field(description="Exactamente 4: Resultados mínimos esperados, Enfoques "
                                                       "exigidos, Condiciones críticas y Gestión contractual")
    objetivo_general: str = Field(description="Un solo párrafo de 60 palabras como máximo (4 a 5 líneas)")
    objetivos_especificos: List[ObjetivoTecnico] = Field(description="3 a 5 objetivos específicos")
    principios: List[str] = Field(description="4 a 6 principios o enfoques de trabajo, cada uno en una frase")
    momentos: List[Momento] = Field(description="4 a 7 momentos de la metodología, en orden")
    palabras_clave_monitoreo: List[str] = Field(description="4 a 6 palabras clave del monitoreo y evaluación")
    componentes: List[Componente] = Field(description="Un componente por objetivo específico")
    entregables: List[Entregable] = Field(description="Entregables con código E1, E2..., según el TdR")
    cronograma: List[FilaCronograma] = Field(description="De la planificación a la evaluación y cierre")
    resumen_equipo: str = Field(description="2 a 3 frases sobre el equipo técnico que se necesita")
    equipo: List[Rol]
    criterios_calidad: List[str] = Field(description="Criterios de calidad, p. ej. prevención, transparencia, "
                                                     "mejora continua; cada uno con una frase")
    riesgos: List[Riesgo] = Field(description="5 a 7 riesgos principales")
    salvaguardas: List[Salvaguarda] = Field(description="Social, Financiera, Digital e Institucional")
    estructura_tdr: List[SeccionTdR] = Field(description="Solo si el TdR exige un índice para la propuesta "
                                                         "técnica; si no, lista vacía")
    pendientes: List[str] = Field(description="Datos que el postor debe completar")


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
    secciones_requeridas: List[str] = Field(description="Índice o secciones que el TdR exige para la PROPUESTA "
                                            "TÉCNICA, con sus títulos tal cual y en su orden; lista vacía si el TdR "
                                            "no fija un formato. No incluyas documentos administrativos (DNI, "
                                            "vigencia de poder, declaraciones juradas) ni la propuesta económica.")
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
