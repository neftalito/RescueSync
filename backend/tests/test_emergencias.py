from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
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
    Organizacion,
    RolUsuario,
    TipoOrganizacion,
    Usuario,
)
from app.db.session import get_db
from app.integrations.bonita.contratos import (
    CasoBonita,
    ContratoInicioProceso,
    DefinicionProceso,
    InstanciaIniciada,
)
from app.main import app
from app.schemas.emergencia import EmergenciaCreate
from app.services import emergencias as servicio_emergencias

PASSWORD = "Una-clave-segura-2026"
PAYLOAD_VALIDO = {
    "gravedad": "ALTA",
    "zona": "Ribera norte",
    "descripcion": "Inundación con familias evacuadas",
}
CASO_BONITA_PRUEBA = 4242


class ClienteBonitaParaPruebas:
    """Doble sin red que vincula al instante con un caso fijo."""

    def __init__(self) -> None:
        self.inicios = 0
        self.configuracion = SimpleNamespace(version_proceso="1.2")

    def obtener_proceso_habilitado(self) -> DefinicionProceso:
        return DefinicionProceso.model_validate(
            {
                "id": "55",
                "name": "RescueSync",
                "version": "1.2",
                "activationState": "ENABLED",
                "configurationState": "RESOLVED",
            }
        )

    def iniciar_instancia(
        self, proceso_id: int, contrato: ContratoInicioProceso
    ) -> InstanciaIniciada:
        self.inicios += 1
        return InstanciaIniciada.model_validate({"caseId": CASO_BONITA_PRUEBA})

    def buscar_casos_por_emergencia(
        self, proceso_id: int, id_emergencia: int
    ) -> list[CasoBonita]:
        return []


@pytest.fixture
def municipio(db_session: Session) -> Organizacion:
    organizacion = Organizacion(
        tipo=TipoOrganizacion.MUNICIPIO,
        nombre="Municipio de Prueba",
    )
    db_session.add(organizacion)
    db_session.flush()
    return organizacion


@pytest.fixture
def usuario_municipal(db_session: Session, municipio: Organizacion) -> Usuario:
    usuario = Usuario(
        organizacion_id=municipio.id,
        email="operador@municipio.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.OPERADOR_MUNICIPAL,
    )
    db_session.add(usuario)
    db_session.flush()
    db_session.refresh(usuario)
    return usuario


@pytest.fixture
def usuarios_no_municipales(db_session: Session) -> dict[RolUsuario, Usuario]:
    """Crea un usuario vigente por cada rol que no registra emergencias."""

    password_hash = generar_password_hash(PASSWORD)
    contextos: dict[RolUsuario, tuple[TipoOrganizacion | None, str, str]] = {
        RolUsuario.COORDINADOR_REGIONAL: (
            TipoOrganizacion.CENTRO_COORDINADOR,
            "Centro Regional Prueba",
            "coordinador-prueba@rescuesync.org",
        ),
        RolUsuario.REPRESENTANTE_ONG: (
            TipoOrganizacion.ONG,
            "ONG Prueba",
            "ong-prueba@rescuesync.org",
        ),
        RolUsuario.AUDITOR_DIRECTIVO: (
            None,
            "Auditor Prueba",
            "auditor-emergencias@rescuesync.org",
        ),
    }
    usuarios: dict[RolUsuario, Usuario] = {}
    for rol, (tipo, nombre, email) in contextos.items():
        organizacion_id: int | None = None
        if tipo is not None:
            organizacion = Organizacion(tipo=tipo, nombre=nombre)
            db_session.add(organizacion)
            db_session.flush()
            organizacion_id = organizacion.id
        usuario = Usuario(
            organizacion_id=organizacion_id,
            email=email,
            password_hash=password_hash,
            rol=rol,
        )
        db_session.add(usuario)
        db_session.flush()
        db_session.refresh(usuario)
        usuarios[rol] = usuario
    return usuarios


@pytest.fixture
def doble_bonita() -> ClienteBonitaParaPruebas:
    return ClienteBonitaParaPruebas()


