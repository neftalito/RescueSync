"""Verifica el cliente de FastAPI contra un Runtime Bonita real (Entrega 2)."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import httpx
import pytest

from app.core.config import get_settings
from app.db.models.enums import GravedadEmergencia
from app.integrations.bonita.cliente import (
    ClienteBonita,
    ConfiguracionBonita,
)
from app.integrations.bonita.contratos import ContratoInicioProceso

pytestmark = [
    pytest.mark.bonita_e2e,
    pytest.mark.skipif(
        os.getenv("RUN_BONITA_E2E") != "1",
        reason="Requiere RUN_BONITA_E2E=1 y Bonita levantado.",
    ),
]

TIMEOUT_SEGUNDOS = float(os.getenv("BONITA_E2E_TIMEOUT_SECONDS", "20"))


@pytest.fixture
def cliente() -> Iterator[ClienteBonita]:
    with ClienteBonita(ConfiguracionBonita.desde_settings(get_settings())) as cliente:
        yield cliente


@pytest.fixture
def observador() -> Iterator[httpx.Client]:
    """Sesión independiente para inspeccionar el caso sin usar el código probado."""

    settings = get_settings()
    with httpx.Client(
        base_url=settings.bonita_base_url.rstrip("/"),
        timeout=TIMEOUT_SEGUNDOS,
    ) as client:
        response = client.post(
            "/loginservice",
            data={
                "username": settings.bonita_username,
                "password": settings.bonita_password.get_secret_value(),
                "redirect": "false",
            },
        )
        assert response.status_code in {200, 204}
        client.headers["X-Bonita-API-Token"] = response.cookies["X-Bonita-API-Token"]
        yield client


def _json(response: httpx.Response) -> object:
    assert response.status_code == 200, response.text[:500]
    return response.json()


def test_api_bonita_soporta_inicio_y_reconciliacion(
    cliente: ClienteBonita,
    observador: httpx.Client,
) -> None:
    """Valida el contrato inicial exigido por la integración de Entrega 2."""

    id_emergencia = 9_000_000_000 + int(time.time())
    contrato = ContratoInicioProceso(
        idEmergencia=id_emergencia,
        gravedad=GravedadEmergencia.CRITICA,
        zona="Zona E2E",
        descripcion="Caso temporal para verificar la API de Bonita",
        municipioId=9_001,
    )
    proceso = cliente.obtener_proceso_habilitado()

    case_id = cliente.iniciar_instancia(proceso.id, contrato).case_id
    try:
        casos = cliente.buscar_casos_por_emergencia(proceso.id, id_emergencia)
        assert [caso.id for caso in casos] == [case_id]

        for nombre, esperado in contrato.a_payload().items():
            variable = _json(
                observador.get(f"/API/bpm/caseVariable/{case_id}/{nombre}")
            )
            assert isinstance(variable, dict)
            assert variable.get("value") == str(esperado)
    finally:
        response = observador.put(
            f"/API/bpm/case/{case_id}", json={"state": "cancelled"}
        )
        assert response.status_code == 200, f"No se pudo cancelar el caso {case_id}."
