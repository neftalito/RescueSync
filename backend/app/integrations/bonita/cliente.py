"""Cliente HTTPX reutilizable de FastAPI para la API REST de Bonita."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Self

import httpx
from pydantic import (
    BaseModel,
    Field,
    JsonValue,
    SecretStr,
    TypeAdapter,
    ValidationError,
)

from app.core.config import Settings
from app.integrations.bonita.contratos import (
    CasoBonita,
    ContratoInicioProceso,
    DefinicionProceso,
    FechaTemporizador,
    InstanciaIniciada,
    TareaActiva,
    TareaBonitaFallida,
    TareaHumana,
    TemporizadorBonita,
    TransicionTareaArchivada,
    UsuarioBonita,
)

LOGGER = logging.getLogger(__name__)

CABECERA_CSRF = "X-Bonita-API-Token"
Parametros = Sequence[tuple[str, str | int]]


class ErrorBonita(RuntimeError):
    """Fallo de integración con un mensaje apto para registrar sin secretos."""


class BonitaNoDisponibleError(ErrorBonita):
    """Bonita no confirmó una operación que puede repetirse de forma segura."""


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
    explanations: list[str | None] = Field(default_factory=list)


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
            estados_esperados=(httpx.codes.OK,),
        )
        definiciones = _validar_lista(respuesta, DefinicionProceso, "procesos")
        etiqueta = (
            f"{self.configuracion.nombre_proceso}:{self.configuracion.version_proceso}"
        )
        if any(
            definicion.name != self.configuracion.nombre_proceso
            or definicion.version != self.configuracion.version_proceso
            for definicion in definiciones
        ):
            raise BonitaRespuestaInvalidaError(
                f"Bonita devolvió una definición ajena al proceso {etiqueta}."
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
            # Bonita 10.4.0 devuelve 200 aunque su OpenAPI 1.0.6 declara 201.
            estados_esperados=(httpx.codes.OK, httpx.codes.CREATED),
            resultado_puede_ser_ambiguo=True,
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
            estados_esperados=(httpx.codes.OK,),
        )
        casos = _validar_lista(respuesta, CasoBonita, "casos")
        if any(
            caso.process_definition_id != proceso_id
            or caso.etiqueta_id_emergencia != "idEmergencia"
            or caso.id_emergencia_indexado != str(id_emergencia)
            for caso in casos
        ):
            raise BonitaRespuestaInvalidaError(
                "Bonita devolvió un caso que no coincide con la emergencia buscada."
            )
        return casos

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
            estados_esperados=(httpx.codes.OK,),
        )
        tareas = _validar_lista(respuesta, TareaHumana, "tareas")
        if any(
            tarea.case_id != case_id or tarea.name != nombre or tarea.state != "ready"
            for tarea in tareas
        ):
            raise BonitaRespuestaInvalidaError(
                f"Bonita devolvió una tarea que no coincide con el caso {case_id}."
            )
        if len(tareas) > 1:
            raise BonitaRespuestaInvalidaError(
                f"El caso {case_id} tiene más de una tarea lista llamada {nombre!r}."
            )
        return tareas[0] if tareas else None

    def tarea_completada(self, case_id: int, nombre: str) -> bool:
        """Confirma en el historial archivado que la tarea humana se completó.

        A diferencia de `buscar_tarea_lista`, que solo ve tareas activas, esto
        consulta el archivo de Bonita: es la única evidencia confiable de que
        una tarea terminó, porque dejar de estar `ready` también puede
        significar que solo se asignó sin llegar a ejecutarse.
        """

        respuesta = self._enviar(
            "GET",
            "/API/bpm/archivedHumanTask",
            params=[
                ("p", 0),
                ("c", 5),
                ("f", f"caseId={case_id}"),
                ("f", f"name={nombre}"),
                ("f", "state=completed"),
            ],
            estados_esperados=(httpx.codes.OK,),
        )
        tareas = _validar_lista(respuesta, TareaHumana, "tareas archivadas")
        if any(tarea.case_id != case_id or tarea.name != nombre for tarea in tareas):
            raise BonitaRespuestaInvalidaError(
                f"Bonita devolvió una tarea archivada que no coincide con el "
                f"caso {case_id}."
            )
        return len(tareas) > 0

    def listar_tareas_fallidas(self) -> list[TareaBonitaFallida]:
        """Pagina nodos fallidos; el servicio restringe los casos a emergencias locales."""
        resultado: list[TareaBonitaFallida] = []
        for pagina in range(100):
            respuesta = self._enviar(
                "GET",
                "/API/bpm/flowNode",
                params=[
                    ("p", pagina),
                    ("c", 100),
                    ("f", "state=failed"),
                    ("o", "name ASC"),
                ],
                estados_esperados=(httpx.codes.OK,),
            )
            filas = _validar_lista(respuesta, TareaBonitaFallida, "tareas fallidas")
            resultado.extend(filas)
            if len(filas) < 100:
                return resultado
        raise BonitaRespuestaInvalidaError(
            "Las tareas fallidas superan el límite de paginación segura."
        )

    def buscar_temporizador(
        self, case_id: int, nombre: str
    ) -> TemporizadorBonita | None:
        """Encuentra un disparo pendiente de una instancia concreta."""
        respuesta = self._enviar(
            "GET",
            "/API/bpm/timerEventTrigger",
            params=[("caseId", case_id), ("p", 0), ("c", 100)],
            estados_esperados=(httpx.codes.OK,),
        )
        timers = _validar_lista(respuesta, TemporizadorBonita, "temporizadores")
        coincidencias = [t for t in timers if t.name == nombre]
        if len(timers) >= 100 or len(coincidencias) > 1:
            raise BonitaRespuestaInvalidaError(
                f"No se pudo identificar un único temporizador {nombre!r} para el caso {case_id}."
            )
        return coincidencias[0] if coincidencias else None

    def reprogramar_temporizador(self, temporizador_id: int, fecha_ms: int) -> None:
        """Adelanta o pospone un disparo existente conservando el parámetro del BPM."""
        respuesta = self._enviar(
            "PUT",
            f"/API/bpm/timerEventTrigger/{temporizador_id}",
            json={"executionDate": fecha_ms},
            estados_esperados=(httpx.codes.OK,),
        )
        fecha = _validar_objeto(respuesta, FechaTemporizador, "fecha del temporizador")
        if fecha.execution_date_ms != fecha_ms:
            raise BonitaRespuestaInvalidaError(
                f"Bonita devolvió un vencimiento distinto para el temporizador {temporizador_id}."
            )

    def obtener_tareas_activas(self, case_id: int) -> list[TareaActiva]:
        """Pagina nodos actuales del caso sin ejecutar ni modificar tareas."""
        resultado: list[TareaActiva] = []
        for pagina in range(100):
            respuesta = self._enviar(
                "GET",
                "/API/bpm/flowNode",
                params=[
                    ("p", pagina),
                    ("c", 100),
                    ("f", f"caseId={case_id}"),
                    ("o", "name ASC"),
                ],
                estados_esperados=(httpx.codes.OK,),
            )
            filas = _validar_lista(respuesta, TareaActiva, "tareas activas")
            if any(f.root_case_id != case_id for f in filas):
                raise BonitaRespuestaInvalidaError(
                    "Bonita devolvió tareas activas de otro caso."
                )
            resultado.extend(filas)
            if len(filas) < 100:
                return resultado
        raise BonitaRespuestaInvalidaError(
            "Las tareas activas superan el límite de paginación segura."
        )

    def obtener_historial_tareas(self, case_id: int) -> list[TransicionTareaArchivada]:
        """Lee todas las transiciones archivadas de un caso, con paginación.

        En Bonita 10.4 `archivedActivity` y `archivedTask` solo devuelven la
        última versión; `archivedFlowNode` conserva también los estados
        intermedios. El ID fuente distingue cada ejecución de una tarea.
        """
        transiciones: list[TransicionTareaArchivada] = []
        for pagina in range(100):
            respuesta = self._enviar(
                "GET",
                "/API/bpm/archivedFlowNode",
                params=[
                    ("p", pagina),
                    ("c", 100),
                    ("f", f"caseId={case_id}"),
                    ("o", "archivedDate ASC"),
                ],
                estados_esperados=(httpx.codes.OK,),
            )
            filas = _validar_lista(
                respuesta, TransicionTareaArchivada, "historial de tareas"
            )
            if any(fila.root_case_id != case_id for fila in filas):
                raise BonitaRespuestaInvalidaError(
                    "Bonita devolvió historial de otro caso."
                )
            transiciones.extend(filas)
            if len(filas) < 100:
                break
        else:
            raise BonitaRespuestaInvalidaError(
                "El historial supera el límite de paginación segura."
            )
        return transiciones

    def ejecutar_tarea(
        self,
        tarea_id: int,
        usuario_actor: str,
        contrato: dict[str, JsonValue] | None = None,
    ) -> None:
        """Asigna una tarea a un miembro de su actor y la completa sin entradas.

        Bonita solo ejecuta tareas asignadas a un candidato del actor; la cuenta
        técnica no lo es. Solo admite tareas cuyo contrato está vacío.
        """

        usuario = self._obtener_usuario(usuario_actor)
        self._enviar(
            "PUT",
            f"/API/bpm/humanTask/{tarea_id}",
            json={"assigned_id": str(usuario.id)},
            estados_esperados=(httpx.codes.OK,),
        )
        self._enviar(
            "POST",
            f"/API/bpm/userTask/{tarea_id}/execution",
            json={} if contrato is None else contrato,
            estados_esperados=(httpx.codes.NO_CONTENT,),
            resultado_puede_ser_ambiguo=True,
        )

    def tarea_exacta(self, tarea_id: int, case_id: int, nombre: str) -> TareaHumana:
        """Revalida la actividad persistida antes de asignarla o ejecutarla."""
        respuesta = self._enviar(
            "GET", f"/API/bpm/humanTask/{tarea_id}", estados_esperados=(httpx.codes.OK,)
        )
        tarea = _validar_objeto(respuesta, TareaHumana, "tarea")
        if (
            tarea.id != tarea_id
            or tarea.case_id != case_id
            or tarea.name != nombre
            or tarea.state != "ready"
        ):
            raise BonitaRespuestaInvalidaError(
                "La actividad no corresponde a la intención pendiente."
            )
        return tarea

    def tareas_para_comando(self, case_id: int, nombre: str) -> list[TareaHumana]:
        """Lista candidatas sin elegir arbitrariamente una instancia paralela."""
        respuesta = self._enviar(
            "GET",
            "/API/bpm/humanTask",
            params=[
                ("p", 0),
                ("c", 1000),
                ("f", f"caseId={case_id}"),
                ("f", f"name={nombre}"),
                ("f", "state=ready"),
            ],
            estados_esperados=(httpx.codes.OK,),
        )
        tareas = _validar_lista(respuesta, TareaHumana, "tareas")
        if len(tareas) >= 1000 or any(
            t.case_id != case_id or t.name != nombre or t.state != "ready"
            for t in tareas
        ):
            raise BonitaRespuestaInvalidaError(
                "La lista de actividades no corresponde al comando."
            )
        return tareas

    def variable_correlacion(
        self,
        case_id: int,
        tarea_id: int,
        participante: bool,
        operacion: bool = False,
    ) -> str:
        """Consulta un escalar definido en Studio, nunca un Map Java serializado."""
        if operacion:
            ruta = f"/API/bpm/activityVariable/{tarea_id}/operacionIdEsperada"
        elif participante:
            ruta = f"/API/bpm/activityVariable/{tarea_id}/participacionIdEsperada"
        else:
            ruta = f"/API/bpm/caseVariable/{case_id}/intentoConvocatoria"
        respuesta = self._enviar("GET", ruta, estados_esperados=(httpx.codes.OK,))
        try:
            contenido = respuesta.json()
        except json.JSONDecodeError as error:
            raise BonitaRespuestaInvalidaError(
                "La correlación de la actividad no es JSON válido."
            ) from error
        if not isinstance(contenido, dict) or not isinstance(
            contenido.get("value"), (str, int)
        ):
            raise BonitaRespuestaInvalidaError("Falta la correlación de la actividad.")
        return str(contenido["value"])

    def actividad_completada(self, tarea_id: int, case_id: int) -> bool:
        """Reconcilia por ID fuente y caso; otra instancia completada no sirve."""
        return any(
            t.source_object_id == tarea_id and t.state == "completed"
            for t in self.obtener_historial_tareas(case_id)
        )

    def _obtener_usuario(self, nombre_usuario: str) -> UsuarioBonita:
        respuesta = self._enviar(
            "GET",
            "/API/identity/user",
            params=[("p", 0), ("c", 2), ("f", f"userName={nombre_usuario}")],
            estados_esperados=(httpx.codes.OK,),
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
        json: dict[str, JsonValue] | None = None,
        estados_esperados: tuple[int, ...],
        resultado_puede_ser_ambiguo: bool = False,
    ) -> httpx.Response:
        """Envía una petición autenticada y traduce los fallos de transporte.

        Un 401 garantiza que Bonita no procesó la operación, por lo que se
        renueva la sesión y se repite una sola vez. Las operaciones no
        idempotentes distinguen los fallos que dejan un resultado incierto.
        """

        token = self._token_vigente()
        respuesta = self._transportar(
            metodo,
            ruta,
            params,
            json,
            token,
            resultado_puede_ser_ambiguo,
        )
        if respuesta.status_code == httpx.codes.UNAUTHORIZED:
            token = self._token_vigente(rechazado=token)
            respuesta = self._transportar(
                metodo,
                ruta,
                params,
                json,
                token,
                resultado_puede_ser_ambiguo,
            )

        if respuesta.status_code in estados_esperados:
            return respuesta
        operacion = f"{metodo} {ruta}"
        if respuesta.is_success:
            estados = " o ".join(str(estado) for estado in estados_esperados)
            raise BonitaRespuestaInvalidaError(
                f"{operacion}: Bonita respondió HTTP {respuesta.status_code}; "
                f"se esperaba HTTP {estados}."
            )
        if respuesta.status_code == httpx.codes.UNAUTHORIZED:
            raise BonitaCredencialesError(
                f"{operacion}: Bonita rechazó la sesión renovada."
            )
        if (
            respuesta.status_code == httpx.codes.REQUEST_TIMEOUT
            or respuesta.status_code >= httpx.codes.INTERNAL_SERVER_ERROR
        ):
            error = (
                BonitaResultadoDesconocidoError
                if resultado_puede_ser_ambiguo
                else BonitaNoDisponibleError
            )
            raise error(f"{operacion}: Bonita respondió HTTP {respuesta.status_code}.")
        detalle = _leer_error(respuesta)
        raise BonitaOperacionRechazadaError(
            f"{operacion}: Bonita respondió HTTP {respuesta.status_code}.",
            tuple(texto for texto in detalle.explanations if texto),
        )

    def _transportar(
        self,
        metodo: str,
        ruta: str,
        params: Parametros | None,
        json: dict[str, JsonValue] | None,
        token: str,
        resultado_puede_ser_ambiguo: bool,
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
                if resultado_puede_ser_ambiguo
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
