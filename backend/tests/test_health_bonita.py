from collections.abc import Iterator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.dependencies import obtener_cliente_bonita
from app.integrations.bonita.cliente import ClienteBonita, ConfiguracionBonita
from app.main import app

BASE_URL = "http://bonita:8080/bonita"


@pytest.fixture
def http() -> Iterator[TestClient]:
    configuracion = ConfiguracionBonita(
        base_url=BASE_URL,
        usuario="install",
        password=SecretStr("install"),
        nombre_proceso="RescueSync",
        version_proceso="1.2",
        timeout_conexion_segundos=1,
        timeout_lectura_segundos=1,
    )
    with ClienteBonita(configuracion) as cliente:
        app.dependency_overrides[obtener_cliente_bonita] = lambda: cliente
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.pop(obtener_cliente_bonita, None)


def test_bonita_lista_con_el_proceso_habilitado(http: TestClient) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.post(f"{BASE_URL}/loginservice").mock(
            return_value=httpx.Response(
                204, headers={"set-cookie": "X-Bonita-API-Token=csrf"}
            )
        )
        router.get(f"{BASE_URL}/API/bpm/process").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "id": "1",
                        "name": "RescueSync",
                        "version": "1.2",
                        "activationState": "ENABLED",
                        "configurationState": "RESOLVED",
                    }
                ],
            )
        )

        response = http.get("/api/v1/health/bonita")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "bonita"}


def test_bonita_no_disponible_responde_503_sin_detalles(http: TestClient) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.post(f"{BASE_URL}/loginservice").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        response = http.get("/api/v1/health/bonita")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Bonita no está disponible o el proceso no está habilitado"
    }
