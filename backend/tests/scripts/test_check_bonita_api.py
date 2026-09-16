"""Pruebas del verificador manual de la API de Bonita."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.scripts.check_bonita_api import (
    BonitaCheckError,
    CheckConfig,
    check_bonita_api,
)

BASE_URL = "http://bonita:8080/bonita"


def _config() -> CheckConfig:
    """Crea una configuración determinista para las pruebas HTTP."""

    return CheckConfig(
        base_url=BASE_URL,
        username="install",
        password="install",
        process_name="RescueSync",
        process_version="1.1",
        timeout_seconds=5.0,
    )


def _process_payload(
    *,
    activation_state: str = "ENABLED",
    configuration_state: str = "RESOLVED",
) -> dict[str, str]:
    """Devuelve una definición mínima con los estados indicados."""

    return {
        "id": "123",
        "name": "RescueSync",
        "version": "1.1",
        "activationState": activation_state,
        "configurationState": configuration_state,
    }


def test_confirma_login_csrf_y_proceso_listo() -> None:
    config = _config()

    with respx.mock(assert_all_called=True) as router:
        router.post(f"{BASE_URL}/loginservice").mock(
            return_value=httpx.Response(
                204,
                headers={"set-cookie": "X-Bonita-API-Token=csrf-token; Path=/bonita"},
            )
        )
        process_route = router.get(f"{BASE_URL}/API/bpm/process").mock(
            return_value=httpx.Response(200, json=[_process_payload()])
        )

        with httpx.Client() as client:
            process = check_bonita_api(client, config)

    assert process.id == "123"
    request = process_route.calls.last.request
    assert request.headers["X-Bonita-API-Token"] == "csrf-token"
    assert request.url.params.get_list("f") == ["name=RescueSync", "version=1.1"]


def test_informa_credenciales_rechazadas_sin_exponerlas() -> None:
    config = _config()

    with respx.mock(assert_all_called=True) as router:
        router.post(f"{BASE_URL}/loginservice").mock(return_value=httpx.Response(401))

        with (
            httpx.Client() as client,
            pytest.raises(BonitaCheckError, match="rechazó las credenciales"),
        ):
            check_bonita_api(client, config)


@pytest.mark.parametrize(
    ("activation_state", "configuration_state", "expected_message"),
    [
        ("DISABLED", "RESOLVED", "no ENABLED"),
        ("DISABLED", "UNRESOLVED", "no RESOLVED"),
    ],
)
def test_rechaza_un_proceso_que_no_esta_listo(
    activation_state: str,
    configuration_state: str,
    expected_message: str,
) -> None:
    config = _config()

    with respx.mock(assert_all_called=True) as router:
        router.post(f"{BASE_URL}/loginservice").mock(
            return_value=httpx.Response(
                204,
                headers={"set-cookie": "X-Bonita-API-Token=csrf-token; Path=/bonita"},
            )
        )
        router.get(f"{BASE_URL}/API/bpm/process").mock(
            return_value=httpx.Response(
                200,
                json=[
                    _process_payload(
                        activation_state=activation_state,
                        configuration_state=configuration_state,
                    )
                ],
            )
        )

        with (
            httpx.Client() as client,
            pytest.raises(BonitaCheckError, match=expected_message),
        ):
            check_bonita_api(client, config)
