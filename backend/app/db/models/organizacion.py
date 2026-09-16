from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import TipoOrganizacion

if TYPE_CHECKING:
    from app.db.models.emergencia import Emergencia
    from app.db.models.oferta import Oferta, OfertaParticipante
    from app.db.models.usuario import Usuario


class Organizacion(Base):
    """Representa un municipio, un centro coordinador o una ONG."""

    __tablename__ = "organizacion"
    __table_args__ = (
        CheckConstraint("btrim(nombre) <> ''", name="nombre_no_vacio"),
        Index("uq_organizacion_tipo_nombre", "tipo", "nombre", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tipo: Mapped[TipoOrganizacion] = mapped_column(
        Enum(TipoOrganizacion, name="tipo_organizacion"),
        nullable=False,
    )
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    activa: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
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

    usuarios: Mapped[list[Usuario]] = relationship(back_populates="organizacion")
    emergencias_registradas: Mapped[list[Emergencia]] = relationship(
        back_populates="municipio",
        foreign_keys="Emergencia.municipio_id",
    )
    emergencias_coordinadas: Mapped[list[Emergencia]] = relationship(
        back_populates="centro_coordinador",
        foreign_keys="Emergencia.centro_coordinador_id",
    )
    ofertas_creadas: Mapped[list[Oferta]] = relationship(
        back_populates="ong_creadora",
        foreign_keys="Oferta.ong_creadora_id",
    )
    participaciones_oferta: Mapped[list[OfertaParticipante]] = relationship(
        back_populates="ong"
    )
