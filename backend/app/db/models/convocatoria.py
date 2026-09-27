from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import EstadoConvocatoria, EstadoTareaBonita

if TYPE_CHECKING:
    from app.db.models.emergencia import Emergencia
    from app.db.models.lote import Lote
    from app.db.models.oferta import Oferta, OfertaItem


class Convocatoria(Base):
    """Representa una ronda temporal de recepción de ofertas."""

    __tablename__ = "convocatoria"
    __table_args__ = (
        CheckConstraint("numero > 0", name="numero_positivo"),
        CheckConstraint("cierra_en > publicada_en", name="ventana_valida"),
        CheckConstraint(
            "estado <> 'CERRADA' OR cerrada_en IS NOT NULL",
            name="cerrada_con_fecha",
        ),
        CheckConstraint(
            "(bonita_generar_lotes_intento_id IS NULL) = "
            "(bonita_generar_lotes_intento_expira_en IS NULL)",
            name="bonita_generar_lotes_intento_completo",
        ),
        UniqueConstraint(
            "emergencia_id",
            "numero",
            name="uq_convocatoria_emergencia_numero",
        ),
        Index("ix_convocatoria_emergencia_estado", "emergencia_id", "estado"),
        Index(
            "uq_convocatoria_abierta_por_emergencia",
            "emergencia_id",
            unique=True,
            postgresql_where=text("estado = 'ABIERTA'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    emergencia_id: Mapped[int] = mapped_column(
        ForeignKey("emergencia.id", ondelete="RESTRICT"),
        nullable=False,
    )
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[EstadoConvocatoria] = mapped_column(
        Enum(EstadoConvocatoria, name="estado_convocatoria"),
        nullable=False,
        default=EstadoConvocatoria.ABIERTA,
        server_default=text("'ABIERTA'"),
    )
    publicada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    cierra_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cerrada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    bonita_generar_lotes_estado: Mapped[EstadoTareaBonita] = mapped_column(
        Enum(EstadoTareaBonita, name="estado_tarea_bonita"),
        nullable=False,
        default=EstadoTareaBonita.PENDIENTE,
        server_default=text("'PENDIENTE'"),
    )
    bonita_generar_lotes_ultimo_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    bonita_generar_lotes_ultimo_intento_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    bonita_generar_lotes_intento_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        nullable=True,
    )
    bonita_generar_lotes_intento_expira_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    emergencia: Mapped[Emergencia] = relationship(back_populates="convocatorias")
    lotes: Mapped[list[ConvocatoriaLote]] = relationship(back_populates="convocatoria")
    ofertas: Mapped[list[Oferta]] = relationship(back_populates="convocatoria")


class ConvocatoriaLote(Base):
    """Conserva el snapshot de un lote publicado en una convocatoria."""

    __tablename__ = "convocatoria_lote"
    __table_args__ = (
        CheckConstraint("cantidad_publicada > 0", name="cantidad_positiva"),
        CheckConstraint("btrim(unidad_publicada) <> ''", name="unidad_no_vacia"),
        PrimaryKeyConstraint(
            "convocatoria_id",
            "lote_id",
            name="pk_convocatoria_lote",
        ),
    )

    convocatoria_id: Mapped[int] = mapped_column(
        ForeignKey("convocatoria.id", ondelete="RESTRICT"),
        nullable=False,
    )
    lote_id: Mapped[int] = mapped_column(
        ForeignKey("lote.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cantidad_publicada: Mapped[Decimal] = mapped_column(
        Numeric(14, 3),
        nullable=False,
    )
    unidad_publicada: Mapped[str] = mapped_column(String(40), nullable=False)

    convocatoria: Mapped[Convocatoria] = relationship(back_populates="lotes")
    lote: Mapped[Lote] = relationship(back_populates="publicaciones")
    items_oferta: Mapped[list[OfertaItem]] = relationship(
        back_populates="convocatoria_lote"
    )
