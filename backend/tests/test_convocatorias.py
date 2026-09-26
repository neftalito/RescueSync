"""Pruebas del endpoint de publicación de convocatorias."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
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
    ConvocatoriaLote,
    Emergencia,
    EstadoConvocatoria,
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


def _convocatoria(
    db_session: Session,
    emergencia: Emergencia,
    *,
    numero: int = 1,
    estado: EstadoConvocatoria = EstadoConvocatoria.ABIERTA,
    publicada_en: datetime | None = None,
    horas: int = 1,
) -> Convocatoria:
    """Crea una convocatoria ya persistida con su fecha de publicación fijada."""

    inicio = publicada_en or datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    convocatoria = Convocatoria(
        emergencia_id=emergencia.id,
        numero=numero,
        estado=estado,
        publicada_en=inicio,
        cierra_en=inicio + timedelta(hours=horas),
        cerrada_en=inicio if estado is EstadoConvocatoria.CERRADA else None,
    )
    db_session.add(convocatoria)
    db_session.flush()
    db_session.refresh(convocatoria)
    return convocatoria


def _publicar_lote(
    db_session: Session,
    convocatoria: Convocatoria,
    lote: Lote,
) -> ConvocatoriaLote:
    """Snapshotea un lote en la convocatoria como lo hace la publicación."""

    publicacion = ConvocatoriaLote(
        convocatoria_id=convocatoria.id,
        lote_id=lote.id,
        cantidad_publicada=lote.cantidad_requerida,
        unidad_publicada=lote.unidad,
    )
    lote.estado = EstadoLote.PUBLICADO
    db_session.add(publicacion)
    db_session.flush()
    return publicacion


def test_lista_las_convocatorias_del_centro_con_su_conteo_de_lotes(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    convocatoria = _convocatoria(db_session, emergencia)
    _publicar_lote(
        db_session, convocatoria, _lote(db_session, emergencia, coordinador, "Agua")
    )
    _publicar_lote(
        db_session,
        convocatoria,
        _lote(db_session, emergencia, coordinador, "Abrigo", EstadoLote.PUBLICADO),
    )
    _autenticar(client, coordinador)

    response = client.get("/api/v1/convocatorias")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": convocatoria.id,
                "emergencia_id": emergencia.id,
                "numero": 1,
                "estado": "ABIERTA",
                "publicada_en": "2026-09-20T12:00:00Z",
                "cierra_en": "2026-09-20T13:00:00Z",
                "cantidad_lotes": 2,
                "gravedad": "ALTA",
                "zona": "Ribera norte",
            }
        ]
    }


def test_lista_de_mas_reciente_a_mas_antigua(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    antigua = _convocatoria(
        db_session,
        emergencia,
        numero=1,
        estado=EstadoConvocatoria.CERRADA,
        publicada_en=datetime(2026, 9, 18, 9, 0, tzinfo=UTC),
    )
    reciente = _convocatoria(
        db_session,
        emergencia,
        numero=2,
        publicada_en=datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
    )
    _autenticar(client, coordinador)

    response = client.get("/api/v1/convocatorias")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [
        reciente.id,
        antigua.id,
    ]


def test_no_lista_convocatorias_de_otros_centros(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    operador: Usuario,
) -> None:
    otro_emergencia = Emergencia(
        municipio_id=emergencia.municipio_id,
        creada_por_usuario_id=operador.id,
        gravedad=GravedadEmergencia.BAJA,
        zona="Barrio sur",
        descripcion="Corte de luz",
    )
    db_session.add(otro_emergencia)
    db_session.flush()
    _convocatoria(db_session, emergencia, numero=1)
    ajena = _convocatoria(db_session, otro_emergencia, numero=1)
    _autenticar(client, coordinador)

    response = client.get("/api/v1/convocatorias")

    assert response.status_code == 200
    assert ajena.id not in [item["id"] for item in response.json()["items"]]
    assert response.json()["items"] == []


def test_filtra_el_listado_por_estado(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    cerrada = _convocatoria(
        db_session,
        emergencia,
        numero=1,
        estado=EstadoConvocatoria.CERRADA,
        publicada_en=datetime(2026, 9, 18, 9, 0, tzinfo=UTC),
    )
    _autenticar(client, coordinador)

    sin_filtro = client.get("/api/v1/convocatorias")
    abierta = client.get("/api/v1/convocatorias?estado=ABIERTA")
    cerrada_response = client.get("/api/v1/convocatorias?estado=CERRADA")

    assert sin_filtro.json()["items"] == [
        {
            "id": cerrada.id,
            "emergencia_id": emergencia.id,
            "numero": 1,
            "estado": "CERRADA",
            "publicada_en": "2026-09-18T09:00:00Z",
            "cierra_en": "2026-09-18T10:00:00Z",
            "cantidad_lotes": 0,
            "gravedad": "ALTA",
            "zona": "Ribera norte",
        }
    ]
    assert abierta.json()["items"] == []
    assert [item["id"] for item in cerrada_response.json()["items"]] == [cerrada.id]


def test_rechaza_estado_desconocido_en_el_filtro(
    client: TestClient, coordinador: Usuario
) -> None:
    _autenticar(client, coordinador)

    response = client.get("/api/v1/convocatorias?estado=PUBLICADA")

    assert response.status_code == 422


def test_exige_sesion_para_listar_convocatorias(client: TestClient) -> None:
    response = client.get("/api/v1/convocatorias")

    assert response.status_code == 401


def test_no_exige_csrf_para_listar_convocatorias(
    client: TestClient, coordinador: Usuario
) -> None:
    _autenticar(client, coordinador)

    response = client.get("/api/v1/convocatorias")

    assert response.status_code == 200


def test_servicio_rechaza_listar_convocatorias_sin_centro(
    db_session: Session, emergencia: Emergencia
) -> None:
    # Un coordinador sin centro no llega al endpoint: `obtener_usuario_actual`
    # ya invalida la sesión. La defensa vive en el servicio, como en la
    # publicación, y se verifica sin persistir el usuario para no chocar con el
    # trigger que exige organización a ese rol.
    coordinador_suelto = Usuario(
        organizacion_id=None,
        email="suelto-listado-convocatorias@centro.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.COORDINADOR_REGIONAL,
    )

    with pytest.raises(servicio_convocatorias.CentroNoAutorizadoError):
        servicio_convocatorias.listar_convocatorias(db_session, coordinador_suelto)


@pytest.mark.parametrize(
    "rol",
    [
        RolUsuario.OPERADOR_MUNICIPAL,
        RolUsuario.REPRESENTANTE_ONG,
        RolUsuario.AUDITOR_DIRECTIVO,
    ],
)
def test_deniega_listar_convocatorias_a_otros_roles(
    client: TestClient,
    usuarios_denegados: dict[RolUsuario, Usuario],
    rol: RolUsuario,
) -> None:
    _autenticar(client, usuarios_denegados[rol])

    response = client.get("/api/v1/convocatorias")

    assert response.status_code == 403


def test_openapi_documenta_listar_convocatorias(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    operacion = response.json()["paths"]["/api/v1/convocatorias"]["get"]
    assert operacion["summary"]
    assert operacion["description"]
    assert "estado" in {param["name"] for param in operacion["parameters"]}
