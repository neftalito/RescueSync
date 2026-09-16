"""Verifica el contrato mínimo de Entrega 2 contra un Runtime Bonita real."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx
import pytest

pytestmark = [
    pytest.mark.bonita_e2e,
    pytest.mark.skipif(
        os.getenv("RUN_BONITA_E2E") != "1",
        reason="Requiere RUN_BONITA_E2E=1 y Bonita levantado.",
    ),
]


@dataclass(frozen=True)
class RuntimeConfig:
    """Contiene los datos no sensibles del Runtime bajo prueba."""

    base_url: str
    username: str
    password: str
    process_name: str
    process_version: str
    timeout_seconds: float

    @classmethod
    def from_environment(cls) -> RuntimeConfig:
        """Construye la configuración E2E desde el entorno de Compose."""

        return cls(
            base_url=_required_environment("BONITA_BASE_URL").rstrip("/"),
            username=_required_environment("BONITA_USERNAME"),
            password=_required_environment("BONITA_PASSWORD"),
            process_name=os.getenv("BONITA_PROCESS_NAME", "RescueSync"),
            process_version=os.getenv("BONITA_PROCESS_VERSION", "1.1"),
            timeout_seconds=float(os.getenv("BONITA_E2E_TIMEOUT_SECONDS", "20")),
        )


def _required_environment(name: str) -> str:
    """Obtiene una variable obligatoria sin incluir su valor en errores."""

    value = os.getenv(name, "").strip()
    if not value:
        pytest.fail(f"La variable {name} es obligatoria para el E2E.")
    return value


def _json_object(response: httpx.Response, operation: str) -> dict[str, object]:
    """Valida que una respuesta exitosa contenga un objeto JSON."""

    assert response.status_code == 200, (
        f"{operation}: Bonita respondió HTTP {response.status_code}: "
        f"{response.text[:500]}"
    )
    payload = response.json()
    assert isinstance(payload, dict), f"{operation}: se esperaba un objeto JSON."
    return payload


def _json_list(response: httpx.Response, operation: str) -> list[object]:
    """Valida que una respuesta exitosa contenga una lista JSON."""

    assert response.status_code == 200, (
        f"{operation}: Bonita respondió HTTP {response.status_code}: "
        f"{response.text[:500]}"
    )
    payload = response.json()
    assert isinstance(payload, list), f"{operation}: se esperaba una lista JSON."
    return payload


def _identifier(value: object, field_name: str) -> str:
    """Normaliza identificadores que Bonita serializa como texto o número."""

    assert not isinstance(value, bool) and isinstance(value, (int, str)), (
        f"Bonita devolvió un {field_name} inválido: {value!r}."
    )
    identifier = str(value)
    assert identifier
    return identifier


def _login(client: httpx.Client, config: RuntimeConfig) -> None:
    """Inicia una sesión administrativa y configura el token CSRF."""

    response = client.post(
        f"{config.base_url}/loginservice",
        data={
            "username": config.username,
            "password": config.password,
            "redirect": "false",
        },
    )
    assert response.status_code in {200, 204}, (
        f"Bonita rechazó el login con HTTP {response.status_code}."
    )

    token = next(
        (
            cookie.value
            for cookie in client.cookies.jar
            if cookie.name == "X-Bonita-API-Token"
        ),
        None,
    )
    assert token, "Bonita no devolvió la cookie X-Bonita-API-Token."
    client.headers["X-Bonita-API-Token"] = token


def _enabled_process_id(client: httpx.Client, config: RuntimeConfig) -> str:
    """Obtiene la única definición habilitada para el proceso esperado."""

    processes = _json_list(
        client.get(
            f"{config.base_url}/API/bpm/process",
            params=[
                ("p", "0"),
                ("c", "10"),
                ("f", f"name={config.process_name}"),
                ("f", f"version={config.process_version}"),
                ("f", "activationState=ENABLED"),
            ],
        ),
        "búsqueda de la definición habilitada",
    )
    assert len(processes) == 1, (
        "Se esperaba una única definición habilitada de "
        f"{config.process_name}:{config.process_version}; se encontraron "
        f"{len(processes)}."
    )
    process = processes[0]
    assert isinstance(process, dict)
    return _identifier(process.get("id"), "processDefinitionId")


def _wait_for_coordinator_task(
    client: httpx.Client,
    config: RuntimeConfig,
    case_id: str,
) -> dict[str, object]:
    """Espera hasta que el caso llegue a la primera tarea del Coordinador."""

    deadline = time.monotonic() + config.timeout_seconds
    latest_tasks: list[object] = []
    while time.monotonic() < deadline:
        latest_tasks = _json_list(
            client.get(
                f"{config.base_url}/API/bpm/humanTask",
                params=[("p", "0"), ("c", "20"), ("f", f"caseId={case_id}")],
            ),
            "consulta de tareas humanas",
        )
        matching = [
            task
            for task in latest_tasks
            if isinstance(task, dict)
            and task.get("name") == "Generar lotes de necesidades"
            and task.get("state") == "ready"
        ]
        if matching:
            return matching[0]
        time.sleep(0.25)

    pytest.fail(
        "El caso no llegó a 'Generar lotes de necesidades'. "
        f"Últimas tareas observadas: {latest_tasks!r}"
    )


def _wait_until_task_leaves_ready_state(
    client: httpx.Client,
    config: RuntimeConfig,
    task_id: str,
) -> None:
    """Espera hasta que la ejecución retire la tarea de la bandeja activa."""

    deadline = time.monotonic() + config.timeout_seconds
    while time.monotonic() < deadline:
        response = client.get(f"{config.base_url}/API/bpm/humanTask/{task_id}")
        if response.status_code == 404:
            return
        assert response.status_code == 200, (
            "consulta de tarea ejecutada: Bonita respondió HTTP "
            f"{response.status_code}: {response.text[:500]}"
        )
        task = response.json()
        if isinstance(task, dict) and task.get("state") != "ready":
            return
        time.sleep(0.25)

    pytest.fail(
        "La tarea del Coordinador continuó en estado ready después de ejecutarla."
    )


def _wait_for_offer_timer(
    client: httpx.Client,
    config: RuntimeConfig,
    case_id: str,
) -> dict[str, object]:
    """Espera la ventana de ofertas administrada por el timer de Bonita."""

    deadline = time.monotonic() + config.timeout_seconds
    latest_triggers: list[object] = []
    latest_activities: list[object] = []
    while time.monotonic() < deadline:
        latest_triggers = _json_list(
            client.get(
                f"{config.base_url}/API/bpm/timerEventTrigger",
                params=[("p", "0"), ("c", "20"), ("caseId", case_id)],
            ),
            "consulta del timer de ofertas",
        )
        matching = [
            trigger
            for trigger in latest_triggers
            if isinstance(trigger, dict)
            and trigger.get("eventInstanceName") == "EsperarOfertas"
        ]
        if matching:
            return matching[0]

        latest_activities = _json_list(
            client.get(
                f"{config.base_url}/API/bpm/activity",
                params=[
                    ("p", "0"),
                    ("c", "20"),
                    ("f", f"parentProcessInstanceId={case_id}"),
                ],
            ),
            "consulta de actividades durante el avance al timer",
        )
        failed_activities = [
            activity
            for activity in latest_activities
            if isinstance(activity, dict) and activity.get("state") == "failed"
        ]
        if failed_activities:
            pytest.fail(
                "El flujo falló antes de llegar al timer 'EsperarOfertas'. "
                "Revisar los conectores del .bar y los callbacks de FastAPI. "
                f"Actividades fallidas: {failed_activities!r}"
            )

        case = _json_object(
            client.get(f"{config.base_url}/API/bpm/case/{case_id}"),
            "consulta del caso durante el avance al timer",
        )
        assert int(str(case.get("failedFlowNodes", "0"))) == 0
        time.sleep(0.25)

    pytest.fail(
        "El caso no llegó al timer 'EsperarOfertas'. "
        f"Últimos timers observados: {latest_triggers!r}. "
        f"Últimas actividades observadas: {latest_activities!r}"
    )


def _user_id(client: httpx.Client, config: RuntimeConfig, username: str) -> str:
    """Obtiene el identificador del usuario funcional indicado."""

    users = _json_list(
        client.get(
            f"{config.base_url}/API/identity/user",
            params=[("p", "0"), ("c", "2"), ("f", f"userName={username}")],
        ),
        f"búsqueda del usuario {username}",
    )
    assert len(users) == 1, f"No existe un único usuario {username}."
    user = users[0]
    assert isinstance(user, dict)
    return _identifier(user.get("id"), "userId")


def _assert_case_variable(
    client: httpx.Client,
    config: RuntimeConfig,
    case_id: str,
    name: str,
    expected_value: str,
) -> None:
    """Comprueba el valor persistido de una variable del proceso."""

    variable = _json_object(
        client.get(f"{config.base_url}/API/bpm/caseVariable/{case_id}/{name}"),
        f"consulta de la variable {name}",
    )
    assert str(variable.get("value")) == expected_value


def _cancel_case(
    client: httpx.Client,
    config: RuntimeConfig,
    case_id: str,
) -> None:
    """Cancela el caso creado por la prueba para no dejar estado residual."""

    response = client.put(
        f"{config.base_url}/API/bpm/case/{case_id}",
        json={"state": "cancelled"},
    )
    assert response.status_code == 200, (
        f"No se pudo cancelar el caso E2E {case_id}: HTTP {response.status_code}."
    )


def test_api_bonita_soporta_inicio_lotes_y_apertura_de_ofertas() -> None:
    """Valida el tramo hasta la ventana de ofertas exigido en Entrega 2."""

    config = RuntimeConfig.from_environment()
    payload = {
        "idEmergencia": 9_000_000_001,
        "gravedad": "ALTA",
        "zona": "Zona E2E",
        "descripcion": "Caso temporal para verificar la API de Bonita",
        "municipioId": 9_001,
    }

    with httpx.Client(timeout=config.timeout_seconds) as client:
        _login(client, config)
        process_id = _enabled_process_id(client, config)

        invalid_response = client.post(
            f"{config.base_url}/API/bpm/process/{process_id}/instantiation",
            json={"idEmergencia": payload["idEmergencia"], "gravedad": "ALTA"},
        )
        assert invalid_response.status_code == 400

        start_response = client.post(
            f"{config.base_url}/API/bpm/process/{process_id}/instantiation",
            json=payload,
        )
        start_payload = _json_object(start_response, "instanciación del proceso")
        case_id = _identifier(start_payload.get("caseId"), "caseId")

        try:
            _assert_case_variable(
                client, config, case_id, "idEmergencia", str(payload["idEmergencia"])
            )
            _assert_case_variable(
                client, config, case_id, "gravedad", str(payload["gravedad"])
            )
            _assert_case_variable(client, config, case_id, "zona", str(payload["zona"]))
            _assert_case_variable(
                client, config, case_id, "descripcion", str(payload["descripcion"])
            )
            _assert_case_variable(
                client, config, case_id, "municipioId", str(payload["municipioId"])
            )

            task = _wait_for_coordinator_task(client, config, case_id)
            task_id = _identifier(task.get("id"), "taskId")

            coordinator_id = _user_id(client, config, username="coordinador.regional")
            assign_response = client.put(
                f"{config.base_url}/API/bpm/humanTask/{task_id}",
                json={"assigned_id": coordinator_id},
            )
            assert assign_response.status_code == 200

            execute_response = client.post(
                f"{config.base_url}/API/bpm/userTask/{task_id}/execution",
                json={},
            )
            assert execute_response.status_code in {200, 204}
            _wait_until_task_leaves_ready_state(client, config, task_id)

            timer = _wait_for_offer_timer(client, config, case_id)
            execution_date = timer.get("executionDate")
            assert isinstance(execution_date, int)
            assert execution_date > int(time.time() * 1_000)

            case = _json_object(
                client.get(f"{config.base_url}/API/bpm/case/{case_id}"),
                "consulta del caso después de ejecutar la tarea",
            )
            assert case.get("state") == "started"
            assert int(str(case.get("failedFlowNodes", "0"))) == 0
        finally:
            _cancel_case(client, config, case_id)
