"""Solicitud durable para reconciliar el alta nacional después de un timeout."""

from uuid import UUID, uuid4

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AprovisionamientoNacional(Base):
    __tablename__ = "aprovisionamiento_nacional"

    organizacion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizacion.id", ondelete="CASCADE"), primary_key=True
    )
    referencia: Mapped[UUID] = mapped_column(default=uuid4, unique=True)
    nombre: Mapped[str] = mapped_column(String(160))
    email_contacto: Mapped[str | None] = mapped_column(String(320))
    secreto_cifrado: Mapped[str] = mapped_column(String(1024))
