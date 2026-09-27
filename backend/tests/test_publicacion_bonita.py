from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.security import generar_password_hash
from app.db.models import (
    Convocatoria,
    Emergencia,
    EstadoSincronizacionBonita,
    EstadoTareaBonita,
    GravedadEmergencia,
    Organizacion,
    RolUsuario,
    TipoOrganizacion,
    Usuario,
)
from app.integrations.bonita.cliente import ClienteBonita, ConfiguracionBonita
from app.integrations.bonita.contratos import (
    TAREA_GENERAR_LOTES,
    USUARIO_ACTOR_COORDINADOR,
)
from app.schemas.emergencia import EmergenciaCreate
from app.services import emergencias as servicio_emergencias
from app.services.publicacion_bonita import completar_generacion_lotes

BASE_URL = "http://bonita:8080/bonita"
PASSWORD = "Una-clave-segura-2026"
CASE_ID = 4242
TAREA_ID = 17


@pytest.fixture
def municipio(db_session: Session) -> Organizacion:
    organizacion = Organizacion(
        tipo=TipoOrganizacion.MUNICIPIO,
        nombre="Municipio de Publicación Bonita",
    )
    db_session.add(organizacion)
    db_session.flush()
    return organizacion


@pytest.fixture
def usuario_municipal(db_session: Session, municipio: Organizacion) -> Usuario:
    usuario = Usuario(
        organizacion_id=municipio.id,
        email="publicacion-bonita@municipio.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.OPERADOR_MUNICIPAL,
    )
    db_session.add(usuario)
    db_session.flush()
    db_session.refresh(usuario)
    return usuario


@pytest.fixture
def emergencia(db_session: Session, usuario_municipal: Usuario) -> Emergencia:
    """Emergencia ya vinculada a un caso de Bonita (simula un alta previa)."""

    emergencia = servicio_emergencias.registrar_emergencia(
        db_session,
        usuario_municipal,
        EmergenciaCreate(
            gravedad=GravedadEmergencia.ALTA,
            zona="Ribera norte",
            descripcion="Inundación con familias evacuadas",
        ),
    )
    emergencia.bonita_sync = EstadoSincronizacionBonita.VINCULADA
    emergencia.bonita_process_instance_id = CASE_ID
    db_session.commit()
    db_session.refresh(emergencia)
    return emergencia


@pytest.fixture
def convocatoria(db_session: Session, emergencia: Emergencia) -> Convocatoria:
    ahora = datetime.now(UTC)
    convocatoria = Convocatoria(
        emergencia_id=emergencia.id,
        numero=1,
        publicada_en=ahora,
        cierra_en=ahora + timedelta(hours=2),
    )
    db_session.add(convocatoria)
    db_session.commit()
    db_session.refresh(convocatoria)
    return convocatoria


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


def _login(router: respx.MockRouter, token: str = "csrf-1") -> None:
    router.post(f"{BASE_URL}/loginservice").mock(
        return_value=httpx.Response(
            204, headers={"set-cookie": f"X-Bonita-API-Token={token}"}
        )
    )


def _tarea_lista(router: respx.MockRouter, case_id: int = CASE_ID) -> None:
    router.get(f"{BASE_URL}/API/bpm/humanTask").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": str(TAREA_ID),
                    "name": TAREA_GENERAR_LOTES,
                    "state": "ready",
                    "caseId": str(case_id),
                }
            ],
        )
    )


def _sin_tarea_lista(router: respx.MockRouter) -> None:
    router.get(f"{BASE_URL}/API/bpm/humanTask").mock(
        return_value=httpx.Response(200, json=[])
    )


def _identidad(router: respx.MockRouter) -> None:
    router.get(f"{BASE_URL}/API/identity/user").mock(
        return_value=httpx.Response(
            200, json=[{"id": "9", "userName": USUARIO_ACTOR_COORDINADOR}]
        )
    )


