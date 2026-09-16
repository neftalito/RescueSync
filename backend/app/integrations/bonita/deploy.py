"""Instala y habilita el proceso de RescueSync en Bonita."""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import httpx

LOGGER = logging.getLogger("bonita-deploy")


class DeploymentError(RuntimeError):
    """Representa un fallo controlado durante el despliegue en Bonita."""


@dataclass(frozen=True)
class Config:
    """Contiene la configuración necesaria para desplegar el proceso."""

    base_url: str
    username: str
    password: str
    actor_password: str
    process_name: str
    process_version: str
    process_parameters: tuple[tuple[str, str], ...]
    bar_path: Path
    bos_path: Path | None
    organization_group: str | None
    startup_timeout_seconds: int
    request_timeout_seconds: float

    @classmethod
    def from_environment(cls) -> Config:
        """Construye la configuración desde variables de entorno."""

        bos_path_value = os.getenv("BONITA_BOS_PATH", "").strip()
        organization_group = os.getenv("BONITA_ORGANIZATION_GROUP", "").strip()

        return cls(
            base_url=_required_environment("BONITA_BASE_URL").rstrip("/"),
            username=_required_environment("BONITA_USERNAME"),
            password=_required_environment("BONITA_PASSWORD"),
            actor_password=os.getenv("BONITA_ACTOR_PASSWORD", "").strip()
            or secrets.token_urlsafe(32),
            process_name=_required_environment("BONITA_PROCESS_NAME"),
            process_version=_required_environment("BONITA_PROCESS_VERSION"),
            process_parameters=(
                (
                    "backendBaseUrl",
                    os.getenv("BONITA_BACKEND_BASE_URL", "http://backend:8000").rstrip(
                        "/"
                    ),
                ),
                (
                    "nationalApiBaseUrl",
                    os.getenv(
                        "BONITA_NATIONAL_API_BASE_URL", "http://national-api:8000"
                    ).rstrip("/"),
                ),
                (
                    "ventanaOfertasMs",
                    str(
                        _positive_integer_environment(
                            "BONITA_OFFER_WINDOW_MS", 7_200_000
                        )
                    ),
                ),
                (
                    "connectTimeoutMs",
                    str(
                        _positive_integer_environment(
                            "BONITA_CONNECT_TIMEOUT_MS", 5_000
                        )
                    ),
                ),
                (
                    "readTimeoutMs",
                    str(
                        _positive_integer_environment("BONITA_READ_TIMEOUT_MS", 30_000)
                    ),
                ),
            ),
            bar_path=Path(_required_environment("BONITA_BAR_PATH")),
            bos_path=Path(bos_path_value) if bos_path_value else None,
            organization_group=organization_group or None,
            startup_timeout_seconds=int(
                os.getenv("BONITA_STARTUP_TIMEOUT_SECONDS", "300")
            ),
            request_timeout_seconds=float(
                os.getenv("BONITA_REQUEST_TIMEOUT_SECONDS", "30")
            ),
        )


@dataclass(frozen=True)
class ProcessDefinition:
    """Representa una definición de proceso devuelta por Bonita."""

    id: str
    name: str
    version: str
    activation_state: str
    configuration_state: str

    @classmethod
    def from_object(cls, value: object) -> ProcessDefinition:
        """Valida los campos necesarios de una definición externa."""

        if not isinstance(value, dict):
            raise DeploymentError("Bonita devolvió una definición de proceso inválida.")

        fields = {
            "id": value.get("id"),
            "name": value.get("name"),
            "version": value.get("version"),
            "activationState": value.get("activationState"),
            "configurationState": value.get("configurationState"),
        }
        for field_name, field_value in fields.items():
            if not isinstance(field_value, str):
                raise DeploymentError(
                    f"Bonita no devolvió el campo textual {field_name!r}."
                )

        return cls(
            id=fields["id"],
            name=fields["name"],
            version=fields["version"],
            activation_state=fields["activationState"],
            configuration_state=fields["configurationState"],
        )


def _required_environment(name: str) -> str:
    """Obtiene una variable obligatoria sin revelar su contenido."""

    value = os.getenv(name, "").strip()
    if not value:
        raise DeploymentError(f"La variable de entorno {name} es obligatoria.")
    return value


def _positive_integer_environment(name: str, default: int) -> int:
    """Obtiene un entero positivo desde el entorno."""

    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise DeploymentError(f"La variable de entorno {name} debe ser positiva.")
    return value


def _ensure_success(
    response: httpx.Response,
    operation: str,
    expected_statuses: set[int],
) -> None:
    """Valida el código HTTP de una operación contra Bonita."""

    if response.status_code in expected_statuses:
        return
    raise DeploymentError(
        f"{operation} falló: Bonita respondió HTTP "
        f"{response.status_code} {response.reason_phrase}."
    )


