"""Verifica el cliente de FastAPI contra un Runtime Bonita real (Entrega 2)."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator

import httpx
import pytest

from app.core.config import get_settings
from app.db.models.enums import GravedadEmergencia
from app.integrations.bonita.cliente import (
    BonitaOperacionRechazadaError,
    ClienteBonita,
    ConfiguracionBonita,
)
from app.integrations.bonita.contratos import (
    TAREA_GENERAR_LOTES,
    USUARIO_ACTOR_COORDINADOR,
    ContratoInicioProceso,
    TareaHumana,
)

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


def _esperar[T](descripcion: str, obtener: Callable[[], T | None]) -> T:
    deadline = time.monotonic() + TIMEOUT_SEGUNDOS
    while time.monotonic() < deadline:
        if (resultado := obtener()) is not None:
            return resultado
        time.sleep(0.25)
    pytest.fail(f"Se agotó la espera: {descripcion}.")


def _json(response: httpx.Response) -> object:
    assert response.status_code == 200, response.text[:500]
    return response.json()


def _nodos_fallidos(observador: httpx.Client, case_id: int) -> list[object]:
    actividades = _json(
        observador.get(
            "/API/bpm/activity",
            params=[
                ("p", 0),
                ("c", 50),
                ("f", f"parentProcessInstanceId={case_id}"),
                ("f", "state=failed"),
            ],
        )
    )
    assert isinstance(actividades, list)
    return actividades


def _timer_de_ofertas(
    observador: httpx.Client, case_id: int
) -> dict[str, object] | None:
    fallidos = _nodos_fallidos(observador, case_id)
    if fallidos:
        nombres = [a.get("name") for a in fallidos if isinstance(a, dict)]
        pytest.fail(
            "El flujo falló antes de llegar al timer 'EsperarOfertas'. Revisar "
            f"conectores del .bar y callbacks de FastAPI. Actividades: {nombres}"
        )
    timers = _json(
        observador.get(
            "/API/bpm/timerEventTrigger",
            params=[("p", 0), ("c", 20), ("caseId", case_id)],
        )
    )
    assert isinstance(timers, list)
    return next(
        (
            timer
            for timer in timers
            if isinstance(timer, dict)
            and timer.get("eventInstanceName") == "EsperarOfertas"
        ),
        None,
    )


def test_api_bonita_soporta_inicio_lotes_y_apertura_de_ofertas(
    cliente: ClienteBonita,
    observador: httpx.Client,
) -> None:
    """Valida el tramo hasta la ventana de ofertas exigido en Entrega 2."""

    id_emergencia = 9_000_000_000 + int(time.time())
    contrato = ContratoInicioProceso(
        idEmergencia=id_emergencia,
        gravedad=GravedadEmergencia.ALTA,
        zona="Zona E2E",
        descripcion="Caso temporal para verificar la API de Bonita",
        municipioId=9_001,
    )
    proceso = cliente.obtener_proceso_habilitado()

    # Se omite la validación local para confirmar que el motor rechaza lo mismo.
    no_admitido = contrato.model_construct(
        **(contrato.__dict__ | {"gravedad": GravedadEmergencia.CRITICA})
    )
    with pytest.raises(BonitaOperacionRechazadaError, match="HTTP 400"):
        cliente.iniciar_instancia(proceso.id, no_admitido)

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

        tarea: TareaHumana = _esperar(
            f"tarea '{TAREA_GENERAR_LOTES}'",
            lambda: cliente.buscar_tarea_lista(case_id, TAREA_GENERAR_LOTES),
        )
        cliente.ejecutar_tarea(tarea.id, USUARIO_ACTOR_COORDINADOR)

        timer = _esperar(
            "timer 'EsperarOfertas'",
            lambda: _timer_de_ofertas(observador, case_id),
        )
        execution_date = timer.get("executionDate")
        assert isinstance(execution_date, int)
        assert execution_date > int(time.time() * 1_000)
        assert _nodos_fallidos(observador, case_id) == []
    finally:
        response = observador.put(
            f"/API/bpm/case/{case_id}", json={"state": "cancelled"}
        )
        assert response.status_code == 200, f"No se pudo cancelar el caso {case_id}."
