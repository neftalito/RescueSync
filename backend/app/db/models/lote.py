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
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import EstadoLote, GravedadEmergencia

if TYPE_CHECKING:
    from app.db.models.convocatoria import ConvocatoriaLote
    from app.db.models.emergencia import Emergencia
    from app.db.models.usuario import Usuario


class Lote(Base):
    """Describe una necesidad cuantificada dentro de una emergencia."""

    __tablename__ = "lote"
    __table_args__ = (
        CheckConstraint("btrim(tipo_necesidad) <> ''", name="tipo_no_vacio"),
        CheckConstraint("cantidad_requerida > 0", name="cantidad_positiva"),
        CheckConstraint("btrim(unidad) <> ''", name="unidad_no_vacia"),
        CheckConstraint("version > 0", name="version_positiva"),
        Index("ix_lote_emergencia_estado", "emergencia_id", "estado"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    emergencia_id: Mapped[int] = mapped_column(
        ForeignKey("emergencia.id", ondelete="RESTRICT"),
        nullable=False,
    )
    creado_por_usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tipo_necesidad: Mapped[str] = mapped_column(String(160), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    cantidad_requerida: Mapped[Decimal] = mapped_column(
        Numeric(14, 3),
        nullable=False,
    )
    unidad: Mapped[str] = mapped_column(String(40), nullable=False)
    capacidad_nacional_id: Mapped[UUID | None] = mapped_column()
    codigo_capacidad: Mapped[str | None] = mapped_column(String(80))
    admite_fracciones: Mapped[bool | None] = mapped_column()
    riesgo_requerido: Mapped[GravedadEmergencia | None] = mapped_column(
        Enum(GravedadEmergencia, name="gravedad_emergencia")
    )
    estado: Mapped[EstadoLote] = mapped_column(
        Enum(EstadoLote, name="estado_lote"),
        nullable=False,
        default=EstadoLote.BORRADOR,
        server_default=text("'BORRADOR'"),
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    emergencia: Mapped[Emergencia] = relationship(back_populates="lotes")
    creado_por: Mapped[Usuario] = relationship(back_populates="lotes_creados")
    publicaciones: Mapped[list[ConvocatoriaLote]] = relationship(back_populates="lote")
