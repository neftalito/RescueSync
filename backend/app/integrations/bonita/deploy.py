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

from app.integrations.bonita.contratos import (
    PARAMETRO_CALLBACK_TOKEN,
)

LOGGER = logging.getLogger("bonita-deploy")

SECRET_PARAMETERS = frozenset(
    {PARAMETRO_CALLBACK_TOKEN, "nationalApiPassword", "nationalApiUser"}
)
"""Parámetros cuyo valor nunca se registra ni se incluye en errores."""

MINIMUM_CALLBACK_TOKEN_LENGTH = 32


class DeploymentError(RuntimeError):
    """Representa un fallo controlado durante el despliegue en Bonita."""


@dataclass(frozen=True)
class Config:
    """Contiene la configuración necesaria para desplegar el proceso."""

    base_url: str
    username: str
    password: str
    admin_username: str
    admin_initial_password: str
    actor_password: str
    process_name: str
    process_version: str
    process_parameters: tuple[tuple[str, str], ...]
    """Parámetros inyectados en el BAR. Solo se aplican al instalar."""
    bar_path: Path
    startup_timeout_seconds: int
    request_timeout_seconds: float

    @classmethod
    def from_environment(cls) -> Config:
        """Construye la configuración desde variables de entorno."""

        return cls(
            base_url=_required_environment("BONITA_BASE_URL").rstrip("/"),
            username=_required_environment("BONITA_USERNAME"),
            password=_required_environment("BONITA_PASSWORD"),
            admin_username=_required_environment("ADMIN_EMAIL").lower(),
            admin_initial_password=_required_secret_environment(
                "ADMIN_INITIAL_PASSWORD"
            ),
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
                (PARAMETRO_CALLBACK_TOKEN, _callback_token_environment()),
            )
            + (
                (
                    (
                        "nationalApiUser",
                        _required_environment("BONITA_NATIONAL_API_LOGIN"),
                    ),
                    (
                        "nationalApiPassword",
                        _required_secret_environment("BONITA_NATIONAL_API_PASSWORD"),
                    ),
                    (
                        "maxReintentosIntegracion",
                        str(
                            _positive_integer_environment(
                                "BONITA_MAX_REINTENTOS_INTEGRACION", 3
                            )
                        ),
                    ),
                )
                if os.getenv("BONITA_PROCESS_VERSION") in {"1.5"}
                else ()
            ),
            bar_path=Path(_required_environment("BONITA_BAR_PATH")),
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


@dataclass(frozen=True)
class IdentityUser:
    """Representa una identidad de usuario devuelta por Bonita."""

    id: str
    username: str

    @classmethod
    def from_object(cls, value: object) -> IdentityUser:
        """Valida los campos usados para reconciliar una cuenta."""

        if not isinstance(value, dict):
            raise DeploymentError("Bonita devolvió un usuario inválido.")
        username = value.get("userName")
        if not isinstance(username, str) or not username:
            raise DeploymentError("Bonita no devolvió un userName válido.")
        return cls(id=_external_id(value.get("id"), "usuario"), username=username)


@dataclass(frozen=True)
class Profile:
    """Representa un perfil que concede acceso a una aplicación de Bonita."""

    id: str
    name: str

    @classmethod
    def from_object(cls, value: object) -> Profile:
        """Valida los campos usados para asignar el perfil."""

        if not isinstance(value, dict):
            raise DeploymentError("Bonita devolvió un perfil inválido.")
        name = value.get("name")
        if not isinstance(name, str) or not name:
            raise DeploymentError("Bonita no devolvió un nombre de perfil válido.")
        return cls(id=_external_id(value.get("id"), "perfil"), name=name)


def _required_environment(name: str) -> str:
    """Obtiene una variable obligatoria sin revelar su contenido."""

    value = os.getenv(name, "").strip()
    if not value:
        raise DeploymentError(f"La variable de entorno {name} es obligatoria.")
    return value


def _required_secret_environment(name: str) -> str:
    """Obtiene un secreto obligatorio sin modificarlo ni revelar su contenido."""

    value = os.getenv(name)
    if value is None or not value:
        raise DeploymentError(f"La variable de entorno {name} es obligatoria.")
    return value


