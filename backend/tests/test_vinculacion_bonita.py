import json
from collections.abc import Iterator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.api.dependencies import obtener_cliente_bonita
from app.core.security import (
    crear_token_csrf,
    crear_valor_sesion,
    generar_password_hash,
)
from app.db.models import (
    Emergencia,
    EstadoEmergencia,
    EstadoSincronizacionBonita,
    GravedadEmergencia,
    Organizacion,
    RolUsuario,
    TipoOrganizacion,
    Usuario,
)
from app.db.session import get_db
from app.integrations.bonita.cliente import ClienteBonita, ConfiguracionBonita
from app.main import app
from app.schemas.emergencia import EmergenciaCreate
from app.services import emergencias as servicio_emergencias
from app.services.vinculacion_bonita import vincular_emergencia_con_bonita

BASE_URL = "http://bonita:8080/bonita"
PASSWORD = "Una-clave-segura-2026"
SECRETO_BONITA = "secreto-tecnico-que-no-debe-filtrarse"
DEFINICION_ID = 7204236220545867063
CASE_ID = 4242


@pytest.fixture
def municipio(db_session: Session) -> Organizacion:
    organizacion = Organizacion(
        tipo=TipoOrganizacion.MUNICIPIO,
        nombre="Municipio de Vinculación",
    )
    db_session.add(organizacion)
    db_session.flush()
    return organizacion


@pytest.fixture
def usuario_municipal(db_session: Session, municipio: Organizacion) -> Usuario:
    usuario = Usuario(
        organizacion_id=municipio.id,
        email="vinculacion@municipio.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.OPERADOR_MUNICIPAL,
    )
    db_session.add(usuario)
    db_session.flush()
    db_session.refresh(usuario)
    return usuario


@pytest.fixture
def emergencia(db_session: Session, usuario_municipal: Usuario) -> Emergencia:
    return servicio_emergencias.registrar_emergencia(
        db_session,
        usuario_municipal,
        EmergenciaCreate(
            gravedad=GravedadEmergencia.ALTA,
            zona="Ribera norte",
            descripcion="Inundación con familias evacuadas",
        ),
    )


@pytest.fixture
def cliente() -> Iterator[ClienteBonita]:
    configuracion = ConfiguracionBonita(
        base_url=BASE_URL,
        usuario="install",
        password=SecretStr("clave-tecnica"),
        nombre_proceso="RescueSync",
        version_proceso="1.2",
        timeout_conexion_segundos=1,
        timeout_lectura_segundos=1,
    )
    with ClienteBonita(configuracion) as cliente_bonita:
        yield cliente_bonita


@pytest.fixture
def client(db_session: Session, cliente: ClienteBonita) -> Iterator[TestClient]:
    def usar_sesion_de_prueba() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = usar_sesion_de_prueba
    app.dependency_overrides[obtener_cliente_bonita] = lambda: cliente
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _login(router: respx.MockRouter, token: str = "csrf-1") -> None:
    router.post(f"{BASE_URL}/loginservice").mock(
        return_value=httpx.Response(
            204, headers={"set-cookie": f"X-Bonita-API-Token={token}"}
        )
    )


def _proceso(router: respx.MockRouter) -> None:
    router.get(f"{BASE_URL}/API/bpm/process").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": str(DEFINICION_ID),
                    "name": "RescueSync",
                    "version": "1.2",
                    "activationState": "ENABLED",
                    "configurationState": "RESOLVED",
                }
            ],
        )
    )


def _caso(emergencia_id: int, case_id: int = CASE_ID) -> dict[str, str]:
    return {
        "id": str(case_id),
        "processDefinitionId": str(DEFINICION_ID),
        "state": "started",
        "searchIndex1Label": "idEmergencia",
        "searchIndex1Value": str(emergencia_id),
    }


def _autenticar(client: TestClient, usuario: Usuario) -> str:
    client.cookies.set(
        "rescuesync_session",
        crear_valor_sesion(usuario.id),
        path="/api/v1",
    )
    return crear_token_csrf(usuario.id)


