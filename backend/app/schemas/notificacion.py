from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.db.models import TipoNotificacion


class NotificacionResponse(BaseModel):
    """Novedad durable visible únicamente por su destinatario."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    tipo: TipoNotificacion
    titulo: str
    mensaje: str
    ruta: str | None
    leida_en: datetime | None
    creada_en: datetime


class NotificacionesLeidasResponse(BaseModel):
    """Resultado de marcar todas las novedades pendientes del usuario."""

    cantidad_actualizada: int = Field(ge=0)
    leida_en: AwareDatetime


class EventoNotificacion(BaseModel):
    """Mensaje enviado al navegador cuando aparece una notificación."""

    evento: str = "notificacion.creada"
    notificacion: NotificacionResponse