def _external_id(value: object, resource: str) -> str:
    """Normaliza un identificador positivo serializado como texto o entero."""

    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return str(value)
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return value
    raise DeploymentError(f"Bonita devolvió un identificador de {resource} inválido.")


def _callback_token_environment() -> str:
    """Obtiene el token compartido con FastAPI sin revelar su contenido."""

    token = _required_environment("BONITA_CALLBACK_TOKEN")
    if len(token) < MINIMUM_CALLBACK_TOKEN_LENGTH:
        raise DeploymentError(
            "BONITA_CALLBACK_TOKEN debe tener al menos "
            f"{MINIMUM_CALLBACK_TOKEN_LENGTH} caracteres."
        )
    return token


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


def ensure_bar_matches_contract(bar_path: Path, config: Config) -> None:
    """Verifica que el BAR sea la versión para la que se escribió el backend.

    Evita instalar un artefacto cuyo contrato no coincide con `contratos.py`.
    """

    try:
        with ZipFile(bar_path) as archive:
            design = archive.read("process-design.xml")
    except KeyError as error:
        raise DeploymentError("El BAR no contiene process-design.xml.") from error
    except BadZipFile as error:
        raise DeploymentError(f"El archivo {bar_path} no es un BAR válido.") from error

    try:
        root = ElementTree.fromstring(design)
    except ElementTree.ParseError as error:
        raise DeploymentError("El process-design.xml del BAR no es válido.") from error

    found = f"{root.get('name')}:{root.get('version')}"
    expected = f"{config.process_name}:{config.process_version}"
    if found != expected:
        raise DeploymentError(
            f"El BAR {bar_path.name} contiene {found}, pero el backend espera "
            f"{expected}. Actualizá docs/ y app/integrations/bonita/contratos.py "
            "en el mismo cambio."
        )


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


def _find_admin_user(client: httpx.Client, config: Config) -> IdentityUser | None:
    """Busca la cuenta administrativa inicial por su nombre exacto."""

    response = client.get(
        f"{config.base_url}/API/identity/user",
        params=[
            ("p", "0"),
            ("c", "2"),
            ("f", f"userName={config.admin_username}"),
        ],
    )
    _ensure_success(response, "La consulta del administrador inicial", {200})
    payload = _decode_json(response, "la consulta del administrador inicial")
    if not isinstance(payload, list):
        raise DeploymentError(
            "Bonita devolvió una respuesta inválida para el administrador inicial."
        )
    matches = [
        user
        for item in payload
        if (user := IdentityUser.from_object(item)).username == config.admin_username
    ]
    if len(matches) > 1:
        raise DeploymentError("Bonita devolvió más de un usuario para ADMIN_EMAIL.")
    return matches[0] if matches else None


def _find_administrator_profile(client: httpx.Client, config: Config) -> Profile:
    """Resuelve el perfil predeterminado que habilita la aplicación administrativa."""

    profile_name = "Administrator"
    response = client.get(
        f"{config.base_url}/API/portal/profile",
        params=[("p", "0"), ("c", "2"), ("f", f"name={profile_name}")],
    )
    _ensure_success(response, "La consulta del perfil Administrator", {200})
    payload = _decode_json(response, "la consulta del perfil Administrator")
    if not isinstance(payload, list):
        raise DeploymentError(
            "Bonita devolvió una respuesta inválida para el perfil Administrator."
        )
    matches = [
        profile
        for item in payload
        if (profile := Profile.from_object(item)).name == profile_name
    ]
    if len(matches) != 1:
        raise DeploymentError("Bonita no devolvió un único perfil Administrator.")
    return matches[0]