def test_vincula_al_confirmar_el_alta_con_caso_validado(
    db_session: Session,
    emergencia: Emergencia,
    municipio: Organizacion,
    cliente: ClienteBonita,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        _proceso(router)
        instanciacion = router.post(
            f"{BASE_URL}/API/bpm/process/{DEFINICION_ID}/instantiation"
        ).mock(return_value=httpx.Response(201, json={"caseId": CASE_ID}))

        vinculada = vincular_emergencia_con_bonita(db_session, emergencia, cliente)

    assert vinculada.estado is EstadoEmergencia.REGISTRADA
    assert vinculada.bonita_sync is EstadoSincronizacionBonita.VINCULADA
    assert vinculada.bonita_process_instance_id == CASE_ID
    assert vinculada.bonita_process_definition_id == DEFINICION_ID
    assert vinculada.bonita_process_version == "1.2"
    assert vinculada.bonita_ultimo_error is None
    assert vinculada.bonita_ultimo_intento_en is not None
    assert vinculada.bonita_ultimo_intento_en.tzinfo is not None
    assert instanciacion.call_count == 1
    assert json.loads(instanciacion.calls.last.request.content) == {
        "idEmergencia": emergencia.id,
        "gravedad": "ALTA",
        "zona": "Ribera norte",
        "descripcion": "Inundación con familias evacuadas",
        "municipioId": municipio.id,
    }


def test_rechazo_definitivo_conserva_emergencia_y_registra_error_seguro(
    db_session: Session, emergencia: Emergencia, cliente: ClienteBonita
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        _proceso(router)
        instanciacion = router.post(
            f"{BASE_URL}/API/bpm/process/{DEFINICION_ID}/instantiation"
        ).mock(
            return_value=httpx.Response(
                400,
                json={
                    "exception": "ContractViolationException",
                    "message": f"Error interno con {SECRETO_BONITA}",
                    "explanations": ["Expected input [zona] is missing"],
                },
            )
        )

        vinculada = vincular_emergencia_con_bonita(db_session, emergencia, cliente)

    assert vinculada.estado is EstadoEmergencia.REGISTRADA
    assert vinculada.bonita_sync is EstadoSincronizacionBonita.ERROR
    assert vinculada.bonita_process_instance_id is None
    assert vinculada.bonita_ultimo_error is not None
    assert SECRETO_BONITA not in vinculada.bonita_ultimo_error
    assert instanciacion.call_count == 1


@pytest.mark.parametrize("fallo", ["timeout", "error_500"])
def test_post_incierto_guarda_resultado_desconocido_sin_repetir(
    db_session: Session,
    emergencia: Emergencia,
    cliente: ClienteBonita,
    fallo: str,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        _proceso(router)
        instanciacion = router.post(
            f"{BASE_URL}/API/bpm/process/{DEFINICION_ID}/instantiation"
        )
        busqueda = router.get(f"{BASE_URL}/API/bpm/case")
        if fallo == "timeout":
            instanciacion.mock(side_effect=httpx.ReadTimeout("timeout"))
        else:
            instanciacion.mock(return_value=httpx.Response(500))
        busqueda.mock(return_value=httpx.Response(200, json=[]))

        vinculada = vincular_emergencia_con_bonita(db_session, emergencia, cliente)

    assert vinculada.estado is EstadoEmergencia.REGISTRADA
    assert vinculada.bonita_sync is EstadoSincronizacionBonita.RESULTADO_DESCONOCIDO
    assert vinculada.bonita_process_instance_id is None
    assert vinculada.bonita_ultimo_error is not None
    assert instanciacion.call_count == 1


def test_reintento_reconcilia_antes_de_repetir_el_post(
    db_session: Session, emergencia: Emergencia, cliente: ClienteBonita
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        _proceso(router)
        instanciacion = router.post(
            f"{BASE_URL}/API/bpm/process/{DEFINICION_ID}/instantiation"
        ).mock(side_effect=httpx.ReadTimeout("timeout"))
        router.get(f"{BASE_URL}/API/bpm/case").mock(
            return_value=httpx.Response(200, json=[])
        )

        primer_intento = vincular_emergencia_con_bonita(db_session, emergencia, cliente)

    assert (
        primer_intento.bonita_sync is EstadoSincronizacionBonita.RESULTADO_DESCONOCIDO
    )

    with respx.mock(assert_all_called=False) as router:
        acceso = router.post(f"{BASE_URL}/loginservice").mock(
            return_value=httpx.Response(204)
        )
        _proceso(router)
        busqueda = router.get(f"{BASE_URL}/API/bpm/case").mock(
            return_value=httpx.Response(200, json=[_caso(emergencia.id)])
        )

        segundo_intento = vincular_emergencia_con_bonita(
            db_session, emergencia, cliente
        )

    assert acceso.call_count == 0
    assert busqueda.call_count == 1

    assert segundo_intento.bonita_sync is EstadoSincronizacionBonita.VINCULADA
    assert segundo_intento.bonita_process_instance_id == CASE_ID
    assert segundo_intento.bonita_ultimo_error is None
    assert instanciacion.call_count == 1


def test_no_repite_el_post_si_ya_esta_vinculada(
    db_session: Session, emergencia: Emergencia, cliente: ClienteBonita
) -> None:
    emergencia.bonita_sync = EstadoSincronizacionBonita.VINCULADA
    emergencia.bonita_process_instance_id = CASE_ID
    db_session.commit()

    with respx.mock(assert_all_called=False) as router:
        acceso = router.post(f"{BASE_URL}/loginservice").mock(
            return_value=httpx.Response(204)
        )

        vinculada = vincular_emergencia_con_bonita(db_session, emergencia, cliente)

    assert vinculada.bonita_process_instance_id == CASE_ID
    assert acceso.call_count == 0


def test_alta_inicia_instancia_y_devuelve_vinculada(
    client: TestClient, usuario_municipal: Usuario
) -> None:
    csrf = _autenticar(client, usuario_municipal)
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        _proceso(router)
        router.post(f"{BASE_URL}/API/bpm/process/{DEFINICION_ID}/instantiation").mock(
            return_value=httpx.Response(201, json={"caseId": CASE_ID})
        )

        response = client.post(
            "/api/v1/emergencias",
            json={
                "gravedad": "CRITICA",
                "zona": "Corredor norte",
                "descripcion": "Inundación con evacuados",
            },
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["estado"] == EstadoEmergencia.REGISTRADA.value
    assert payload["bonita_sync"] == EstadoSincronizacionBonita.VINCULADA.value
    assert payload["bonita_process_instance_id"] == CASE_ID


def test_alta_con_bonita_rechazada_devuelve_201_con_error_trazable(
    client: TestClient, db_session: Session, usuario_municipal: Usuario
) -> None:
    csrf = _autenticar(client, usuario_municipal)
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        _proceso(router)
        router.post(f"{BASE_URL}/API/bpm/process/{DEFINICION_ID}/instantiation").mock(
            return_value=httpx.Response(
                400,
                json={
                    "message": f"Fallo interno con {SECRETO_BONITA}",
                    "explanations": ["Contrato inválido"],
                },
            )
        )

        response = client.post(
            "/api/v1/emergencias",
            json={
                "gravedad": "MEDIA",
                "zona": "Arroyo sur",
                "descripcion": "Desborde preventivo",
            },
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["estado"] == EstadoEmergencia.REGISTRADA.value
    assert payload["bonita_sync"] == EstadoSincronizacionBonita.ERROR.value

    db_session.expire_all()
    emergencia = db_session.get(Emergencia, payload["id"])
    assert emergencia is not None
    assert emergencia.estado is EstadoEmergencia.REGISTRADA
    assert emergencia.bonita_sync is EstadoSincronizacionBonita.ERROR
    assert emergencia.bonita_ultimo_error is not None
    assert SECRETO_BONITA not in emergencia.bonita_ultimo_error
