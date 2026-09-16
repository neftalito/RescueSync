"""Cliente HTTPX reutilizable de FastAPI para la API REST de Bonita."""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Self

import httpx
from pydantic import BaseModel, SecretStr, TypeAdapter, ValidationError

from app.core.config import Settings
from app.integrations.bonita.contratos import (
    CasoBonita,
    ContratoInicioProceso,
    DefinicionProceso,
    InstanciaIniciada,
    TareaHumana,
    UsuarioBonita,
)

LOGGER = logging.getLogger(__name__)

CABECERA_CSRF = "X-Bonita-API-Token"
Parametros = Sequence[tuple[str, str | int]]


class ErrorBonita(RuntimeError):
    """Fallo de integración con un mensaje apto para registrar sin secretos."""


class BonitaNoDisponibleError(ErrorBonita):
    """Bonita no respondió; la operación no llegó a producir efectos."""


class BonitaCredencialesError(ErrorBonita):
    """Bonita rechazó la cuenta técnica configurada."""


class BonitaRespuestaInvalidaError(ErrorBonita):
    """Bonita respondió con un formato distinto del contrato esperado."""


class BonitaProcesoNoDisponibleError(ErrorBonita):
    """La definición configurada no existe, no está resuelta o no está habilitada."""


class BonitaOperacionRechazadaError(ErrorBonita):
    """Bonita procesó la petición y la rechazó de forma definitiva."""

    def __init__(self, mensaje: str, explicaciones: tuple[str, ...] = ()) -> None:
        super().__init__(mensaje)
        self.explicaciones = explicaciones


class BonitaResultadoDesconocidoError(ErrorBonita):
    """La conexión se perdió después de enviar una operación con efectos.

    Bonita pudo haberla aplicado. No se debe repetir sin reconciliar antes, por
    ejemplo con `buscar_casos_por_emergencia`.
    """


class _RespuestaErrorBonita(BaseModel):
    message: str | None = None
    explanations: list[str | None] = []


@dataclass(frozen=True)
class ConfiguracionBonita:
    """Parámetros de conexión del backend con el Runtime."""

    base_url: str
    usuario: str
    password: SecretStr
    nombre_proceso: str
    version_proceso: str
    timeout_conexion_segundos: float
    timeout_lectura_segundos: float

    @classmethod
    def desde_settings(cls, settings: Settings) -> ConfiguracionBonita:
        """Toma la configuración centralizada del backend."""

        return cls(
            base_url=settings.bonita_base_url.rstrip("/"),
            usuario=settings.bonita_username,
            password=settings.bonita_password,
            nombre_proceso=settings.bonita_process_name,
            version_proceso=settings.bonita_process_version,
            timeout_conexion_segundos=settings.bonita_client_connect_timeout_seconds,
            timeout_lectura_segundos=settings.bonita_client_read_timeout_seconds,
        )