@pytest.fixture
def client(
    db_session: Session, doble_bonita: ClienteBonitaParaPruebas
) -> Iterator[TestClient]:
    def usar_sesion_de_prueba() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = usar_sesion_de_prueba
    app.dependency_overrides[obtener_cliente_bonita] = lambda: doble_bonita
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _autenticar(client: TestClient, usuario: Usuario) -> str:
    client.cookies.set(
        "rescuesync_session",
        crear_valor_sesion(usuario.id),
        path="/api/v1",
    )
    return crear_token_csrf(usuario.id)


def _contar_emergencias(db_session: Session) -> int:
    return db_session.scalar(select(func.count()).select_from(Emergencia)) or 0


def test_registra_emergencia_valida_con_municipio_y_estado_inicial(
    client: TestClient,
    db_session: Session,
    usuario_municipal: Usuario,
    municipio: Organizacion,
    doble_bonita: ClienteBonitaParaPruebas,
) -> None:
    csrf = _autenticar(client, usuario_municipal)
    iniciales = _contar_emergencias(db_session)

    response = client.post(
        "/api/v1/emergencias",
        json=PAYLOAD_VALIDO,
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["gravedad"] == "ALTA"
    assert payload["zona"] == "Ribera norte"
    assert payload["descripcion"] == "Inundación con familias evacuadas"
    assert payload["estado"] == EstadoEmergencia.REGISTRADA.value
    assert payload["bonita_sync"] == EstadoSincronizacionBonita.VINCULADA.value
    assert payload["municipio_id"] == municipio.id
    assert payload["creada_por_usuario_id"] == usuario_municipal.id
    assert payload["centro_coordinador_id"] is None
    assert payload["bonita_process_instance_id"] == CASO_BONITA_PRUEBA
    assert doble_bonita.inicios == 1
    assert _contar_emergencias(db_session) == iniciales + 1

    db_session.expire_all()
    emergencia = db_session.get(Emergencia, payload["id"])
    assert emergencia is not None
    assert emergencia.estado is EstadoEmergencia.REGISTRADA
    assert emergencia.bonita_sync is EstadoSincronizacionBonita.VINCULADA
    assert emergencia.bonita_process_instance_id == CASO_BONITA_PRUEBA
    assert emergencia.municipio_id == municipio.id
    assert emergencia.creada_por_usuario_id == usuario_municipal.id


@pytest.mark.parametrize(
    "payload",
    [
        {"zona": "Ribera norte", "descripcion": "Falta la gravedad"},
        {"gravedad": "ALTA", "descripcion": "Falta la zona"},
        {"gravedad": "ALTA", "zona": "Ribera norte"},
        {"gravedad": "EXTREMA", "zona": "Ribera", "descripcion": "Gravedad inválida"},
        {"gravedad": "ALTA", "zona": "", "descripcion": "Zona vacía"},
        {"gravedad": "ALTA", "zona": "   ", "descripcion": "Zona en blancos"},
        {"gravedad": "ALTA", "zona": "Ribera", "descripcion": ""},
        {"gravedad": "ALTA", "zona": "Ribera", "descripcion": "   "},
        {"gravedad": "ALTA", "zona": "x" * 256, "descripcion": "Zona muy larga"},
    ],
)
def test_registra_emergencia_rechaza_datos_invalidos_sin_persistir(
    client: TestClient,
    db_session: Session,
    usuario_municipal: Usuario,
    payload: dict[str, str],
) -> None:
    csrf = _autenticar(client, usuario_municipal)
    iniciales = _contar_emergencias(db_session)

    response = client.post(
        "/api/v1/emergencias",
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422
    assert _contar_emergencias(db_session) == iniciales


def test_registra_emergencia_exige_sesion(
    client: TestClient,
    db_session: Session,
    usuario_municipal: Usuario,
) -> None:
    iniciales = _contar_emergencias(db_session)
    response = client.post(
        "/api/v1/emergencias",
        json=PAYLOAD_VALIDO,
        headers={"X-CSRF-Token": crear_token_csrf(usuario_municipal.id)},
    )

    assert response.status_code == 401
    assert _contar_emergencias(db_session) == iniciales


@pytest.mark.parametrize(
    "rol",
    [
        RolUsuario.COORDINADOR_REGIONAL,
        RolUsuario.REPRESENTANTE_ONG,
        RolUsuario.AUDITOR_DIRECTIVO,
    ],
)
def test_registra_emergencia_deniega_roles_no_municipales(
    client: TestClient,
    db_session: Session,
    usuarios_no_municipales: dict[RolUsuario, Usuario],
    rol: RolUsuario,
) -> None:
    usuario = usuarios_no_municipales[rol]
    csrf = _autenticar(client, usuario)
    iniciales = _contar_emergencias(db_session)

    response = client.post(
        "/api/v1/emergencias",
        json=PAYLOAD_VALIDO,
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 403
    assert _contar_emergencias(db_session) == iniciales


@pytest.mark.parametrize("token", [None, "token-invalido"])
def test_registra_emergencia_exige_csrf_vigente(
    client: TestClient,
    db_session: Session,
    usuario_municipal: Usuario,
    token: str | None,
) -> None:
    _autenticar(client, usuario_municipal)
    headers = {"X-CSRF-Token": token} if token is not None else {}
    iniciales = _contar_emergencias(db_session)

    response = client.post("/api/v1/emergencias", json=PAYLOAD_VALIDO, headers=headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "El token CSRF no es válido."}
    assert _contar_emergencias(db_session) == iniciales


def test_registra_emergencia_rechaza_csrf_de_otro_usuario(
    client: TestClient,
    db_session: Session,
    usuario_municipal: Usuario,
    municipio: Organizacion,
) -> None:
    otro = Usuario(
        organizacion_id=municipio.id,
        email="otro@municipio.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.OPERADOR_MUNICIPAL,
    )
    db_session.add(otro)
    db_session.flush()
    _autenticar(client, usuario_municipal)
    iniciales = _contar_emergencias(db_session)

    response = client.post(
        "/api/v1/emergencias",
        json=PAYLOAD_VALIDO,
        headers={"X-CSRF-Token": crear_token_csrf(otro.id)},
    )

    assert response.status_code == 403
    assert _contar_emergencias(db_session) == iniciales


def test_registra_emergencia_hace_rollback_ante_fallo_de_persistencia(
    client: TestClient,
    db_session: Session,
    usuario_municipal: Usuario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csrf = _autenticar(client, usuario_municipal)
    iniciales = _contar_emergencias(db_session)

    def commit_fallido() -> None:
        raise IntegrityError("INSERT", {}, Exception("restricción simulada"))

    monkeypatch.setattr(db_session, "commit", commit_fallido)

    response = client.post(
        "/api/v1/emergencias",
        json=PAYLOAD_VALIDO,
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Los datos de la emergencia no son válidos."}
    db_session.rollback()
    assert _contar_emergencias(db_session) == iniciales


def test_registrar_emergencia_rechaza_usuario_sin_municipio_vigente(
    db_session: Session,
) -> None:
    iniciales = _contar_emergencias(db_session)
    usuario_sin_municipio = Usuario(
        organizacion_id=None,
        email="sin-municipio@rescuesync.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.OPERADOR_MUNICIPAL,
    )

    with pytest.raises(servicio_emergencias.MunicipioInvalidoError):
        servicio_emergencias.registrar_emergencia(
            db_session,
            usuario_sin_municipio,
            EmergenciaCreate(**PAYLOAD_VALIDO),
        )

    assert _contar_emergencias(db_session) == iniciales


def test_openapi_documenta_el_alta_de_emergencia(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    operacion = response.json()["paths"]["/api/v1/emergencias"]["post"]
    assert operacion["responses"]["201"]["description"]
    assert operacion["summary"]
    assert operacion["description"]
    assert "EmergenciaResponse" in str(operacion["responses"]["201"])