def _admin_has_profile(
    client: httpx.Client,
    config: Config,
    user: IdentityUser,
    profile: Profile,
) -> bool:
    """Comprueba la membresía directa sin confiar solo en una lectura previa."""

    response = client.get(
        f"{config.base_url}/API/portal/profileMember",
        params=[
            ("p", "0"),
            ("c", "2"),
            ("f", "member_type=user"),
            ("f", f"profile_id={profile.id}"),
            ("f", f"user_id={user.id}"),
        ],
    )
    _ensure_success(response, "La consulta del perfil del administrador", {200})
    payload = _decode_json(response, "la consulta del perfil del administrador")
    if not isinstance(payload, list):
        raise DeploymentError(
            "Bonita devolvió una respuesta inválida para la membresía administrativa."
        )
    if len(payload) > 1:
        raise DeploymentError(
            "Bonita devolvió más de una membresía administrativa para ADMIN_EMAIL."
        )
    if not payload:
        return False
    membership = payload[0]
    if not isinstance(membership, dict):
        raise DeploymentError("Bonita devolvió una membresía administrativa inválida.")
    return (
        _external_id(membership.get("profile_id"), "perfil de la membresía")
        == profile.id
        and _external_id(membership.get("user_id"), "usuario de la membresía")
        == user.id
    )


def _admin_credentials_match(config: Config) -> bool:
    """Verifica una cuenta preexistente antes de elevarla a Administrator."""

    try:
        with httpx.Client(
            timeout=config.request_timeout_seconds,
            follow_redirects=False,
        ) as verifier:
            response = verifier.post(
                f"{config.base_url}/loginservice",
                data={
                    "username": config.admin_username,
                    "password": config.admin_initial_password,
                    "redirect": "false",
                },
            )
    except httpx.HTTPError as error:
        raise DeploymentError(
            "No se pudieron verificar las credenciales del administrador preexistente."
        ) from error
    if response.status_code in {200, 204}:
        return True
    if response.status_code in {401, 403}:
        return False
    raise DeploymentError(
        "La verificación del administrador preexistente falló: Bonita respondió "
        f"HTTP {response.status_code} {response.reason_phrase}."
    )


def ensure_initial_admin(client: httpx.Client, config: Config) -> None:
    """Crea el administrador inicial y le asigna el perfil Administrator.

    Una cuenta ya mapeada no se modifica para no restablecer una contraseña que
    el administrador haya cambiado. Si el nombre existe pero aún no posee el
    perfil, las credenciales compartidas se verifican antes de elevarlo.
    """

    profile = _find_administrator_profile(client, config)
    user = _find_admin_user(client, config)
    created = user is None
    if created:
        response = client.post(
            f"{config.base_url}/API/identity/user",
            json={
                "userName": config.admin_username,
                "password": config.admin_initial_password,
                "password_confirm": config.admin_initial_password,
                "firstname": "Administrador",
                "lastname": "RescueSync",
                "enabled": "true",
            },
        )
        _ensure_success(response, "La creación del administrador inicial", {200, 201})
        user = IdentityUser.from_object(
            _decode_json(response, "la creación del administrador inicial")
        )
        if user.username != config.admin_username:
            raise DeploymentError("Bonita creó una cuenta distinta de ADMIN_EMAIL.")

    if _admin_has_profile(client, config, user, profile):
        LOGGER.info("El administrador inicial ya existe y tiene su perfil en Bonita.")
        return
    if not created and not _admin_credentials_match(config):
        raise DeploymentError(
            "ADMIN_EMAIL ya existe en Bonita con otras credenciales y no tiene el "
            "perfil Administrator; no se modificó la cuenta."
        )

    response = client.post(
        f"{config.base_url}/API/portal/profileMember",
        json={
            "profile_id": profile.id,
            "member_type": "USER",
            "user_id": user.id,
        },
    )
    _ensure_success(response, "La asignación del perfil Administrator", {200, 201})
    LOGGER.info("Administrador inicial creado y habilitado en Bonita.")


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
            f"Bonita instaló {process.name}:{process.version} en lugar de "
            f"{config.process_name}:{config.process_version}."
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


def _count(
    client: httpx.Client,
    config: Config,
    resource: str,
    process: ProcessDefinition,
) -> int:
    """Cuenta casos de una definición usando la cabecera Content-Range."""

    response = client.get(
        f"{config.base_url}/API/bpm/{resource}",
        params=[("p", "0"), ("c", "1"), ("f", f"processDefinitionId={process.id}")],
    )
    _ensure_success(response, f"La consulta de {resource}", {200})
    content_range = response.headers.get("Content-Range", "")
    total = content_range.rpartition("/")[2]
    if not total.isdigit():
        raise DeploymentError(f"Bonita no informó la cantidad de {resource}.")
    return int(total)