class ClienteBonita:
    """Adaptador de la API REST de Bonita con sesión y token CSRF compartidos.

    Es seguro usarlo desde varios hilos del threadpool de FastAPI: la sesión se
    renueva una sola vez cuando Bonita responde 401.
    """

    def __init__(
        self,
        configuracion: ConfiguracionBonita,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.configuracion = configuracion
        self._http = httpx.Client(
            base_url=configuracion.base_url,
            timeout=httpx.Timeout(
                configuracion.timeout_lectura_segundos,
                connect=configuracion.timeout_conexion_segundos,
            ),
            headers={"Accept": "application/json"},
            follow_redirects=False,
            transport=transport,
        )
        self._lock = threading.Lock()
        self._token_csrf: str | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Libera las conexiones del pool HTTP."""

        self._http.close()

    def obtener_proceso_habilitado(self) -> DefinicionProceso:
        """Resuelve por nombre y versión la definición lista para iniciar casos."""

        respuesta = self._enviar(
            "GET",
            "/API/bpm/process",
            params=[
                ("p", 0),
                ("c", 2),
                ("f", f"name={self.configuracion.nombre_proceso}"),
                ("f", f"version={self.configuracion.version_proceso}"),
            ],
        )
        definiciones = _validar_lista(respuesta, DefinicionProceso, "procesos")
        etiqueta = (
            f"{self.configuracion.nombre_proceso}:{self.configuracion.version_proceso}"
        )
        if len(definiciones) != 1:
            raise BonitaProcesoNoDisponibleError(
                f"Se esperaba una definición {etiqueta}; Bonita devolvió "
                f"{len(definiciones)}."
            )
        definicion = definiciones[0]
        if not definicion.lista_para_iniciar:
            raise BonitaProcesoNoDisponibleError(
                f"El proceso {etiqueta} está {definicion.configuration_state} y "
                f"{definicion.activation_state}."
            )
        return definicion

    def iniciar_instancia(
        self,
        proceso_id: int,
        contrato: ContratoInicioProceso,
    ) -> InstanciaIniciada:
        """Crea un caso y devuelve su `caseId`.

        Raises:
            BonitaOperacionRechazadaError: el contrato fue rechazado; reintentar
                con los mismos datos volverá a fallar.
            BonitaResultadoDesconocidoError: el caso pudo crearse igualmente.
        """

        respuesta = self._enviar(
            "POST",
            f"/API/bpm/process/{proceso_id}/instantiation",
            json=contrato.a_payload(),
            con_efectos=True,
        )
        return _validar_objeto(respuesta, InstanciaIniciada, "instanciación")

    def buscar_casos_por_emergencia(
        self,
        proceso_id: int,
        id_emergencia: int,
    ) -> list[CasoBonita]:
        """Busca casos activos por el índice `idEmergencia` para reconciliar.

        No incluye casos archivados, es decir, finalizados o cancelados.
        """

        respuesta = self._enviar(
            "GET",
            "/API/bpm/case",
            params=[
                ("p", 0),
                ("c", 10),
                ("f", f"processDefinitionId={proceso_id}"),
                ("f", f"searchIndex1Value={id_emergencia}"),
            ],
        )
        return _validar_lista(respuesta, CasoBonita, "casos")

    def buscar_tarea_lista(self, case_id: int, nombre: str) -> TareaHumana | None:
        """Obtiene la tarea humana pendiente con el nombre indicado."""

        respuesta = self._enviar(
            "GET",
            "/API/bpm/humanTask",
            params=[
                ("p", 0),
                ("c", 2),
                ("f", f"caseId={case_id}"),
                ("f", "state=ready"),
                ("f", f"name={nombre}"),
            ],
        )
        tareas = _validar_lista(respuesta, TareaHumana, "tareas")
        if len(tareas) > 1:
            raise BonitaRespuestaInvalidaError(
                f"El caso {case_id} tiene más de una tarea lista llamada {nombre!r}."
            )
        return tareas[0] if tareas else None

    def ejecutar_tarea(self, tarea_id: int, usuario_actor: str) -> None:
        """Asigna una tarea a un miembro de su actor y la completa sin entradas.

        Bonita solo ejecuta tareas asignadas a un candidato del actor; la cuenta
        técnica no lo es. Solo admite tareas cuyo contrato está vacío.
        """

        usuario = self._obtener_usuario(usuario_actor)
        self._enviar(
            "PUT",
            f"/API/bpm/humanTask/{tarea_id}",
            json={"assigned_id": str(usuario.id)},
        )
        self._enviar(
            "POST",
            f"/API/bpm/userTask/{tarea_id}/execution",
            json={},
            con_efectos=True,
        )

    def _obtener_usuario(self, nombre_usuario: str) -> UsuarioBonita:
        respuesta = self._enviar(
            "GET",
            "/API/identity/user",
            params=[("p", 0), ("c", 2), ("f", f"userName={nombre_usuario}")],
        )
        usuarios = [
            usuario
            for usuario in _validar_lista(respuesta, UsuarioBonita, "usuarios")
            if usuario.user_name == nombre_usuario
        ]
        if len(usuarios) != 1:
            raise BonitaOperacionRechazadaError(
                f"No existe un único usuario {nombre_usuario!r} en Bonita."
            )
        return usuarios[0]

    def _enviar(
        self,
        metodo: str,
        ruta: str,
        *,
        params: Parametros | None = None,
        json: dict[str, str | int] | None = None,
        con_efectos: bool = False,
    ) -> httpx.Response:
        """Envía una petición autenticada y traduce los fallos de transporte.

        Un 401 garantiza que Bonita no procesó la operación, por lo que se
        renueva la sesión y se repite una sola vez incluso si tiene efectos.
        """

        token = self._token_vigente()
        respuesta = self._transportar(metodo, ruta, params, json, token, con_efectos)
        if respuesta.status_code == httpx.codes.UNAUTHORIZED:
            token = self._token_vigente(rechazado=token)
            respuesta = self._transportar(
                metodo, ruta, params, json, token, con_efectos
            )

        if respuesta.is_success:
            return respuesta
        operacion = f"{metodo} {ruta}"
        if respuesta.status_code == httpx.codes.UNAUTHORIZED:
            raise BonitaCredencialesError(
                f"{operacion}: Bonita rechazó la sesión renovada."
            )
        if respuesta.status_code in {502, 503, 504}:
            error = (
                BonitaResultadoDesconocidoError
                if con_efectos
                else BonitaNoDisponibleError
            )
            raise error(f"{operacion}: Bonita respondió HTTP {respuesta.status_code}.")
        detalle = _leer_error(respuesta)
        raise BonitaOperacionRechazadaError(
            f"{operacion}: Bonita respondió HTTP {respuesta.status_code}."
            + (f" {detalle.message}" if detalle.message else ""),
            tuple(texto for texto in detalle.explanations if texto),
        )

    def _transportar(
        self,
        metodo: str,
        ruta: str,
        params: Parametros | None,
        json: dict[str, str | int] | None,
        token: str,
        con_efectos: bool,
    ) -> httpx.Response:
        try:
            return self._http.request(
                metodo,
                ruta,
                params=params,
                json=json,
                headers={CABECERA_CSRF: token},
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as error:
            # La petición no llegó a enviarse: es seguro informarla como no aplicada.
            raise BonitaNoDisponibleError(
                f"{metodo} {ruta}: no se pudo conectar con Bonita."
            ) from error
        except httpx.TransportError as error:
            tipo = (
                BonitaResultadoDesconocidoError
                if con_efectos
                else BonitaNoDisponibleError
            )
            raise tipo(
                f"{metodo} {ruta}: se perdió la respuesta de Bonita "
                f"({type(error).__name__})."
            ) from error

    def _token_vigente(self, rechazado: str | None = None) -> str:
        with self._lock:
            if self._token_csrf is None or self._token_csrf == rechazado:
                self._token_csrf = self._iniciar_sesion()
            return self._token_csrf

    def _iniciar_sesion(self) -> str:
        self._http.cookies.clear()
        try:
            respuesta = self._http.post(
                "/loginservice",
                data={
                    "username": self.configuracion.usuario,
                    "password": self.configuracion.password.get_secret_value(),
                    "redirect": "false",
                },
            )
        except httpx.TransportError as error:
            raise BonitaNoDisponibleError(
                "No se pudo iniciar sesión: Bonita no respondió."
            ) from error

        if respuesta.status_code in {401, 403}:
            raise BonitaCredencialesError("Bonita rechazó las credenciales técnicas.")
        if respuesta.status_code not in {200, 204}:
            raise BonitaNoDisponibleError(
                f"El login de Bonita respondió HTTP {respuesta.status_code}."
            )
        token = respuesta.cookies.get(CABECERA_CSRF)
        if not token:
            raise BonitaRespuestaInvalidaError(
                "Bonita inició la sesión sin entregar el token CSRF."
            )
        LOGGER.info("Sesión técnica iniciada en Bonita.")
        return token


def _validar_lista[T: BaseModel](
    respuesta: httpx.Response,
    modelo: type[T],
    recurso: str,
) -> list[T]:
    try:
        return TypeAdapter(list[modelo]).validate_json(respuesta.content)
    except ValidationError as error:
        raise BonitaRespuestaInvalidaError(
            f"Bonita devolvió {recurso} con un formato inesperado."
        ) from error


def _validar_objeto[T: BaseModel](
    respuesta: httpx.Response,
    modelo: type[T],
    recurso: str,
) -> T:
    try:
        return modelo.model_validate_json(respuesta.content)
    except ValidationError as error:
        raise BonitaRespuestaInvalidaError(
            f"Bonita devolvió una {recurso} con un formato inesperado."
        ) from error


def _leer_error(respuesta: httpx.Response) -> _RespuestaErrorBonita:
    try:
        return _RespuestaErrorBonita.model_validate_json(respuesta.content)
    except ValidationError:
        return _RespuestaErrorBonita()