def _decode_json(response: httpx.Response, operation: str) -> object:
    """Decodifica una respuesta JSON y traduce errores de formato."""

    try:
        return json.loads(response.text)
    except json.JSONDecodeError as error:
        raise DeploymentError(
            f"Bonita devolvió una respuesta no JSON durante {operation}."
        ) from error


def _csrf_token(client: httpx.Client) -> str:
    """Extrae el token CSRF establecido al iniciar sesión."""

    for cookie in client.cookies.jar:
        if cookie.name == "X-Bonita-API-Token":
            return cookie.value
    raise DeploymentError(
        "Bonita inició la sesión pero no devolvió X-Bonita-API-Token."
    )


def login_when_ready(client: httpx.Client, config: Config) -> None:
    """Espera al Runtime e inicia una sesión administrativa."""

    deadline = time.monotonic() + config.startup_timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = client.post(
                f"{config.base_url}/loginservice",
                data={
                    "username": config.username,
                    "password": config.password,
                    "redirect": "false",
                },
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
            LOGGER.info("Bonita todavía no está disponible; reintentando...")
            time.sleep(3)
            continue

        if response.status_code in {200, 204}:
            client.headers["X-Bonita-API-Token"] = _csrf_token(client)
            LOGGER.info("Sesión administrativa iniciada en Bonita.")
            return
        if response.status_code in {401, 403}:
            raise DeploymentError("Bonita rechazó las credenciales de despliegue.")

        LOGGER.info(
            "Bonita respondió HTTP %s durante el arranque; reintentando...",
            response.status_code,
        )
        time.sleep(3)

    raise DeploymentError(
        "Bonita no estuvo disponible antes de finalizar el tiempo de espera."
    )


def _organization_exists(client: httpx.Client, config: Config) -> bool:
    """Comprueba si existe el grupo raíz requerido por los actores."""

    if config.organization_group is None:
        return True

    response = client.get(
        f"{config.base_url}/API/identity/group",
        params=[
            ("p", "0"),
            ("c", "1"),
            ("f", f"name={config.organization_group}"),
        ],
    )
    _ensure_success(response, "La consulta de la organización", {200})
    payload = _decode_json(response, "la consulta de la organización")
    if not isinstance(payload, list):
        raise DeploymentError(
            "Bonita devolvió una respuesta inválida al consultar la organización."
        )
    return bool(payload)


def _organization_from_bos(bos_path: Path) -> tuple[str, bytes]:
    """Extrae la única organización incluida en un proyecto BOS."""

    if not bos_path.is_file():
        raise DeploymentError(f"No se encontró el archivo BOS en {bos_path}.")

    try:
        with ZipFile(bos_path) as archive:
            candidates = [
                name
                for name in archive.namelist()
                if "/app/organizations/" in name and name.endswith(".xml")
            ]
            if len(candidates) != 1:
                raise DeploymentError(
                    "El BOS debe contener exactamente una organización XML."
                )
            name = candidates[0]
            return Path(name).name, archive.read(name)
    except BadZipFile as error:
        raise DeploymentError(f"El archivo {bos_path} no es un BOS válido.") from error


def ensure_organization(client: httpx.Client, config: Config) -> None:
    """Importa desde el BOS la organización requerida cuando todavía no existe."""

    if _organization_exists(client, config):
        LOGGER.info("La organización requerida ya está disponible en Bonita.")
        return
    if config.bos_path is None:
        raise DeploymentError(
            "Falta BONITA_BOS_PATH para importar la organización requerida."
        )

    file_name, content = _organization_from_bos(config.bos_path)
    response = client.post(
        f"{config.base_url}/portal/organizationUpload",
        files={"file": (file_name, BytesIO(content), "application/xml")},
    )
    _ensure_success(response, "La subida de la organización", {200})

    temporary_name = response.text.strip().strip('"')
    if not temporary_name:
        raise DeploymentError(
            "Bonita no devolvió el nombre temporal de la organización."
        )

    import_response = client.post(
        f"{config.base_url}/services/organization/import",
        data={
            "organizationDataUpload": temporary_name,
            "importPolicy": "MERGE_DUPLICATES",
        },
    )
    _ensure_success(import_response, "La importación de la organización", {200})

    if not _organization_exists(client, config):
        raise DeploymentError(
            "Bonita aceptó la organización pero no creó el grupo requerido."
        )
    LOGGER.info("Organización %s importada en Bonita.", file_name)


def _resolve_bar_path(path: Path) -> Path:
    """Resuelve un archivo BAR explícito o el único BAR de un directorio."""

    if path.is_file():
        candidates = [path]
    elif path.is_dir():
        candidates = sorted(path.glob("*.bar"))
    else:
        raise DeploymentError(f"No se encontró la ruta de despliegue {path}.")

    if len(candidates) != 1:
        raise DeploymentError(
            f"Se esperaba exactamente un archivo .bar en {path}; "
            f"se encontraron {len(candidates)}."
        )
    if candidates[0].suffix.casefold() != ".bar":
        raise DeploymentError(f"El archivo {candidates[0]} no tiene extensión .bar.")
    return candidates[0]


def _actor_usernames_from_bar(bar_path: Path) -> tuple[str, ...]:
    """Extrae los usuarios asignados directamente a actores dentro del BAR."""

    try:
        with ZipFile(bar_path) as archive:
            actor_mapping = archive.read("actorMapping.xml")
    except KeyError as error:
        raise DeploymentError("El BAR no contiene actorMapping.xml.") from error
    except BadZipFile as error:
        raise DeploymentError(f"El archivo {bar_path} no es un BAR válido.") from error

    try:
        root = ElementTree.fromstring(actor_mapping)
    except ElementTree.ParseError as error:
        raise DeploymentError("El actorMapping.xml del BAR no es válido.") from error

    usernames = {
        username
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "user"
        and (username := (element.text or "").strip())
    }
    return tuple(sorted(usernames))


def _user_exists(client: httpx.Client, config: Config, username: str) -> bool:
    """Comprueba si un usuario de actores ya existe en Bonita."""

    response = client.get(
        f"{config.base_url}/API/identity/user",
        params=[("p", "0"), ("c", "2"), ("f", f"userName={username}")],
    )
    _ensure_success(response, f"La consulta del usuario {username}", {200})
    payload = _decode_json(response, f"la consulta del usuario {username}")
    if not isinstance(payload, list):
        raise DeploymentError(
            f"Bonita devolvió una respuesta inválida para el usuario {username}."
        )
    return any(
        isinstance(user, dict) and user.get("userName") == username for user in payload
    )


def ensure_actor_users(
    client: httpx.Client,
    config: Config,
    bar_path: Path,
) -> None:
    """Crea los usuarios referenciados por los mapeos de actores del BAR."""

    missing = [
        username
        for username in _actor_usernames_from_bar(bar_path)
        if not _user_exists(client, config, username)
    ]
    if not missing:
        LOGGER.info("Los usuarios requeridos por los actores ya existen en Bonita.")
        return
    for username in missing:
        name_parts = username.replace("_", ".").split(".")
        first_name = name_parts[0].capitalize()
        last_name = (
            " ".join(part.capitalize() for part in name_parts[1:]) or "RescueSync"
        )
        response = client.post(
            f"{config.base_url}/API/identity/user",
            json={
                "userName": username,
                "password": config.actor_password,
                "password_confirm": config.actor_password,
                "firstname": first_name,
                "lastname": last_name,
                "enabled": "true",
            },
        )
        _ensure_success(response, f"La creación del usuario {username}", {200, 201})
        LOGGER.info("Usuario de actor %s creado en Bonita.", username)


def find_process(
    client: httpx.Client,
    config: Config,
) -> ProcessDefinition | None:
    """Busca el proceso por nombre y versión exactos."""

    response = client.get(
        f"{config.base_url}/API/bpm/process",
        params=[
            ("p", "0"),
            ("c", "10"),
            ("f", f"name={config.process_name}"),
            ("f", f"version={config.process_version}"),
        ],
    )
    _ensure_success(response, "La búsqueda del proceso", {200})
    payload = _decode_json(response, "la búsqueda del proceso")
    if not isinstance(payload, list):
        raise DeploymentError(
            "Bonita devolvió una respuesta inválida al buscar el proceso."
        )

    matches = [
        process
        for item in payload
        if (process := ProcessDefinition.from_object(item)).name == config.process_name
        and process.version == config.process_version
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise DeploymentError(
            "Bonita devolvió más de un proceso para el mismo nombre y versión."
        )
    return matches[0]


def install_process(client: httpx.Client, config: Config) -> ProcessDefinition:
    """Sube el BAR y crea la definición de proceso en Bonita."""

    bar_path = _resolve_bar_path(config.bar_path)
    bar_content = _configured_bar_content(bar_path, config.process_parameters)
    upload_response = client.post(
        f"{config.base_url}/portal/processUpload",
        files={
            "file": (
                bar_path.name,
                bar_content,
                "application/octet-stream",
            )
        },
    )
    _ensure_success(upload_response, "La subida del archivo BAR", {200})

    temporary_name = upload_response.text.strip().strip('"')
    if not temporary_name:
        raise DeploymentError("Bonita no devolvió el nombre temporal del archivo BAR.")

    install_response = client.post(
        f"{config.base_url}/API/bpm/process",
        json={"fileupload": temporary_name},
    )
    _ensure_success(install_response, "La instalación del proceso", {200, 201})
    process = ProcessDefinition.from_object(
        _decode_json(install_response, "la instalación del proceso")
    )
    if process.name != config.process_name or process.version != config.process_version:
        raise DeploymentError(
            "El BAR instalado no coincide con BONITA_PROCESS_NAME y "
            "BONITA_PROCESS_VERSION."
        )

    LOGGER.info(
        "Proceso %s:%s instalado con ID %s.",
        process.name,
        process.version,
        process.id,
    )
    return process


def _configured_bar_content(
    bar_path: Path,
    parameters: tuple[tuple[str, str], ...],
) -> BytesIO:
    """Crea en memoria un BAR con los parámetros del entorno actual."""

    result = BytesIO()
    try:
        with ZipFile(bar_path) as source, ZipFile(result, "w") as target:
            entries = source.infolist()
            if not any(entry.filename == "parameters.properties" for entry in entries):
                raise DeploymentError("El BAR no contiene parameters.properties.")

            parameter_content = "".join(
                f"{name}={value}\n" for name, value in parameters
            ).encode("iso-8859-1")
            for entry in entries:
                content = (
                    parameter_content
                    if entry.filename == "parameters.properties"
                    else source.read(entry.filename)
                )
                target.writestr(entry, content)
    except BadZipFile as error:
        raise DeploymentError(f"El archivo {bar_path} no es un BAR válido.") from error

    result.seek(0)
    return result


def _resolution_problems(
    client: httpx.Client,
    config: Config,
    process: ProcessDefinition,
) -> tuple[str, ...]:
    """Obtiene los motivos seguros por los que un proceso no está resuelto."""

    response = client.get(
        f"{config.base_url}/API/bpm/processResolutionProblem",
        params=[("p", "0"), ("c", "100"), ("f", f"process_id={process.id}")],
    )
    _ensure_success(response, "La consulta de problemas del proceso", {200})
    payload = _decode_json(response, "la consulta de problemas del proceso")
    if not isinstance(payload, list):
        raise DeploymentError(
            "Bonita devolvió una respuesta inválida para los problemas del proceso."
        )

    return tuple(
        message
        for item in payload
        if isinstance(item, dict)
        and isinstance((message := item.get("message")), str)
        and message
    )


def enable_process(
    client: httpx.Client,
    config: Config,
    process: ProcessDefinition,
) -> None:
    """Habilita un proceso instalado y correctamente resuelto."""

    if process.activation_state == "ENABLED":
        LOGGER.info(
            "El proceso %s:%s ya está habilitado.",
            process.name,
            process.version,
        )
        return
    if process.configuration_state != "RESOLVED":
        details = _resolution_problems(client, config, process)
        suffix = f" Motivos: {'; '.join(details)}" if details else ""
        raise DeploymentError(
            f"El proceso {process.name}:{process.version} está sin resolver; "
            "revisá actores, parámetros, conectores, formularios y BDM." + suffix
        )

    response = client.put(
        f"{config.base_url}/API/bpm/process/{process.id}",
        json={"activationState": "ENABLED"},
    )
    _ensure_success(response, "La habilitación del proceso", {200})
    LOGGER.info(
        "Proceso %s:%s habilitado con ID %s.",
        process.name,
        process.version,
        process.id,
    )


def deploy(config: Config) -> None:
    """Instala y habilita el proceso cuando todavía no está desplegado."""

    bar_path = _resolve_bar_path(config.bar_path)
    with httpx.Client(
        timeout=config.request_timeout_seconds,
        follow_redirects=False,
        headers={"Accept": "application/json"},
    ) as client:
        login_when_ready(client, config)
        ensure_organization(client, config)
        ensure_actor_users(client, config, bar_path)
        process = find_process(client, config)
        if process is None:
            LOGGER.info(
                "El proceso %s:%s no existe; instalando el BAR...",
                config.process_name,
                config.process_version,
            )
            process = install_process(client, config)
        else:
            LOGGER.info(
                "El proceso %s:%s ya está instalado con ID %s.",
                process.name,
                process.version,
                process.id,
            )
        enable_process(client, config, process)


def main() -> int:
    """Ejecuta el despliegue y devuelve un código apto para Compose."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        deploy(Config.from_environment())
    except (DeploymentError, httpx.HTTPError, OSError, ValueError) as error:
        LOGGER.error("No se pudo desplegar el proceso: %s", error)
        return 1

    LOGGER.info("Despliegue de Bonita finalizado correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
