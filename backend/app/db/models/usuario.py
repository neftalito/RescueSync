from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import RolUsuario

if TYPE_CHECKING:
    from app.db.models.emergencia import Emergencia
    from app.db.models.lote import Lote
    from app.db.models.oferta import Oferta, OfertaVersion
    from app.db.models.organizacion import Organizacion


class Usuario(Base):
    """Almacena la identidad, las credenciales y el rol local de una persona."""

    __tablename__ = "usuario"
    __table_args__ = (
        CheckConstraint("btrim(email) <> ''", name="email_no_vacio"),
        CheckConstraint(
            "password_hash LIKE '$argon2%'",
            name="password_hash_argon2",
        ),
        CheckConstraint("version_sesion > 0", name="version_sesion_positiva"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    organizacion_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizacion.id", ondelete="RESTRICT"),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[RolUsuario] = mapped_column(
        Enum(RolUsuario, name="rol_usuario"),
        nullable=False,
    )
    activo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    requiere_cambio_password: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    version_sesion: Mapped[int] = mapped_column(
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

    organizacion: Mapped[Organizacion | None] = relationship(back_populates="usuarios")
    emergencias_creadas: Mapped[list[Emergencia]] = relationship(
        back_populates="creada_por"
    )
    lotes_creados: Mapped[list[Lote]] = relationship(back_populates="creado_por")
    ofertas_creadas: Mapped[list[Oferta]] = relationship(back_populates="creada_por")
    versiones_oferta_creadas: Mapped[list[OfertaVersion]] = relationship(
        back_populates="creada_por"
    )


Index("uq_usuario_email_normalizado", func.lower(Usuario.email), unique=True)
