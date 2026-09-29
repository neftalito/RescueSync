from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import TipoNotificacion

if TYPE_CHECKING:
    from app.db.models.usuario import Usuario


class Notificacion(Base):
    """Conserva una novedad durable dirigida a un usuario concreto."""

    __tablename__ = "notificacion"
    __table_args__ = (
        CheckConstraint("btrim(clave_evento) <> ''", name="clave_evento_no_vacia"),
        CheckConstraint("btrim(titulo) <> ''", name="titulo_no_vacio"),
        CheckConstraint("btrim(mensaje) <> ''", name="mensaje_no_vacio"),
        CheckConstraint(
            "ruta IS NULL OR ruta LIKE '/%'",
            name="ruta_relativa",
        ),
        UniqueConstraint(
            "usuario_id",
            "clave_evento",
            name="uq_notificacion_usuario_evento",
        ),
        Index("ix_notificacion_usuario_creada", "usuario_id", "creada_en"),
        Index("ix_notificacion_usuario_leida", "usuario_id", "leida_en"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id", ondelete="CASCADE"),
        nullable=False,
    )
    clave_evento: Mapped[str] = mapped_column(String(180), nullable=False)
    tipo: Mapped[TipoNotificacion] = mapped_column(
        Enum(TipoNotificacion, name="tipo_notificacion"),
        nullable=False,
    )
    titulo: Mapped[str] = mapped_column(String(140), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    ruta: Mapped[str | None] = mapped_column(String(255), nullable=True)
    leida_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    usuario: Mapped[Usuario] = relationship(back_populates="notificaciones")
