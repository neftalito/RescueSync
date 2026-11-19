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
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import (
    EstadoEmergencia,
    EstadoSincronizacionBonita,
    GravedadEmergencia,
)

if TYPE_CHECKING:
    from app.db.models.convocatoria import Convocatoria
    from app.db.models.lote import Lote
    from app.db.models.organizacion import Organizacion
    from app.db.models.usuario import Usuario


class Emergencia(Base):
    """Conserva los datos operativos y el vínculo BPM de una emergencia."""

    __tablename__ = "emergencia"
    __table_args__ = (
        CheckConstraint("btrim(zona) <> ''", name="zona_no_vacia"),
        CheckConstraint("btrim(descripcion) <> ''", name="descripcion_no_vacia"),
        CheckConstraint("version > 0", name="version_positiva"),
        CheckConstraint("prioridad BETWEEN 1 AND 10", name="prioridad_rango"),
        CheckConstraint(
            "bonita_process_definition_id IS NULL OR bonita_process_definition_id > 0",
            name="bonita_definition_id_positivo",
        ),
        CheckConstraint(
            "bonita_process_instance_id IS NULL OR bonita_process_instance_id > 0",
            name="bonita_instance_id_positivo",
        ),
        CheckConstraint(
            "bonita_sync <> 'VINCULADA' OR bonita_process_instance_id IS NOT NULL",
            name="bonita_vinculada_con_instancia",
        ),
        UniqueConstraint(
            "bonita_process_instance_id",
            name="uq_emergencia_bonita_process_instance_id",
        ),
        Index("ix_emergencia_municipio_estado", "municipio_id", "estado"),
        Index(
            "ix_emergencia_centro_coordinador_estado",
            "centro_coordinador_id",
            "estado",
        ),
        Index("ix_emergencia_bonita_sync", "bonita_sync"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    municipio_id: Mapped[int] = mapped_column(
        ForeignKey("organizacion.id", ondelete="RESTRICT"),
        nullable=False,
    )
    centro_coordinador_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizacion.id", ondelete="RESTRICT"),
        nullable=True,
    )
    creada_por_usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gravedad: Mapped[GravedadEmergencia] = mapped_column(
        Enum(GravedadEmergencia, name="gravedad_emergencia"),
        nullable=False,
    )
    zona: Mapped[str] = mapped_column(String(255), nullable=False)
    prioridad: Mapped[int | None] = mapped_column(Integer, nullable=True)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[EstadoEmergencia] = mapped_column(
        Enum(EstadoEmergencia, name="estado_emergencia"),
        nullable=False,
        default=EstadoEmergencia.REGISTRADA,
        server_default=text("'REGISTRADA'"),
    )
    bonita_process_definition_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    bonita_process_instance_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    bonita_process_version: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    bonita_sync: Mapped[EstadoSincronizacionBonita] = mapped_column(
        Enum(
            EstadoSincronizacionBonita,
            name="estado_sincronizacion_bonita",
        ),
        nullable=False,
        default=EstadoSincronizacionBonita.PENDIENTE,
        server_default=text("'PENDIENTE'"),
    )
    bonita_ultimo_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    bonita_ultimo_intento_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    bonita_claim_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(
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

    municipio: Mapped[Organizacion] = relationship(
        back_populates="emergencias_registradas",
        foreign_keys=[municipio_id],
    )
    centro_coordinador: Mapped[Organizacion | None] = relationship(
        back_populates="emergencias_coordinadas",
        foreign_keys=[centro_coordinador_id],
    )
    creada_por: Mapped[Usuario] = relationship(back_populates="emergencias_creadas")
    lotes: Mapped[list[Lote]] = relationship(back_populates="emergencia")
    convocatorias: Mapped[list[Convocatoria]] = relationship(
        back_populates="emergencia"
    )
