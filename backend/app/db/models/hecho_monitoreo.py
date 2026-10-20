"""Registro inmutable de evidencia de negocio confirmada por el proceso BPM."""

from datetime import datetime

from pydantic import JsonValue
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HechoMonitoreo(Base):
    __tablename__ = "hecho_monitoreo"
    __table_args__ = (
        UniqueConstraint("emergencia_id", "clave", name="uq_hecho_emergencia_clave"),
        UniqueConstraint("emergencia_id", "referencia", name="uq_hecho_referencia"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    emergencia_id: Mapped[int] = mapped_column(
        ForeignKey("emergencia.id", ondelete="RESTRICT"), index=True
    )
    clave: Mapped[str] = mapped_column(String(120))
    referencia: Mapped[str] = mapped_column(String(255))
    datos: Mapped[dict[str, JsonValue]] = mapped_column(JSONB)
    registrado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
