"""Comprueba el acceso a la API de Bonita y el proceso de RescueSync."""

from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass

import httpx


class BonitaCheckError(RuntimeError):
    """Representa una verificación fallida sin revelar datos sensibles."""


@dataclass(frozen=True)
class CheckConfig:
    """Contiene la configuración del Runtime y del proceso esperado."""

    base_url: str
    username: str
    password: str
    process_name: str
    process_version: str
    timeout_seconds: float

    @classmethod
    def from_environment(cls) -> CheckConfig:
        """Construye la configuración desde las variables compartidas del backend."""

        timeout_seconds = _positive_float_environment(
            "BONITA_REQUEST_TIMEOUT_SECONDS", 30.0
        )
        return cls(
            base_url=_required_environment("BONITA_BASE_URL").rstrip("/"),
            username=_required_environment("BONITA_USERNAME"),
            password=_required_environment("BONITA_PASSWORD"),
            process_name=os.getenv("BONITA_PROCESS_NAME", "RescueSync").strip()
            or "RescueSync",
            process_version=os.getenv("BONITA_PROCESS_VERSION", "1.1").strip() or "1.1",
            timeout_seconds=timeout_seconds,
        )


@dataclass(frozen=True)
class ProcessStatus:
    """Resume el estado relevante de una definición de proceso en Bonita."""

    id: str
    name: str
    version: str
    activation_state: str
    configuration_state: str

    @classmethod
    def from_object(cls, value: object) -> ProcessStatus:
        """Valida la forma mínima de una definición devuelta por Bonita."""

        if not isinstance(value, dict):
            raise BonitaCheckError(
                "Bonita devolvió una definición de proceso con formato inválido."
            )

        process_id = value.get("id")
        if isinstance(process_id, bool) or not isinstance(process_id, (int, str)):
            raise BonitaCheckError("Bonita devolvió un ID de proceso inválido.")

        fields = {
            "name": value.get("name"),
            "version": value.get("version"),
            "activationState": value.get("activationState"),
            "configurationState": value.get("configurationState"),
        }
        for field_name, field_value in fields.items():
            if not isinstance(field_value, str) or not field_value:
                raise BonitaCheckError(
                    f"Bonita no devolvió el campo textual {field_name!r}."
                )

        return cls(
            id=str(process_id),
            name=fields["name"],
            version=fields["version"],
            activation_state=fields["activationState"],
            configuration_state=fields["configurationState"],
        )


def _required_environment(name: str) -> str:
    """Obtiene una variable obligatoria sin incluir su valor en errores."""

    value = os.getenv(name, "").strip()
    if not value:
        raise BonitaCheckError(f"La variable de entorno {name} es obligatoria.")
    return value


def _positive_float_environment(name: str, default: float) -> float:
    """Obtiene un número positivo y finito desde el entorno."""

    raw_value = os.getenv(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as error:
        raise BonitaCheckError(f"La variable {name} debe ser numérica.") from error
    if not math.isfinite(value) or value <= 0:
        raise BonitaCheckError(f"La variable {name} debe ser positiva y finita.")
    return value


def _csrf_token(client: httpx.Client) -> str:
    """Extrae el token CSRF establecido por el servicio de autenticación."""

    for cookie in client.cookies.jar:
        if cookie.name == "X-Bonita-API-Token":
            return cookie.value
    raise BonitaCheckError(
        "El login respondió correctamente, pero Bonita no entregó el token CSRF."
    )


def _decode_processes(response: httpx.Response) -> list[object]:
    """Valida y decodifica la lista de definiciones de proceso."""

    try:
        payload = json.loads(response.text)
    except json.JSONDecodeError as error:
        raise BonitaCheckError(
            "Bonita devolvió una respuesta no JSON al consultar procesos."
        ) from error
    if not isinstance(payload, list):
        raise BonitaCheckError(
            "Bonita devolvió una respuesta inválida al consultar procesos."
        )
    return payload


def check_bonita_api(client: httpx.Client, config: CheckConfig) -> ProcessStatus:
    """Autentica contra Bonita y verifica que RescueSync esté listo para usarse."""

    login_response = client.post(
        f"{config.base_url}/loginservice",
        data={
            "username": config.username,
            "password": config.password,
            "redirect": "false",
        },
    )
    if login_response.status_code in {401, 403}:
        raise BonitaCheckError("Bonita rechazó las credenciales configuradas.")
    if login_response.status_code not in {200, 204}:
        raise BonitaCheckError(
            "El login de Bonita falló con HTTP "
            f"{login_response.status_code} {login_response.reason_phrase}."
        )

    client.headers["X-Bonita-API-Token"] = _csrf_token(client)
    process_response = client.get(
        f"{config.base_url}/API/bpm/process",
        params=[
            ("p", "0"),
            ("c", "10"),
            ("f", f"name={config.process_name}"),
            ("f", f"version={config.process_version}"),
        ],
    )
    if process_response.status_code != 200:
        raise BonitaCheckError(
            "La consulta de procesos falló con HTTP "
            f"{process_response.status_code} {process_response.reason_phrase}."
        )

    processes = _decode_processes(process_response)
    if len(processes) != 1:
        raise BonitaCheckError(
            "Se esperaba una única definición de "
            f"{config.process_name}:{config.process_version}; Bonita devolvió "
            f"{len(processes)}."
        )

    process = ProcessStatus.from_object(processes[0])
    if process.configuration_state != "RESOLVED":
        raise BonitaCheckError(
            f"El proceso está {process.configuration_state}, no RESOLVED."
        )
    if process.activation_state != "ENABLED":
        raise BonitaCheckError(
            f"El proceso está {process.activation_state}, no ENABLED."
        )
    return process


def main() -> int:
    """Ejecuta la verificación y comunica un resultado apto para scripts de shell."""

    try:
        config = CheckConfig.from_environment()
        with httpx.Client(timeout=config.timeout_seconds) as client:
            process = check_bonita_api(client, config)
    except (BonitaCheckError, httpx.RequestError) as error:
        print(f"[ERROR] La API de Bonita no está lista: {error}", file=sys.stderr)
        return 1

    print(f"[OK] Conexión y autenticación: {config.base_url}")
    print(
        "[OK] Proceso listo: "
        f"{process.name}:{process.version} (id={process.id}, "
        f"{process.configuration_state}, {process.activation_state})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
