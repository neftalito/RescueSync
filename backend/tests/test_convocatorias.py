"""Pruebas del endpoint de publicación de convocatorias."""

from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    crear_token_csrf,
    crear_valor_sesion,
    generar_password_hash,
)
from app.db.models import (
    Convocatoria,
    Emergencia,
    EstadoEmergencia,
    EstadoLote,
    GravedadEmergencia,
    Lote,
    Organizacion,
    RolUsuario,
    TipoOrganizacion,
    Usuario,
)
from app.db.session import get_db
from app.main import app
from app.services import convocatorias as servicio_convocatorias

PASSWORD = "Una-clave-segura-2026"


@pytest.fixture
def municipio(db_session: Session) -> Organizacion:
    organizacion = Organizacion(
        tipo=TipoOrganizacion.MUNICIPIO,
        nombre="Municipio de Convocatorias",
    )
    db_session.add(organizacion)
    db_session.flush()
    return organizacion


@pytest.fixture
def operador(db_session: Session, municipio: Organizacion) -> Usuario:
    usuario = Usuario(
        organizacion_id=municipio.id,
        email="operador-convocatorias@municipio.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.OPERADOR_MUNICIPAL,
    )
    db_session.add(usuario)
    db_session.flush()
    db_session.refresh(usuario)
    return usuario


@pytest.fixture
def centro(db_session: Session) -> Organizacion:
    organizacion = Organizacion(
        tipo=TipoOrganizacion.CENTRO_COORDINADOR,
        nombre="Centro de Convocatorias",
    )
    db_session.add(organizacion)
    db_session.flush()
    return organizacion


@pytest.fixture
def coordinador(db_session: Session, centro: Organizacion) -> Usuario:
    usuario = Usuario(
        organizacion_id=centro.id,
        email="coordinador-convocatorias@centro.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.COORDINADOR_REGIONAL,
    )
    db_session.add(usuario)
    db_session.flush()
    db_session.refresh(usuario)
    return usuario


@pytest.fixture
def usuarios_denegados(
    db_session: Session, municipio: Organizacion
) -> dict[RolUsuario, Usuario]:
    """Usuarios vigentes de roles que no publican convocatorias."""

    password_hash = generar_password_hash(PASSWORD)
    ong = Organizacion(tipo=TipoOrganizacion.ONG, nombre="ONG de Convocatorias")
    db_session.add(ong)
    db_session.flush()
    contextos: dict[RolUsuario, tuple[int | None, str]] = {
        RolUsuario.OPERADOR_MUNICIPAL: (
            municipio.id,
            "municipal-convocatorias@santafe.org",
        ),
        RolUsuario.REPRESENTANTE_ONG: (ong.id, "ong-convocatorias@rescuesync.org"),
        RolUsuario.AUDITOR_DIRECTIVO: (
            None,
            "auditor-convocatorias@rescuesync.org",
        ),
    }
    usuarios: dict[RolUsuario, Usuario] = {}
    for rol, (organizacion_id, email) in contextos.items():
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
def emergencia(
    db_session: Session, municipio: Organizacion, operador: Usuario
) -> Emergencia:
    emergencia = Emergencia(
        municipio_id=municipio.id,
        creada_por_usuario_id=operador.id,
        gravedad=GravedadEmergencia.ALTA,
        zona="Ribera norte",
        descripcion="Inundación con familias evacuadas",
    )
    db_session.add(emergencia)
    db_session.flush()
    db_session.refresh(emergencia)
    return emergencia


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def usar_sesion_de_prueba() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = usar_sesion_de_prueba
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


def _lote(
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    tipo: str = "Agua potable",
    estado: EstadoLote = EstadoLote.BORRADOR,
) -> Lote:
    lote = Lote(
        emergencia_id=emergencia.id,
        creado_por_usuario_id=coordinador.id,
        tipo_necesidad=tipo,
        descripcion="Necesidad prioritaria",
        cantidad_requerida=Decimal(1000),
        unidad="litros",
        estado=estado,
    )
    db_session.add(lote)
    db_session.flush()
    db_session.refresh(lote)
    return lote


def _contar_convocatorias(db_session: Session, emergencia_id: int) -> int:
    return (
        db_session.scalar(
            select(func.count())
            .select_from(Convocatoria)
            .where(Convocatoria.emergencia_id == emergencia_id)
        )
        or 0
    )


