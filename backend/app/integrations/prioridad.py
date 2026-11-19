"""Cliente HTTP del servicio de priorización de emergencias."""

import httpx
from pydantic import ValidationError

from app.schemas.emergencia import PrioridadCalculada, SolicitudPrioridadEmergencia


class PrioridadNoDisponibleError(RuntimeError):
    """El servicio de priorización no pudo atender la consulta."""


class RespuestaPrioridadInvalidaError(RuntimeError):
    """El servicio respondió con un resultado incompatible con el contrato."""


class ClientePrioridad:
    """Reutiliza conexiones al servicio y valida cada puntuación recibida."""

    def __init__(self, base_url: str, timeout: float) -> None:
        self.http = httpx.Client(base_url=base_url.rstrip("/") + "/", timeout=timeout)

    def consultar(self, datos: SolicitudPrioridadEmergencia) -> int:
        """Envía únicamente gravedad y zona al servicio de priorización."""

        try:
            respuesta = self.http.post(
                "prioridades", json=datos.model_dump(mode="json")
            )
        except httpx.RequestError as error:
            raise PrioridadNoDisponibleError from error

        if respuesta.status_code >= 500:
            raise PrioridadNoDisponibleError
        if respuesta.status_code != 200:
            raise RespuestaPrioridadInvalidaError
        try:
            return PrioridadCalculada.model_validate_json(respuesta.content).prioridad
        except ValidationError as error:
            raise RespuestaPrioridadInvalidaError from error

    def close(self) -> None:
        self.http.close()
