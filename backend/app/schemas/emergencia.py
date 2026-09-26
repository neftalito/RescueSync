"""Esquemas HTTP para el registro municipal de emergencias."""

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.db.models.enums import (
    EstadoEmergencia,
    EstadoSincronizacionBonita,
    GravedadEmergencia,
)


class EmergenciaCreate(BaseModel):
    """Datos obligatorios que envía el municipio para registrar una emergencia."""

    gravedad: GravedadEmergencia
    zona: str = Field(min_length=1, max_length=255)
    descripcion: str = Field(min_length=1, max_length=2000)

    @field_validator("zona", "descripcion", mode="before")
    @classmethod
    def recortar_texto(cls, valor: object) -> object:
        """Elimina espacios accidentales para rechazar textos solo con blancos."""

        return valor.strip() if isinstance(valor, str) else valor


class EmergenciaResponse(BaseModel):
    """Emergencia persistida con su estado inicial y vínculo municipal."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    municipio_id: int
    centro_coordinador_id: int | None
    creada_por_usuario_id: int
    gravedad: GravedadEmergencia
    zona: str
    descripcion: str
    estado: EstadoEmergencia
    bonita_sync: EstadoSincronizacionBonita
    bonita_process_instance_id: int | None
    creada_en: AwareDatetime
    actualizada_en: AwareDatetime


class EmergenciaBandejaResponse(EmergenciaResponse):
    """Emergencia de la bandeja con los lotes que todavía puede publicar.

    La cantidad viene del servicio de publicación, pero la resuelve la base para
    que la interfaz no tenga que pedir los lotes de cada fila para decidir si
    ofrece la acción de publicar.
    """

    cantidad_lotes_borrador: int = Field(ge=0)
