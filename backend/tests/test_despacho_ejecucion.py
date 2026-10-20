"""El HTTP de Bonita ocurre después del commit y el timeout conserva actividad."""

import json
from uuid import UUID, uuid4

import httpx
import pytest
import respx
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_ejecucion_nacional import adjudicar, capacidad, coordinador, preparar
from test_ofertas import Escenario, escenario

from app.db.models import Usuario
from app.db.models.ejecucion import ComandoBonita, EvaluacionLocal, OperacionNacional
from app.integrations.bonita.cliente import ClienteBonita, ConfiguracionBonita
from app.services.despacho_bonita import despachar

__all__ = ["capacidad", "coordinador", "escenario"]
BASE = "http://bonita:8080/bonita"


def test_timeout_ejecucion_reconcilia_id_exacto_sin_repetir_post(
    db_session: Session, escenario: Escenario, capacidad: UUID, coordinador: Usuario
) -> None:
    prep = adjudicar(
        db_session, escenario, coordinador, preparar(db_session, escenario, capacidad)
    )
    config = ConfiguracionBonita(
        base_url=BASE,
        usuario="install",
        password=SecretStr("secreto-prueba"),
        nombre_proceso="RescueSync",
        version_proceso="1.5",
        timeout_conexion_segundos=1,
        timeout_lectura_segundos=1,
    )
    with respx.mock as mock, ClienteBonita(config) as cliente:
        mock.post(f"{BASE}/loginservice").respond(
            204, headers={"set-cookie": "X-Bonita-API-Token=csrf"}
        )
        tarea = {
            "id": "77",
            "name": "Seleccionar ofertas validadas",
            "state": "ready",
            "caseId": "4242",
        }
        mock.get(f"{BASE}/API/bpm/humanTask").respond(200, json=[tarea])
        mock.get(f"{BASE}/API/bpm/humanTask/77").respond(200, json=tarea)
        mock.get(f"{BASE}/API/bpm/caseVariable/4242/intentoConvocatoria").respond(
            200, json={"value": "1"}
        )
        mock.get(f"{BASE}/API/identity/user").respond(
            200, json=[{"id": "4", "userName": "operador.municipal"}]
        )
        mock.put(f"{BASE}/API/bpm/humanTask/77").respond(200, json={})

        def timeout(request: httpx.Request) -> httpx.Response:
            assert not db_session.in_transaction(), (
                "No mantener una transacción durante HTTP"
            )
            assert json.loads(request.content)["operacionCompromisoId"] == str(
                prep.operacion_compromiso_id
            )
            raise httpx.ReadTimeout("Respuesta perdida", request=request)

        ejecucion = mock.post(f"{BASE}/API/bpm/userTask/77/execution").mock(
            side_effect=timeout
        )
        resultado = despachar(db_session, prep.adjudicacion_id, cliente)
        assert resultado.estado == "RESULTADO_DESCONOCIDO"
        assert db_session.get(ComandoBonita, prep.adjudicacion_id).tarea_id == 77
        mock.get(f"{BASE}/API/bpm/archivedFlowNode").respond(
            200,
            json=[
                {
                    "sourceObjectId": "77",
                    "rootCaseId": "4242",
                    "name": tarea["name"],
                    "type": "USER_TASK",
                    "state": "completed",
                    "reached_state_date": "2026-10-16 10:00:00",
                }
            ],
        )
        assert (
            despachar(db_session, prep.adjudicacion_id, cliente).estado == "COMPLETADA"
        )
        assert ejecucion.call_count == 1


def test_postgresql_impide_alterar_intenciones_y_resultados(
    db_session: Session, escenario: Escenario, capacidad: UUID, coordinador: Usuario
) -> None:
    datos = preparar(db_session, escenario, capacidad)
    prep = adjudicar(db_session, escenario, coordinador, datos)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.get(OperacionNacional, prep.operacion_compromiso_id).clave = str(
            uuid4()
        )
        db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.get(EvaluacionLocal, datos.validacion_id).snapshot = {}
        db_session.flush()


def test_una_tarea_de_otra_ronda_no_se_ejecuta(
    db_session: Session, escenario: Escenario, capacidad: UUID, coordinador: Usuario
) -> None:
    prep = adjudicar(
        db_session, escenario, coordinador, preparar(db_session, escenario, capacidad)
    )
    config = ConfiguracionBonita(
        base_url=BASE,
        usuario="install",
        password=SecretStr("prueba"),
        nombre_proceso="RescueSync",
        version_proceso="1.5",
        timeout_conexion_segundos=1,
        timeout_lectura_segundos=1,
    )
    with respx.mock as mock, ClienteBonita(config) as cliente:
        mock.post(f"{BASE}/loginservice").respond(
            204, headers={"set-cookie": "X-Bonita-API-Token=csrf"}
        )
        mock.get(f"{BASE}/API/bpm/humanTask").respond(
            200,
            json=[
                {
                    "id": "77",
                    "name": "Seleccionar ofertas validadas",
                    "state": "ready",
                    "caseId": "4242",
                }
            ],
        )
        mock.get(f"{BASE}/API/bpm/caseVariable/4242/intentoConvocatoria").respond(
            200, json={"value": "2"}
        )
        assert despachar(db_session, prep.adjudicacion_id, cliente).estado == "ERROR"
        assert all(
            c.request.method != "POST" or c.request.url.path.endswith("loginservice")
            for c in mock.calls
        )
