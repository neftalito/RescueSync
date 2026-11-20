"""Hechos confirmados del proceso y resultados de los seis indicadores BAM."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.db.models.enums import GravedadEmergencia

Cantidad = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
Referencia = Annotated[str, Field(min_length=1, max_length=120, pattern=r"\S")]


class Hecho(BaseModel):
    """Rechaza campos desconocidos y conserva fechas y cantidades exactas."""

    model_config = ConfigDict(extra="forbid")
    ocurrido_en: AwareDatetime
    convocatoria_numero: int = Field(gt=0)


class DecisionConvocatoria(Hecho):
    tipo: Literal["DECISION_CONVOCATORIA"]
    decision: Literal["REABRIR", "REFORMULAR", "CONTINUAR_PARCIAL"]
    motivo: Referencia


class ResultadoValidacion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ong_id: int = Field(gt=0)
    lote_id: int = Field(gt=0)
    habilitada: bool
    motivos: list[
        Literal[
            "ONG_NO_HABILITADA",
            "SIN_ACREDITACION_VIGENTE",
            "ACREDITACION_VENCIDA",
            "ACREDITACION_REVOCADA",
            "ACREDITACION_FUTURA",
            "CERTIFICACION_INACTIVA",
            "RIESGO_NO_PERMITIDO",
        ]
    ] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validar_habilitacion(self) -> Self:
        if self.habilitada == bool(self.motivos):
            raise ValueError(
                "Una inhabilitación requiere motivos de habilitación; stock y fallos técnicos no son inhabilitaciones."
            )
        return self


class ValidacionNacional(Hecho):
    tipo: Literal["VALIDACION_NACIONAL"]
    validacion_ref: Referencia
    resultados: list[ResultadoValidacion] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def sin_duplicados(self) -> Self:
        claves = {(r.ong_id, r.lote_id) for r in self.resultados}
        if len(claves) != len(self.resultados):
            raise ValueError("Una validación incluye una sola fila por ONG y lote.")
        return self


class AporteAdjudicado(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ong_id: int = Field(gt=0)
    lote_id: int = Field(gt=0)
    cantidad: Cantidad
    plazo_en: AwareDatetime | None = None


class AdjudicacionConfirmada(Hecho):
    tipo: Literal["ADJUDICACION_CONFIRMADA"]
    adjudicacion_ref: Referencia
    alerta_en: AwareDatetime
    aportes: list[AporteAdjudicado] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def sin_duplicados(self) -> Self:
        if self.alerta_en > self.ocurrido_en:
            raise ValueError("La alerta no puede ser posterior a la adjudicación.")
        claves = {(a.ong_id, a.lote_id) for a in self.aportes}
        if len(claves) != len(self.aportes):
            raise ValueError("Una adjudicación incluye una sola fila por ONG y lote.")
        if any(a.plazo_en and a.plazo_en < self.ocurrido_en for a in self.aportes):
            raise ValueError("El plazo del aporte no puede preceder a la adjudicación.")
        return self


class FinalizacionOng(Hecho):
    tipo: Literal["FINALIZACION_ONG"]
    adjudicacion_ref: Referencia
    ong_id: int = Field(gt=0)


class CantidadCumplida(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lote_id: int = Field(gt=0)
    cantidad: Decimal = Field(ge=0, max_digits=14, decimal_places=3)


class ResolucionEmergencia(Hecho):
    tipo: Literal["RESOLUCION_EMERGENCIA"]
    alerta_en: AwareDatetime
    plazo_en: AwareDatetime | None = None
    cobertura: list[CantidadCumplida] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validar_cierre(self) -> Self:
        if self.ocurrido_en < self.alerta_en:
            raise ValueError("La resolución no puede preceder a la alerta.")
        if self.plazo_en and self.plazo_en < self.alerta_en:
            raise ValueError("El plazo no puede preceder a la alerta.")
        if len({c.lote_id for c in self.cobertura}) != len(self.cobertura):
            raise ValueError("La cobertura no puede repetir lotes.")
        return self


type DatosHecho = Annotated[
    DecisionConvocatoria
    | ValidacionNacional
    | AdjudicacionConfirmada
    | FinalizacionOng
    | ResolucionEmergencia,
    Field(discriminator="tipo"),
]


class RegistroHecho(BaseModel):
    """La clave identifica el evento, y debe reutilizarse en cada reintento."""

    model_config = ConfigDict(extra="forbid")
    clave: Referencia
    datos: DatosHecho


class HechoRegistrado(BaseModel):
    id: int
    clave: str
    registrado_en: datetime


class ResolucionGravedad(BaseModel):
    gravedad: GravedadEmergencia
    emergencias: int
    resueltas: int
    cierres_confirmados: int
    resueltas_sin_cierre: int
    con_plazo: int
    en_termino: int
    tasa_resolucion: float | None
    tasa_en_termino: float | None
    promedio_segundos: float | None
    promedio_en_termino_segundos: float | None


class RankingOng(BaseModel):
    ong_id: int
    ong: str
    capacidad: str
    unidad: str
    cantidad: Decimal
    aportes: int
    finalizados: int
    con_plazo_finalizados: int
    en_termino: int
    tasa_cumplimiento: float | None


class DemandaRubro(BaseModel):
    capacidad: str
    unidad: str
    cantidad: Decimal


class CasoReiterado(BaseModel):
    emergencia_id: int
    reaperturas: int
    reformulaciones: int


class CoberturaCierres(BaseModel):
    total: int
    parcial: int
    proporcion_total: float | None
    proporcion_parcial: float | None


class IndicadoresProceso(BaseModel):
    """Las ausencias de hechos/plazos se expresan como null y con cobertura."""

    emergencias_con_hechos: int
    emergencias_sin_hechos: int
    resolucion_por_gravedad: list[ResolucionGravedad]
    reiteradas: list[CasoReiterado]
    ranking_ongs: list[RankingOng]
    cobertura_cierres: CoberturaCierres
    demanda_rubros: list[DemandaRubro]
    alerta_adjudicacion_promedio_segundos: float | None
    alerta_adjudicacion_muestras: int
    definiciones: list[str]