def remove_unusable_process(
    client: httpx.Client,
    config: Config,
    process: ProcessDefinition,
) -> bool:
    """Elimina una definición que nunca pudo habilitarse para reinstalarla.

    Bonita Community no permite corregir parámetros de un proceso instalado.
    Solo se elimina si está deshabilitada, sin resolver y sin casos, por lo que
    no se pierde información.
    """

    if process.activation_state != "DISABLED" or process.configuration_state == (
        "RESOLVED"
    ):
        return False
    if _count(client, config, "case", process) or _count(
        client, config, "archivedCase", process
    ):
        return False

    details = _resolution_problems(client, config, process)
    response = client.delete(f"{config.base_url}/API/bpm/process/{process.id}")
    _ensure_success(response, "La eliminación del proceso sin resolver", {200, 204})
    LOGGER.warning(
        "Se eliminó %s:%s sin resolver y sin casos para reinstalarlo. Motivos: %s",
        process.name,
        process.version,
        "; ".join(details) or "no informados",
    )
    return True


def installed_parameter_mismatches(
    client: httpx.Client,
    config: Config,
    process: ProcessDefinition,
) -> tuple[str, ...]:
    """Devuelve los nombres de parámetros instalados que difieren del entorno."""

    response = client.get(
        f"{config.base_url}/API/bpm/processParameter",
        params=[("p", "0"), ("c", "100"), ("f", f"process_id={process.id}")],
    )
    _ensure_success(response, "La consulta de parámetros del proceso", {200})
    payload = _decode_json(response, "la consulta de parámetros del proceso")
    if not isinstance(payload, list):
        raise DeploymentError(
            "Bonita devolvió una respuesta inválida para los parámetros del proceso."
        )

    installed = {
        name: value
        for item in payload
        if isinstance(item, dict)
        and isinstance((name := item.get("name")), str)
        and isinstance((value := item.get("value")), str)
    }
    return tuple(
        name
        for name, expected in config.process_parameters
        if installed.get(name) != expected
    )


def ensure_installed_parameters(
    client: httpx.Client,
    config: Config,
    process: ProcessDefinition,
) -> None:
    """Detecta un `.env` que ya no coincide con el proceso instalado.

    Un token distinto haría que FastAPI rechace todos los callbacks, por lo que
    detiene el despliegue. El resto de las diferencias solo se informa.
    """

    mismatches = installed_parameter_mismatches(client, config, process)
    secrets_changed = sorted(SECRET_PARAMETERS.intersection(mismatches))
    others = sorted(set(mismatches) - SECRET_PARAMETERS)
    if others:
        LOGGER.warning(
            "El proceso %s:%s instalado usa otros valores para %s. Los parámetros "
            "solo se aplican al instalar; para usar los del .env hay que "
            "recrear los volúmenes de Bonita.",
            process.name,
            process.version,
            ", ".join(others),
        )
    if secrets_changed:
        raise DeploymentError(
            f"El proceso {process.name}:{process.version} instalado usa otro "
            f"{', '.join(secrets_changed)} que el definido en BONITA_CALLBACK_TOKEN, "
            "y FastAPI rechazaría sus callbacks. Restaurá el valor anterior en .env "
            "o recreá los volúmenes de Bonita "
            "(ver docs/bonita/despliegue-y-operacion.md)."
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
    ensure_bar_matches_contract(bar_path, config)
    with httpx.Client(
        timeout=config.request_timeout_seconds,
        follow_redirects=False,
        headers={"Accept": "application/json"},
    ) as client:
        login_when_ready(client, config)
        ensure_initial_admin(client, config)
        ensure_actor_users(client, config, bar_path)
        process = find_process(client, config)
        if process is not None and remove_unusable_process(client, config, process):
            process = None
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
            ensure_installed_parameters(client, config, process)
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