def test_publica_convocatoria_con_lotes_en_borrador_y_pasa_a_publicada(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    lote = _lote(db_session, emergencia, coordinador, tipo="Agua potable")
    otro_lote = _lote(db_session, emergencia, coordinador, tipo="Alimentos")
    db_session.flush()
    csrf = _autenticar(client, coordinador)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/publicar",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["numero"] == 1
    assert payload["estado"] == "ABIERTA"
    assert payload["emergencia_id"] == emergencia.id
    assert {item["lote_id"] for item in payload["lotes"]} == {lote.id, otro_lote.id}
    assert all(
        Decimal(item["cantidad_publicada"]) == Decimal(1000)
        and item["unidad_publicada"] == "litros"
        for item in payload["lotes"]
    )

    db_session.expire_all()
    emergencia_guardada = db_session.get(Emergencia, emergencia.id)
    assert emergencia_guardada is not None
    assert emergencia_guardada.estado is EstadoEmergencia.PUBLICADA
    assert db_session.get(Lote, lote.id).estado is EstadoLote.PUBLICADO
    assert db_session.get(Lote, otro_lote.id).estado is EstadoLote.PUBLICADO
    assert _contar_convocatorias(db_session, emergencia.id) == 1


@pytest.mark.parametrize("con_lote_publicado", [False, True])
def test_rechaza_publicar_sin_lotes_en_borrador(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
    con_lote_publicado: bool,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    if con_lote_publicado:
        _lote(db_session, emergencia, coordinador, estado=EstadoLote.PUBLICADO)
    db_session.flush()
    csrf = _autenticar(client, coordinador)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/publicar",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 409
    db_session.expire_all()
    emergencia_guardada = db_session.get(Emergencia, emergencia.id)
    assert emergencia_guardada is not None
    assert emergencia_guardada.estado is EstadoEmergencia.REGISTRADA
    assert _contar_convocatorias(db_session, emergencia.id) == 0


def test_rechaza_publicar_emergencia_sin_centro_asignado(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
) -> None:
    _lote(db_session, emergencia, coordinador)
    csrf = _autenticar(client, coordinador)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/publicar",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 403
    assert _contar_convocatorias(db_session, emergencia.id) == 0


def test_rechaza_publicar_centro_distinto(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
) -> None:
    otro_centro = Organizacion(
        tipo=TipoOrganizacion.CENTRO_COORDINADOR,
        nombre="Otro centro",
    )
    db_session.add(otro_centro)
    db_session.flush()
    emergencia.centro_coordinador_id = otro_centro.id
    _lote(db_session, emergencia, coordinador)
    db_session.flush()
    csrf = _autenticar(client, coordinador)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/publicar",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 403
    assert _contar_convocatorias(db_session, emergencia.id) == 0


def test_rechaza_publicar_emergencia_ya_publicada(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    _lote(db_session, emergencia, coordinador)
    db_session.flush()
    csrf = _autenticar(client, coordinador)

    primera = client.post(
        f"/api/v1/emergencias/{emergencia.id}/publicar",
        headers={"X-CSRF-Token": csrf},
    )
    assert primera.status_code == 201

    segunda = client.post(
        f"/api/v1/emergencias/{emergencia.id}/publicar",
        headers={"X-CSRF-Token": csrf},
    )

    assert segunda.status_code == 409
    assert _contar_convocatorias(db_session, emergencia.id) == 1


def test_exige_sesion_y_csrf(
    client: TestClient, db_session: Session, emergencia: Emergencia
) -> None:
    response = client.post(f"/api/v1/emergencias/{emergencia.id}/publicar")

    assert response.status_code == 401
    assert _contar_convocatorias(db_session, emergencia.id) == 0


@pytest.mark.parametrize("token", [None, "token-invalido"])
def test_exige_csrf_vigente(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
    token: str | None,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    _lote(db_session, emergencia, coordinador)
    db_session.flush()
    _autenticar(client, coordinador)
    headers = {"X-CSRF-Token": token} if token is not None else {}

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/publicar",
        headers=headers,
    )

    assert response.status_code == 403
    assert _contar_convocatorias(db_session, emergencia.id) == 0


@pytest.mark.parametrize(
    "rol",
    [
        RolUsuario.OPERADOR_MUNICIPAL,
        RolUsuario.REPRESENTANTE_ONG,
        RolUsuario.AUDITOR_DIRECTIVO,
    ],
)
def test_deniega_roles_no_autorizados(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    usuarios_denegados: dict[RolUsuario, Usuario],
    rol: RolUsuario,
) -> None:
    csrf = _autenticar(client, usuarios_denegados[rol])

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/publicar",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 403
    assert _contar_convocatorias(db_session, emergencia.id) == 0


def test_rechaza_emergencia_inexistente(
    client: TestClient, db_session: Session, coordinador: Usuario
) -> None:
    csrf = _autenticar(client, coordinador)

    response = client.post(
        "/api/v1/emergencias/999999/publicar",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 404


def test_hace_rollback_ante_fallo_de_persistencia(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    lote = _lote(db_session, emergencia, coordinador)
    # Confirma el estado previo antes de parchear `commit`: el rollback que
    # dispara el servicio solo debe deshacer lo intentado en esta petición,
    # no los datos ya asentados por la sesión de la prueba.
    db_session.commit()
    csrf = _autenticar(client, coordinador)

    def commit_fallido() -> None:
        raise IntegrityError("INSERT", {}, Exception("restricción simulada"))

    monkeypatch.setattr(db_session, "commit", commit_fallido)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/publicar",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422
    db_session.rollback()
    db_session.expire_all()
    lote_guardado = db_session.get(Lote, lote.id)
    emergencia_guardada = db_session.get(Emergencia, emergencia.id)
    assert lote_guardado is not None
    assert lote_guardado.estado is EstadoLote.BORRADOR
    assert emergencia_guardada is not None
    assert emergencia_guardada.estado is EstadoEmergencia.REGISTRADA
    assert _contar_convocatorias(db_session, emergencia.id) == 0


def test_servicio_rechaza_coordinador_sin_centro(
    db_session: Session, emergencia: Emergencia
) -> None:
    coordinador_suelto = Usuario(
        organizacion_id=None,
        email="suelto-convocatorias@centro.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.COORDINADOR_REGIONAL,
    )

    with pytest.raises(servicio_convocatorias.CentroNoAutorizadoError):
        servicio_convocatorias.publicar_convocatoria(
            db_session, coordinador_suelto, emergencia.id
        )


def test_openapi_documenta_publicar_convocatoria(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    operacion = response.json()["paths"][
        "/api/v1/emergencias/{emergencia_id}/publicar"
    ]["post"]
    assert operacion["responses"]["201"]["description"]
    assert operacion["summary"]
    assert operacion["description"]