def test_completa_la_tarea_y_marca_completada(
    db_session: Session,
    emergencia: Emergencia,
    convocatoria: Convocatoria,
    cliente: ClienteBonita,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        _tarea_lista(router)
        _identidad(router)
        asignacion = router.put(f"{BASE_URL}/API/bpm/humanTask/{TAREA_ID}").mock(
            return_value=httpx.Response(200)
        )
        ejecucion = router.post(
            f"{BASE_URL}/API/bpm/userTask/{TAREA_ID}/execution"
        ).mock(return_value=httpx.Response(204))

        resultado = completar_generacion_lotes(
            db_session, emergencia, convocatoria, cliente
        )

    assert resultado.bonita_generar_lotes_estado is EstadoTareaBonita.COMPLETADA
    assert resultado.bonita_generar_lotes_ultimo_error is None
    assert resultado.bonita_generar_lotes_ultimo_intento_en is not None
    assert asignacion.call_count == 1
    assert ejecucion.call_count == 1


def test_marca_error_si_no_encuentra_la_tarea_lista_por_primera_vez(
    db_session: Session,
    emergencia: Emergencia,
    convocatoria: Convocatoria,
    cliente: ClienteBonita,
) -> None:
    """Sin un intento previo incierto, no encontrar la tarea no es éxito."""

    assert convocatoria.bonita_generar_lotes_estado is EstadoTareaBonita.PENDIENTE

    with respx.mock(assert_all_called=True) as router:
        _login(router)
        _sin_tarea_lista(router)

        resultado = completar_generacion_lotes(
            db_session, emergencia, convocatoria, cliente
        )

    assert resultado.bonita_generar_lotes_estado is EstadoTareaBonita.ERROR
    assert resultado.bonita_generar_lotes_ultimo_error is not None


def test_reconcilia_como_completada_tras_un_intento_previo_incierto(
    db_session: Session,
    emergencia: Emergencia,
    convocatoria: Convocatoria,
    cliente: ClienteBonita,
) -> None:
    """Si el intento anterior quedó incierto, no encontrar la tarea sí confirma éxito."""

    convocatoria.bonita_generar_lotes_estado = EstadoTareaBonita.RESULTADO_DESCONOCIDO
    db_session.commit()

    with respx.mock(assert_all_called=True) as router:
        _login(router)
        _sin_tarea_lista(router)

        resultado = completar_generacion_lotes(
            db_session, emergencia, convocatoria, cliente
        )

    assert resultado.bonita_generar_lotes_estado is EstadoTareaBonita.COMPLETADA


def test_marca_error_si_la_emergencia_no_esta_vinculada(
    db_session: Session,
    emergencia: Emergencia,
    convocatoria: Convocatoria,
    cliente: ClienteBonita,
) -> None:
    emergencia.bonita_sync = EstadoSincronizacionBonita.PENDIENTE
    emergencia.bonita_process_instance_id = None
    db_session.commit()

    with respx.mock(assert_all_called=False) as router:
        acceso = router.post(f"{BASE_URL}/loginservice").mock(
            return_value=httpx.Response(204)
        )

        resultado = completar_generacion_lotes(
            db_session, emergencia, convocatoria, cliente
        )

    assert resultado.bonita_generar_lotes_estado is EstadoTareaBonita.ERROR
    assert resultado.bonita_generar_lotes_ultimo_error is not None
    assert acceso.call_count == 0


def test_marca_error_ante_un_rechazo_definitivo_de_bonita(
    db_session: Session,
    emergencia: Emergencia,
    convocatoria: Convocatoria,
    cliente: ClienteBonita,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        _tarea_lista(router)
        _identidad(router)
        router.put(f"{BASE_URL}/API/bpm/humanTask/{TAREA_ID}").mock(
            return_value=httpx.Response(200)
        )
        router.post(f"{BASE_URL}/API/bpm/userTask/{TAREA_ID}/execution").mock(
            return_value=httpx.Response(400, json={"message": "Contrato inválido"})
        )

        resultado = completar_generacion_lotes(
            db_session, emergencia, convocatoria, cliente
        )

    assert resultado.bonita_generar_lotes_estado is EstadoTareaBonita.ERROR
    assert resultado.bonita_generar_lotes_ultimo_error is not None


def test_marca_resultado_desconocido_ante_una_ejecucion_incierta(
    db_session: Session,
    emergencia: Emergencia,
    convocatoria: Convocatoria,
    cliente: ClienteBonita,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        _tarea_lista(router)
        _identidad(router)
        router.put(f"{BASE_URL}/API/bpm/humanTask/{TAREA_ID}").mock(
            return_value=httpx.Response(200)
        )
        router.post(f"{BASE_URL}/API/bpm/userTask/{TAREA_ID}/execution").mock(
            side_effect=httpx.ReadTimeout("timeout")
        )

        resultado = completar_generacion_lotes(
            db_session, emergencia, convocatoria, cliente
        )

    assert (
        resultado.bonita_generar_lotes_estado is EstadoTareaBonita.RESULTADO_DESCONOCIDO
    )
    assert resultado.bonita_generar_lotes_ultimo_error is not None


def test_no_repite_nada_si_ya_estaba_completada(
    db_session: Session,
    emergencia: Emergencia,
    convocatoria: Convocatoria,
    cliente: ClienteBonita,
) -> None:
    convocatoria.bonita_generar_lotes_estado = EstadoTareaBonita.COMPLETADA
    db_session.commit()

    with respx.mock(assert_all_called=False) as router:
        acceso = router.post(f"{BASE_URL}/loginservice").mock(
            return_value=httpx.Response(204)
        )

        resultado = completar_generacion_lotes(
            db_session, emergencia, convocatoria, cliente
        )

    assert resultado.bonita_generar_lotes_estado is EstadoTareaBonita.COMPLETADA
    assert acceso.call_count == 0
