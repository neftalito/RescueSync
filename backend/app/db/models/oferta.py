from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import EstadoOferta, TipoAporte, TipoParticipacion

if TYPE_CHECKING:
    from app.db.models.convocatoria import Convocatoria, ConvocatoriaLote
    from app.db.models.organizacion import Organizacion
    from app.db.models.usuario import Usuario


class Oferta(Base):
    """Representa la identidad estable de una propuesta de ayuda."""

    __tablename__ = "oferta"
    __table_args__ = (
        CheckConstraint("version_actual > 0", name="version_actual_positiva"),
        CheckConstraint("version_bloqueo > 0", name="version_bloqueo_positiva"),
        CheckConstraint(
            "fusionada_en_oferta_id IS NULL OR fusionada_en_oferta_id <> id",
            name="fusion_distinta",
        ),
        Index(
            "uq_oferta_convocatoria_ong_vigente",
            "convocatoria_id",
            "ong_creadora_id",
            unique=True,
            postgresql_where=text("fusionada_en_oferta_id IS NULL"),
        ),
        Index("ix_oferta_convocatoria_estado", "convocatoria_id", "estado"),
        Index("ix_oferta_ong_estado", "ong_creadora_id", "estado"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    convocatoria_id: Mapped[int] = mapped_column(
        ForeignKey("convocatoria.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ong_creadora_id: Mapped[int] = mapped_column(
        ForeignKey("organizacion.id", ondelete="RESTRICT"),
        nullable=False,
    )
    creada_por_usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fusionada_en_oferta_id: Mapped[int | None] = mapped_column(
        ForeignKey("oferta.id", ondelete="RESTRICT"),
        nullable=True,
    )
    estado: Mapped[EstadoOferta] = mapped_column(
        Enum(EstadoOferta, name="estado_oferta"),
        nullable=False,
        default=EstadoOferta.BORRADOR,
        server_default=text("'BORRADOR'"),
    )
    version_actual: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    version_bloqueo: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    actualizada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    convocatoria: Mapped[Convocatoria] = relationship(back_populates="ofertas")
    ong_creadora: Mapped[Organizacion] = relationship(
        back_populates="ofertas_creadas",
        foreign_keys=[ong_creadora_id],
    )
    creada_por: Mapped[Usuario] = relationship(back_populates="ofertas_creadas")
    versiones: Mapped[list[OfertaVersion]] = relationship(back_populates="oferta")
    participantes: Mapped[list[OfertaParticipante]] = relationship(
        back_populates="oferta"
    )


class OfertaVersion(Base):
    """Conserva una revisión inmutable del contenido de una oferta."""

    __tablename__ = "oferta_version"
    __table_args__ = (
        CheckConstraint("numero > 0", name="numero_positivo"),
        UniqueConstraint(
            "oferta_id",
            "numero",
            name="uq_oferta_version_oferta_numero",
        ),
        Index(
            "ix_oferta_version_oferta_numero_desc",
            "oferta_id",
            text("numero DESC"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    oferta_id: Mapped[int] = mapped_column(
        ForeignKey("oferta.id", ondelete="RESTRICT"),
        nullable=False,
    )
    creada_por_usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=False,
    )
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    presentada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    oferta: Mapped[Oferta] = relationship(back_populates="versiones")
    creada_por: Mapped[Usuario] = relationship(
        back_populates="versiones_oferta_creadas"
    )
    items: Mapped[list[OfertaItem]] = relationship(back_populates="oferta_version")


class OfertaItem(Base):
    """Detalla el aporte ofrecido para un lote publicado."""

    __tablename__ = "oferta_item"
    __table_args__ = (
        CheckConstraint("btrim(descripcion) <> ''", name="descripcion_no_vacia"),
        CheckConstraint("cantidad_ofrecida > 0", name="cantidad_positiva"),
        CheckConstraint("btrim(unidad) <> ''", name="unidad_no_vacia"),
        UniqueConstraint(
            "oferta_version_id",
            "lote_id",
            name="uq_oferta_item_version_lote",
        ),
        ForeignKeyConstraint(
            ["convocatoria_id", "lote_id"],
            [
                "convocatoria_lote.convocatoria_id",
                "convocatoria_lote.lote_id",
            ],
            name="fk_oferta_item_convocatoria_lote",
            ondelete="RESTRICT",
        ),
        Index("ix_oferta_item_lote", "lote_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    oferta_version_id: Mapped[int] = mapped_column(
        ForeignKey("oferta_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    convocatoria_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lote_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tipo: Mapped[TipoAporte] = mapped_column(
        Enum(TipoAporte, name="tipo_aporte"),
        nullable=False,
    )
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    cantidad_ofrecida: Mapped[Decimal] = mapped_column(
        Numeric(14, 3),
        nullable=False,
    )
    unidad: Mapped[str] = mapped_column(String(40), nullable=False)

    oferta_version: Mapped[OfertaVersion] = relationship(back_populates="items")
    convocatoria_lote: Mapped[ConvocatoriaLote] = relationship(
        back_populates="items_oferta"
    )


class OfertaParticipante(Base):
    """Vincula las ONGs que integran una oferta individual o conjunta."""

    __tablename__ = "oferta_participante"
    __table_args__ = (
        PrimaryKeyConstraint("oferta_id", "ong_id", name="pk_oferta_participante"),
        Index(
            "uq_oferta_participante_lider",
            "oferta_id",
            unique=True,
            postgresql_where=text("rol = 'LIDER'"),
        ),
    )

    oferta_id: Mapped[int] = mapped_column(
        ForeignKey("oferta.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ong_id: Mapped[int] = mapped_column(
        ForeignKey("organizacion.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rol: Mapped[TipoParticipacion] = mapped_column(
        Enum(TipoParticipacion, name="tipo_participacion"),
        nullable=False,
    )
    incorporada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    oferta: Mapped[Oferta] = relationship(back_populates="participantes")
    ong: Mapped[Organizacion] = relationship(back_populates="participaciones_oferta")
