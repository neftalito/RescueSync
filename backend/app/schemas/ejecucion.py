"""Contratos locales T36/T37; Bonita transporta referencias y resultados nacionales."""

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.db.models.enums import (
    EstadoEmergencia,
    EstadoOperacion,
    GravedadEmergencia,
    TipoOperacion,
)
from app.schemas.bonita import CantidadExacta
from app.schemas.certificaciones import CapacidadHabilitadaResponse

type Cantidad = Annotated[
    CantidadExacta, Field(gt=0, max_digits=14, decimal_places=3, allow_inf_nan=False)
]
type Disponible = Annotated[
    CantidadExacta, Field(ge=0, max_digits=18, decimal_places=3, allow_inf_nan=False)
]
type IdLocal = Annotated[int, Field(gt=0)]


class Contrato(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class Clasificacion(StrEnum):
    PRINCIPAL = "PRINCIPAL"
    APOYO = "APOYO"
    SIN_HABILITACION = "SIN_HABILITACION"


class AccionEvaluacion(StrEnum):
    REABRIR = "REABRIR"
    REFORMULAR = "REFORMULAR"
    CONTINUAR_PARCIAL = "CONTINUAR_PARCIAL"


class MotivoValidacion(Contrato):
    codigo: str = Field(min_length=1, max_length=80)
    mensaje: str = Field(max_length=1000)


class AporteEvaluado(Contrato):
    oferta_id: IdLocal
    version: IdLocal
    item_id: IdLocal
    lote_id: IdLocal
    aporte_id: IdLocal | None
    ong_id: IdLocal
    ong_nacional_id: UUID | None
    recurso_nacional_id: UUID | None
    cantidad_ofrecida: Cantidad
    unidad: str = Field(min_length=1, max_length=40)
    clasificacion: Clasificacion
    capacidades_habilitadas: list[CapacidadHabilitadaResponse]
    niveles_riesgo_permitidos: list[GravedadEmergencia]
    cantidad_disponible_consultada: Disponible | None
    motivos: list[MotivoValidacion]


class RecursoConsultado(Contrato):
    recurso_nacional_id: UUID
    ong_nacional_id: UUID
    capacidad_nacional_id: UUID
    unidad: str = Field(min_length=1, max_length=40)
    cantidad_disponible: Disponible
    cantidad_solicitada_snapshot: Disponible


class ValidacionNacional(Contrato):
    contrato_version: Literal[2]
    sistema_origen: str
    id_emergencia: IdLocal
    case_id: str
    convocatoria_id: IdLocal
    numero: IdLocal
    evaluado_en: AwareDatetime
    aportes: list[AporteEvaluado] = Field(max_length=5000)
    recursos_consultados: list[RecursoConsultado] = Field(max_length=5000)


class PreparacionValidacion(Contrato):
    validacion_id: UUID
    convocatoria_id: IdLocal
    intento_convocatoria: IdLocal


class PreparacionResponse(PreparacionValidacion):
    revision: IdLocal
    huella_snapshot: str


class PerfilesRequest(PreparacionResponse):
    validacion: ValidacionNacional


class Asignacion(Contrato):
    aporte_id: IdLocal
    cantidad: Disponible


class CoberturaLote(Contrato):
    lote_id: IdLocal
    cantidad_requerida: Disponible
    cantidad_asignable: Disponible
    faltante: Disponible
    unidad: str
    aportes: list[Asignacion]


class PerfilesResponse(PreparacionResponse):
    evaluado_en: AwareDatetime
    vigente: bool
    lotes_compatibles_cubiertos: bool
    cobertura: list[CoberturaLote]


class AporteElegible(Contrato):
    descripcion: str = ""
    nombre_ong: str = ""
    tipo_necesidad: str = ""
    aporte_id: IdLocal
    oferta_id: IdLocal
    version: IdLocal
    lote_id: IdLocal
    ong_id: IdLocal
    ong_nacional_id: UUID
    recurso_nacional_id: UUID
    capacidad_nacional_id: UUID
    riesgo_requerido: GravedadEmergencia
    cantidad_ofrecida: Cantidad
    cantidad_disponible: Disponible
    unidad: str
    admite_fracciones: bool
    clasificacion: Clasificacion


class OfertasValidadasResponse(Contrato):
    validacion: PerfilesResponse | None
    aportes: list[AporteElegible]
    diagnosticos: list[AporteEvaluado]
    permite_parcial: bool


class DecisionRequest(Contrato):
    decision_id: UUID
    validacion_id: UUID
    revision: IdLocal
    convocatoria_id: IdLocal
    accion: AccionEvaluacion
    motivo: str = Field(min_length=3, max_length=1000)


class ConvocatoriaPreparada(Contrato):
    convocatoria_id: IdLocal
    numero: IdLocal


class DecisionResponse(DecisionRequest):
    case_id: str
    intento_convocatoria: IdLocal
    convocatoria_preparada: ConvocatoriaPreparada | None = None


class Seleccion(Contrato):
    aporte_id: IdLocal
    cantidad: Cantidad


class AdjudicacionRequest(Contrato):
    adjudicacion_id: UUID
    validacion_id: UUID
    revision: IdLocal
    aportes: list[Seleccion] = Field(min_length=1, max_length=5000)


class AporteCompromiso(Contrato):
    oferta_id: str
    version: IdLocal
    lote_id: str
    aporte_id: str
    ong_nacional_id: UUID
    recurso_nacional_id: UUID
    capacidad_nacional_id: UUID
    riesgo_requerido: GravedadEmergencia
    cantidad: Cantidad
    unidad: str


class CompromisoRequest(Contrato):
    sistema_origen: str
    id_emergencia: str
    case_id: str
    convocatoria_id: str
    adjudicacion_id: str
    aportes: list[AporteCompromiso]


class AdjudicacionPreparada(Contrato):
    adjudicacion_id: UUID
    version: IdLocal
    convocatoria_id: IdLocal
    validacion_id: UUID
    operacion_compromiso_id: UUID
    idempotency_key: str
    huella_request: str
    compromiso: CompromisoRequest


class ConfirmacionCompromisos(Contrato):
    operacion_id: UUID
    proyecto_id: UUID
    compromiso_ids: list[UUID] = Field(min_length=1)
    registrado_en: AwareDatetime


class ItemCompromiso(AporteCompromiso):
    id: UUID
    convocatoria_id: str


class DetalleCompromiso(Contrato):
    id: UUID
    proyecto_id: UUID
    sistema_origen: str
    id_emergencia: str
    case_id: str
    adjudicacion_id: str
    ong_nacional_id: UUID
    estado: Literal["ACTIVO", "LIBERADO"]
    creado_en: AwareDatetime
    liberado_en: AwareDatetime | None
    liberado_por_id: UUID | None
    items: list[ItemCompromiso]


class ConfirmarCompromisosRequest(Contrato):
    adjudicacion_id: UUID
    adjudicacion_version: IdLocal
    operacion_compromiso_id: UUID
    huella_request: str
    confirmacion: ConfirmacionCompromisos
    compromisos: list[DetalleCompromiso] = Field(min_length=1)


class ParticipacionResponse(Contrato):
    participacion_id: UUID
    ong_id: IdLocal
    ong_nacional_id: UUID
    compromiso_ids: list[UUID]
    estado: Literal["EN_EJECUCION", "FINALIZACION_SOLICITADA", "LIBERADA"]
    finalizacion_id: UUID | None = None


class AdjudicacionResponse(Contrato):
    adjudicacion_id: UUID
    version: IdLocal
    estado: Literal["PENDIENTE_COMPROMISO", "CONFIRMADA", "REQUIERE_REVISION"]
    operacion_compromiso_id: UUID
    estado_integracion: EstadoOperacion
    proyecto_id: UUID | None
    participantes: list[ParticipacionResponse]


class NotificarAdjudicacionRequest(Contrato):
    adjudicacion_id: UUID
    adjudicacion_version: IdLocal


class ResultadoOperacionRequest(Contrato):
    tipo: TipoOperacion
    estado_integracion: Literal[
        "INCIERTO", "TEMPORAL", "CONFIGURACION", "RECHAZO_DEFINITIVO"
    ]
    http_status: Annotated[int, Field(ge=100, le=599)] | None = None
    codigo_error: Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,80}$")] | None = None
    idempotency_key: str
    etapa: (
        Literal[
            "COMPROMISO_NACIONAL",
            "CONSULTA_COMPROMISOS",
            "CONFIRMACION_LOCAL",
            "NOTIFICACION",
            "LIBERACION_NACIONAL",
            "CONFIRMACION_LIBERACION",
            "CIERRE_NACIONAL",
            "RESOLVER",
        ]
        | None
    ) = None


