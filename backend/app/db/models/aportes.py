"""Identidades y recursos externos congelados dentro de una versión local."""

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
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import TipoParticipacion

if TYPE_CHECKING:
    from app.db.models.oferta import OfertaItem, OfertaVersion


class OfertaVersionParticipante(Base):
    __tablename__ = "oferta_version_participante"
    __table_args__ = (
        Index(
            "uq_oferta_version_participante_lider",
            "oferta_version_id",
            unique=True,
            postgresql_where=text("rol = 'LIDER'"),
        ),
    )
    oferta_version_id: Mapped[int] = mapped_column(
        ForeignKey("oferta_version.id", ondelete="RESTRICT"), primary_key=True
    )
    ong_id: Mapped[int] = mapped_column(
        ForeignKey("organizacion.id", ondelete="RESTRICT"), primary_key=True
    )
    ong_nacional_id: Mapped[UUID | None] = mapped_column()
    nombre_ong: Mapped[str] = mapped_column(String(160))
    rol: Mapped[TipoParticipacion] = mapped_column(
        Enum(TipoParticipacion, name="tipo_participacion")
    )
    confirmada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version_origen_id: Mapped[int | None] = mapped_column(
        ForeignKey("oferta_version.id", ondelete="RESTRICT")
    )
    version: Mapped[OfertaVersion] = relationship(
        back_populates="participantes", foreign_keys=[oferta_version_id]
    )


class OfertaItemAporte(Base):
    __tablename__ = "oferta_item_aporte"
    __table_args__ = (
        ForeignKeyConstraint(
            ["oferta_item_id", "oferta_version_id"],
            ["oferta_item.id", "oferta_item.oferta_version_id"],
            name="fk_aporte_item_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["oferta_version_id", "ong_id"],
            [
                "oferta_version_participante.oferta_version_id",
                "oferta_version_participante.ong_id",
            ],
            name="fk_aporte_participante_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "oferta_item_id",
            "ong_id",
            "recurso_nacional_id",
            name="uq_aporte_item_ong_recurso",
        ),
        CheckConstraint(
            "cantidad > 0 AND cantidad < 'Infinity'::numeric",
            name="ck_aporte_cantidad_finita",
        ),
        CheckConstraint("btrim(unidad) <> ''", name="ck_aporte_unidad"),
        Index("ix_aporte_recurso_nacional", "recurso_nacional_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    oferta_item_id: Mapped[int] = mapped_column(BigInteger)
    oferta_version_id: Mapped[int] = mapped_column(BigInteger)
    ong_id: Mapped[int] = mapped_column(BigInteger)
    recurso_nacional_id: Mapped[UUID] = mapped_column()
    capacidad_nacional_id: Mapped[UUID] = mapped_column()
    cantidad: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unidad: Mapped[str] = mapped_column(String(40))
    item: Mapped[OfertaItem] = relationship(
        back_populates="aportes", overlaps="participantes"
    )
