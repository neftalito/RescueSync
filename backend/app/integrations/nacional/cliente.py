"""Cliente compartido con timeout, validación de DTO y errores seguros."""

from uuid import UUID

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.schemas.inventario import (
    CapacidadResponse,
    ConexionRequest,
    CuentaNacional,
    RecursoCreate,
    RecursoResponse,
    RecursoUpdate,
    TokenNacional,
)


class ErrorNacional(ValueError):
    """Fallo externo traducido sin propagar cuerpos, credenciales ni URLs."""

    def __init__(self, status: int, mensaje: str) -> None:
        self.status = status
        super().__init__(mensaje)


class ClienteNacional:
    """Reutiliza conexiones HTTP durante la vida de FastAPI; nunca reintenta POST."""

    def __init__(self, base_url: str, timeout: float) -> None:
        self.http = httpx.Client(
            base_url=base_url.rstrip("/") + "/", timeout=timeout, follow_redirects=False
        )

    def close(self) -> None:
        self.http.close()

    def _request[T](
        self,
        method: str,
        path: str,
        adapter: TypeAdapter[T],
        *,
        token: str | None = None,
        datos: BaseModel | None = None,
    ) -> T:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        # Sólo el límite HTTP obtiene la contraseña sin cifrar, nunca repr/logs.
        if isinstance(datos, ConexionRequest):
            payload = {
                "identificadorLogin": datos.identificador_login,
                "password": datos.password.get_secret_value(),
            }
        else:
            payload = datos.model_dump(mode="json", by_alias=True) if datos else None
        try:
            response = self.http.request(method, path, headers=headers, json=payload)
        except httpx.TimeoutException as error:
            raise ErrorNacional(
                504,
                "El Sistema Nacional demoró en responder. Actualizá el listado para comprobar el resultado antes de repetir la operación.",
            ) from error
        except httpx.RequestError as error:
            raise ErrorNacional(
                503, "No pudimos comunicarnos con el Sistema Nacional."
            ) from error
        if not response.is_success:
            mensajes = {
                401: "La credencial nacional no es válida o expiró. Volvé a conectar tu cuenta.",
                403: "La cuenta nacional no tiene permisos para esta operación.",
                404: "La ONG, capacidad o recurso no existe en el Sistema Nacional.",
                409: "Hay un conflicto: el código puede estar repetido, el recurso cambió o el total es menor que lo comprometido. Actualizá el listado.",
                422: "Revisá los datos, cantidades y unidades del recurso.",
            }
            raise ErrorNacional(
                response.status_code if response.status_code in mensajes else 502,
                mensajes.get(
                    response.status_code,
                    "El Sistema Nacional no pudo completar la solicitud.",
                ),
            )
        try:
            return adapter.validate_json(response.content)
        except ValidationError as error:
            raise ErrorNacional(
                502, "El Sistema Nacional devolvió una respuesta inválida."
            ) from error

    def login(self, datos: ConexionRequest) -> TokenNacional:
        return self._request("POST", "login", TypeAdapter(TokenNacional), datos=datos)

    def cuenta(self, token: str) -> CuentaNacional:
        return self._request("GET", "me", TypeAdapter(CuentaNacional), token=token)

    def capacidades(self, token: str) -> list[CapacidadResponse]:
        return self._request(
            "GET", "capacidades", TypeAdapter(list[CapacidadResponse]), token=token
        )

    def recursos(self, token: str, ong_id: UUID) -> list[RecursoResponse]:
        return self._request(
            "GET",
            f"ongs/{ong_id}/recursos",
            TypeAdapter(list[RecursoResponse]),
            token=token,
        )

    def crear(self, token: str, ong_id: UUID, datos: RecursoCreate) -> RecursoResponse:
        return self._request(
            "POST",
            f"ongs/{ong_id}/recursos",
            TypeAdapter(RecursoResponse),
            token=token,
            datos=datos,
        )

    def actualizar(
        self, token: str, ong_id: UUID, recurso_id: UUID, datos: RecursoUpdate
    ) -> RecursoResponse:
        return self._request(
            "PATCH",
            f"ongs/{ong_id}/recursos/{recurso_id}",
            TypeAdapter(RecursoResponse),
            token=token,
            datos=datos,
        )
