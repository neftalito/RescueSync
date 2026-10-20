"""Intenciones locales inmutables y confirmaciones de la integración nacional."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import EstadoOperacion, EstadoTareaBonita, TipoOperacion


class EvaluacionLocal(Base):
    __tablename__ = "evaluacion_local"
    __table_args__ = (
        UniqueConstraint("convocatoria_id", "revision"),
        CheckConstraint("revision > 0", name="revision_positiva"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    emergencia_id: Mapped[int] = mapped_column(ForeignKey("emergencia.id"))
    convocatoria_id: Mapped[int] = mapped_column(ForeignKey("convocatoria.id"))
    revision: Mapped[int] = mapped_column(Integer)
    huella_snapshot: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    resultado: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB)
    cobertura: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ComandoBonita(Base):
    """Despacho de una intención; conserva actividad exacta, claim y contrato."""

    __tablename__ = "comando_bonita"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    emergencia_id: Mapped[int] = mapped_column(ForeignKey("emergencia.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    tarea: Mapped[str] = mapped_column(String(160))
    actor: Mapped[str] = mapped_column(String(80))
    correlacion: Mapped[str] = mapped_column(String(120))
    contrato: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    tarea_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    estado: Mapped[EstadoTareaBonita] = mapped_column(
        Enum(EstadoTareaBonita, name="estado_tarea_bonita"),
        default=EstadoTareaBonita.PENDIENTE,
    )
    claim_id: Mapped[UUID | None] = mapped_column()
    intento_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(500))


class DecisionLocal(Base):
    __tablename__ = "decision_evaluacion"
    __table_args__ = (UniqueConstraint("evaluacion_id"),)
    id: Mapped[UUID] = mapped_column(ForeignKey("comando_bonita.id"), primary_key=True)
    evaluacion_id: Mapped[UUID] = mapped_column(ForeignKey("evaluacion_local.id"))
    contenido: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)


class OperacionNacional(Base):
    __tablename__ = "operacion_nacional_sync"
    __table_args__ = (
        Index("ix_operacion_nacional_emergencia_estado", "emergencia_id", "estado"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    emergencia_id: Mapped[int] = mapped_column(ForeignKey("emergencia.id"))
    tipo: Mapped[TipoOperacion] = mapped_column(
        Enum(TipoOperacion, name="tipo_operacion_nacional")
    )
    estado: Mapped[EstadoOperacion] = mapped_column(
        Enum(EstadoOperacion, name="estado_operacion_nacional"),
        default=EstadoOperacion.PENDIENTE,
    )
    clave: Mapped[str] = mapped_column(String(120), unique=True)
    huella: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    confirmacion: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB)
    resultado: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB)


class AdjudicacionLocal(Base):
    __tablename__ = "adjudicacion_local"
    __table_args__ = (
        Index(
            "uq_adjudicacion_efectiva_ronda",
            "convocatoria_id",
            unique=True,
            postgresql_where=text("estado <> 'REQUIERE_REVISION'"),
        ),
        CheckConstraint(
            "estado IN ('PENDIENTE_COMPROMISO','CONFIRMADA','REQUIERE_REVISION')",
            name="estado_valido",
        ),
    )
    id: Mapped[UUID] = mapped_column(ForeignKey("comando_bonita.id"), primary_key=True)
    convocatoria_id: Mapped[int] = mapped_column(ForeignKey("convocatoria.id"))
    evaluacion_id: Mapped[UUID] = mapped_column(ForeignKey("evaluacion_local.id"))
    operacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("operacion_nacional_sync.id"), unique=True
    )
    seleccion: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    estado: Mapped[str] = mapped_column(String(30), default="PENDIENTE_COMPROMISO")
    proyecto_id: Mapped[UUID | None] = mapped_column()


class ParticipacionLocal(Base):
    __tablename__ = "participacion_adjudicada"
    __table_args__ = (
        UniqueConstraint(
            "adjudicacion_id", "ong_id", name="uq_participacion_ong_local"
        ),
        UniqueConstraint(
            "adjudicacion_id", "ong_nacional_id", name="uq_participacion_ong_nacional"
        ),
        CheckConstraint(
            "estado IN ('EN_EJECUCION','FINALIZACION_SOLICITADA','LIBERADA')",
            name="estado_valido",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    adjudicacion_id: Mapped[UUID] = mapped_column(ForeignKey("adjudicacion_local.id"))
    ong_id: Mapped[int] = mapped_column(ForeignKey("organizacion.id"))
    ong_nacional_id: Mapped[UUID] = mapped_column()
    estado: Mapped[str] = mapped_column(String(30), default="EN_EJECUCION")


class CompromisoLocal(Base):
    __tablename__ = "compromiso_nacional_local"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    participacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("participacion_adjudicada.id"), index=True
    )
    detalle: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    liberacion_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("operacion_nacional_sync.id"), unique=True
    )
    liberado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FinalizacionLocal(Base):
    __tablename__ = "finalizacion_ong"
    id: Mapped[UUID] = mapped_column(ForeignKey("comando_bonita.id"), primary_key=True)
    participacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("participacion_adjudicada.id"), unique=True
    )
    solicitada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CierreLocal(Base):
    __tablename__ = "solicitud_cierre"
    id: Mapped[UUID] = mapped_column(ForeignKey("comando_bonita.id"), primary_key=True)
    adjudicacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("adjudicacion_local.id"), unique=True
    )
    operacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("operacion_nacional_sync.id"), unique=True
    )