class OperacionResponse(Contrato):
    operacion_id: UUID
    tipo: TipoOperacion
    estado_integracion: EstadoOperacion
    etapa_pendiente: str | None = None


class RecuperacionRequest(Contrato):
    recuperacion_id: UUID
    accion: Literal["REINTENTAR_MISMA_OPERACION", "VOLVER_A_SELECCION"]


class FinalizacionResponse(Contrato):
    finalizacion_id: UUID
    participacion_id: UUID
    solicitada_en: AwareDatetime


class RequestCaso(Contrato):
    case_id: str


class LiberacionPreparada(Contrato):
    operacion_id: UUID
    compromiso_id: UUID
    idempotency_key: str
    request: RequestCaso


class LiberacionesResponse(FinalizacionResponse):
    operaciones: list[LiberacionPreparada]


class ConfirmacionLiberacion(Contrato):
    operacion_id: UUID
    proyecto_id: UUID
    compromiso_id: UUID
    ong_nacional_id: UUID
    liberado_en: AwareDatetime


class LiberacionConfirmadaRequest(Contrato):
    finalizacion_id: UUID
    participacion_id: UUID
    operacion_id: UUID
    confirmacion: ConfirmacionLiberacion


class CierrePreparado(Contrato):
    solicitud_cierre_id: UUID
    proyecto_id: UUID
    case_id: str
    operacion_cierre_id: UUID
    idempotency_key: str
    request: RequestCaso
    liberaciones_confirmadas: bool
    operaciones_inciertas: bool


class ConfirmacionCierre(Contrato):
    operacion_id: UUID
    proyecto_id: UUID
    cerrado_en: AwareDatetime


class ResolverRequest(Contrato):
    id_emergencia: IdLocal
    estado: Literal["RESUELTA"]
    proyecto_nacional_id: UUID
    solicitud_cierre_id: UUID
    operacion_cierre_id: UUID
    cierre: ConfirmacionCierre


class ResolucionResponse(Contrato):
    id_emergencia: IdLocal
    estado: EstadoEmergencia
    proyecto_nacional_id: UUID
    cerrado_en: AwareDatetime


class SeguimientoResponse(Contrato):
    id_emergencia: IdLocal
    estado: EstadoEmergencia
    adjudicaciones: list[AdjudicacionResponse]
    puede_solicitar_cierre: bool
    cierre: CierrePreparado | None
    operaciones: list[OperacionResponse] = Field(default_factory=list)


class DespachoResponse(Contrato):
    comando_id: UUID
    estado: str
    error: str | None
