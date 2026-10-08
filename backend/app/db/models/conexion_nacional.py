"""Credencial temporal cifrada, ligada al usuario y a su versión local."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConexionNacional(Base):
    """Comparte la conexión entre workers sin poner JWT en cookies ni respuestas."""

    __tablename__ = "conexion_nacional"
    __table_args__ = (
        CheckConstraint("version_sesion > 0", name="version_sesion_positiva"),
    )

    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True
    )
    version_sesion: Mapped[int]
    ong_id: Mapped[UUID]
    token_cifrado: Mapped[str] = mapped_column(String(4096))
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
