"""Acceso institucional cifrado, compartido entre representantes y workers."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccesoNacional(Base):
    __tablename__ = "acceso_nacional"

    organizacion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizacion.id", ondelete="CASCADE"), primary_key=True
    )
    ong_id: Mapped[UUID]
    cuenta_id: Mapped[UUID]
    configuracion_id: Mapped[UUID]
    identificador_login: Mapped[str] = mapped_column(String(320))
    secreto_cifrado: Mapped[str] = mapped_column(String(1024))
    token_cifrado: Mapped[str | None] = mapped_column(String(4096))
    expira_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requiere_revision: Mapped[bool] = mapped_column(server_default=text("false"))
