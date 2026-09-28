from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from psycopg import Error as PsycopgError
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
from app.schemas.lote import LoteItem
from app.services import lotes as servicio_lotes

PASSWORD = "Una-clave-segura-2026"


@pytest.fixture
def municipio(db_session: Session) -> Organizacion:
    organizacion = Organizacion(
        tipo=TipoOrganizacion.MUNICIPIO,
        nombre="Municipio de Lotes",
    )
    db_session.add(organizacion)
    db_session.flush()
    return organizacion


@pytest.fixture
def operador(db_session: Session, municipio: Organizacion) -> Usuario:
    usuario = Usuario(
        organizacion_id=municipio.id,
        email="operador-lotes@municipio.org",
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
        nombre="Centro de Lotes",
    )
    db_session.add(organizacion)
    db_session.flush()
    return organizacion


@pytest.fixture
def coordinador(db_session: Session, centro: Organizacion) -> Usuario:
    usuario = Usuario(
        organizacion_id=centro.id,
        email="coordinador-lotes@centro.org",
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
    """Usuarios vigentes de roles que no gestionan lotes."""

    password_hash = generar_password_hash(PASSWORD)
    ong = Organizacion(tipo=TipoOrganizacion.ONG, nombre="ONG de Lotes")
    db_session.add(ong)
    db_session.flush()
    contextos: dict[RolUsuario, tuple[int | None, str]] = {
        RolUsuario.OPERADOR_MUNICIPAL: (municipio.id, "municipal-lotes@santafe.org"),
        RolUsuario.REPRESENTANTE_ONG: (ong.id, "ong-lotes@rescuesync.org"),
        RolUsuario.AUDITOR_DIRECTIVO: (None, "auditor-lotes@rescuesync.org"),
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


def _contar_lotes(db_session: Session) -> int:
    return db_session.scalar(select(func.count()).select_from(Lote)) or 0


def _contar_convocatorias(db_session: Session, emergencia_id: int) -> int:
    return (
        db_session.scalar(
            select(func.count())
            .select_from(Convocatoria)
            .where(Convocatoria.emergencia_id == emergencia_id)
        )
        or 0
    )


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


def test_crea_uno_o_mas_lotes_en_borrador_sin_publicar(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
) -> None:
    csrf = _autenticar(client, coordinador)
    iniciales = _contar_lotes(db_session)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/lotes",
        json={
            "lotes": [
                {
                    "tipo_necesidad": "Agua potable",
                    "descripcion": "Agua apta para consumo",
                    "cantidad_requerida": 5000,
                    "unidad": "litros",
                },
                {
                    "tipo_necesidad": "Alimentos",
                    "cantidad_requerida": 1000,
                    "unidad": "raciones",
                },
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 201
    payload = response.json()
    assert len(payload) == 2
    assert [item["tipo_necesidad"] for item in payload] == [
        "Agua potable",
        "Alimentos",
    ]
    assert {item["estado"] for item in payload} == {EstadoLote.BORRADOR.value}
    assert all(
        item["emergencia_id"] == emergencia.id
        and item["creado_por_usuario_id"] == coordinador.id
        for item in payload
    )
    assert _contar_lotes(db_session) == iniciales + 2

    db_session.expire_all()
    emergencia_guardada = db_session.get(Emergencia, emergencia.id)
    assert emergencia_guardada is not None
    assert emergencia_guardada.estado is EstadoEmergencia.REGISTRADA
    assert emergencia_guardada.centro_coordinador_id == coordinador.organizacion_id
    assert _contar_convocatorias(db_session, emergencia.id) == 0


def test_edita_lote_en_borrador_sin_crear_filas(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
) -> None:
    # Representa un lote que otra transacción confirmó después de que esta
    # consulta leyó la emergencia todavía sin centro asignado.
    lote = _lote(db_session, emergencia, coordinador)
    csrf = _autenticar(client, coordinador)
    iniciales = _contar_lotes(db_session)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/lotes",
        json={
            "lotes": [
                {
                    "id": lote.id,
                    "version": lote.version,
                    "tipo_necesidad": "Agua potable",
                    "descripcion": "Agua embotellada",
                    "cantidad_requerida": 8000,
                    "unidad": "litros",
                }
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 201
    assert response.json()[0]["id"] == lote.id
    assert response.json()[0]["version"] == 2
    assert Decimal(response.json()[0]["cantidad_requerida"]) == Decimal(8000)
    assert response.json()[0]["estado"] == EstadoLote.BORRADOR.value
    assert _contar_lotes(db_session) == iniciales
    assert _contar_convocatorias(db_session, emergencia.id) == 0


def test_rechaza_edicion_con_version_obsoleta_sin_pisar_cambios(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
) -> None:
    lote = _lote(db_session, emergencia, coordinador)
    csrf = _autenticar(client, coordinador)
    url = f"/api/v1/emergencias/{emergencia.id}/lotes"

    primera = client.post(
        url,
        json={
            "lotes": [
                {
                    "id": lote.id,
                    "version": 1,
                    "tipo_necesidad": "Agua potable",
                    "cantidad_requerida": 8000,
                    "unidad": "litros",
                }
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )
    obsoleta = client.post(
        url,
        json={
            "lotes": [
                {
                    "id": lote.id,
                    "version": 1,
                    "tipo_necesidad": "Agua potable",
                    "cantidad_requerida": 9999,
                    "unidad": "litros",
                }
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert primera.status_code == 201
    assert primera.json()[0]["version"] == 2
    assert obsoleta.status_code == 409
    assert "cambió desde que lo consultaste" in obsoleta.json()["detail"]
    db_session.expire_all()
    guardado = db_session.get(Lote, lote.id)
    assert guardado is not None
    assert guardado.cantidad_requerida == Decimal(8000)
    assert guardado.version == 2


def test_rechaza_edicion_sin_version(
    client: TestClient,
    emergencia: Emergencia,
    coordinador: Usuario,
    db_session: Session,
) -> None:
    lote = _lote(db_session, emergencia, coordinador)
    csrf = _autenticar(client, coordinador)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/lotes",
        json={
            "lotes": [
                {
                    "id": lote.id,
                    "tipo_necesidad": "Agua potable",
                    "cantidad_requerida": 8000,
                    "unidad": "litros",
                }
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422
    db_session.expire_all()
    guardado = db_session.get(Lote, lote.id)
    assert guardado is not None
    assert guardado.cantidad_requerida == Decimal(1000)
    assert guardado.version == 1


def test_crea_y_edita_en_la_misma_operacion_atomica(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
) -> None:
    lote = _lote(db_session, emergencia, coordinador, tipo="Abrigo")
    csrf = _autenticar(client, coordinador)
    iniciales = _contar_lotes(db_session)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/lotes",
        json={
            "lotes": [
                {
                    "id": lote.id,
                    "version": lote.version,
                    "tipo_necesidad": "Abrigo",
                    "cantidad_requerida": 200,
                    "unidad": "mantas",
                },
                {
                    "tipo_necesidad": "Medicamentos",
                    "cantidad_requerida": 50,
                    "unidad": "cajas",
                },
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 201
    assert len(response.json()) == 2
    assert _contar_lotes(db_session) == iniciales + 1


@pytest.mark.parametrize(
    "lotes",
    [
        [
            {
                "tipo_necesidad": "Agua",
                "cantidad_requerida": 0,
                "unidad": "litros",
            }
        ],
        [
            {
                "tipo_necesidad": "Agua",
                "cantidad_requerida": -10,
                "unidad": "litros",
            }
        ],
        [
            {
                "tipo_necesidad": "",
                "cantidad_requerida": 10,
                "unidad": "litros",
            }
        ],
        [
            {
                "tipo_necesidad": "   ",
                "cantidad_requerida": 10,
                "unidad": "litros",
            }
        ],
        [
            {
                "tipo_necesidad": "Agua",
                "cantidad_requerida": 10,
                "unidad": "",
            }
        ],
        [
            {
                "tipo_necesidad": "Agua",
                "cantidad_requerida": 1.2345,
                "unidad": "litros",
            }
        ],
        [
            {
                "tipo_necesidad": "x" * 121,
                "cantidad_requerida": 10,
                "unidad": "litros",
            }
        ],
        [
            {
                "tipo_necesidad": "Agua",
                "cantidad_requerida": 10,
                "unidad": "x" * 41,
            }
        ],
        [],
        [
            {
                "tipo_necesidad": "Agua",
                "cantidad_requerida": 10,
                "unidad": "litros",
            },
            {
                "tipo_necesidad": "Válido pero atómico",
                "cantidad_requerida": 0,
                "unidad": "litros",
            },
        ],
    ],
)
def test_rechaza_lotes_invalidos_sin_persistir_nada(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    lotes: list[dict[str, object]],
) -> None:
    csrf = _autenticar(client, coordinador)
    iniciales = _contar_lotes(db_session)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/lotes",
        json={"lotes": lotes},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422
    assert _contar_lotes(db_session) == iniciales
    assert _contar_convocatorias(db_session, emergencia.id) == 0


def test_rechaza_emergencia_inexistente(
    client: TestClient, db_session: Session, coordinador: Usuario
) -> None:
    csrf = _autenticar(client, coordinador)
    iniciales = _contar_lotes(db_session)

    response = client.post(
        "/api/v1/emergencias/999999/lotes",
        json={
            "lotes": [
                {
                    "tipo_necesidad": "Agua",
                    "cantidad_requerida": 10,
                    "unidad": "litros",
                }
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 404
    assert _contar_lotes(db_session) == iniciales


def test_rechaza_lote_ajeno_a_la_emergencia(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    municipio: Organizacion,
    operador: Usuario,
) -> None:
    otra = Emergencia(
        municipio_id=municipio.id,
        creada_por_usuario_id=operador.id,
        gravedad=GravedadEmergencia.MEDIA,
        zona="Otra zona",
        descripcion="Otra emergencia",
    )
    db_session.add(otra)
    db_session.flush()
    ajeno = _lote(db_session, otra, coordinador)
    csrf = _autenticar(client, coordinador)
    iniciales = _contar_lotes(db_session)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/lotes",
        json={
            "lotes": [
                {
                    "id": ajeno.id,
                    "version": ajeno.version,
                    "tipo_necesidad": "Agua",
                    "cantidad_requerida": 10,
                    "unidad": "litros",
                }
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 404
    assert _contar_lotes(db_session) == iniciales


def test_rechaza_editar_lote_publicado(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
) -> None:
    lote = _lote(db_session, emergencia, coordinador, estado=EstadoLote.PUBLICADO)
    csrf = _autenticar(client, coordinador)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/lotes",
        json={
            "lotes": [
                {
                    "id": lote.id,
                    "version": lote.version,
                    "tipo_necesidad": "Agua potable",
                    "cantidad_requerida": 9999,
                    "unidad": "litros",
                }
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 409
    db_session.expire_all()
    assert db_session.get(Lote, lote.id) is not None
    assert db_session.get(Lote, lote.id).cantidad_requerida == Decimal(1000)


def test_exige_sesion_y_csrf(
    client: TestClient, db_session: Session, emergencia: Emergencia
) -> None:
    cuerpo = {
        "lotes": [
            {"tipo_necesidad": "Agua", "cantidad_requerida": 10, "unidad": "litros"}
        ]
    }
    iniciales = _contar_lotes(db_session)

    sin_sesion = client.post(f"/api/v1/emergencias/{emergencia.id}/lotes", json=cuerpo)

    assert sin_sesion.status_code == 401
    assert _contar_lotes(db_session) == iniciales


@pytest.mark.parametrize("token", [None, "token-invalido"])
def test_exige_csrf_vigente(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    token: str | None,
) -> None:
    _autenticar(client, coordinador)
    headers = {"X-CSRF-Token": token} if token is not None else {}
    iniciales = _contar_lotes(db_session)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/lotes",
        json={
            "lotes": [
                {
                    "tipo_necesidad": "Agua",
                    "cantidad_requerida": 10,
                    "unidad": "litros",
                }
            ]
        },
        headers=headers,
    )

    assert response.status_code == 403
    assert _contar_lotes(db_session) == iniciales


@pytest.mark.parametrize(
    "rol",
    [
        RolUsuario.OPERADOR_MUNICIPAL,
        RolUsuario.REPRESENTANTE_ONG,
        RolUsuario.AUDITOR_DIRECTIVO,
    ],
)
def test_deniega_roles_que_no_gestionan_lotes(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    usuarios_denegados: dict[RolUsuario, Usuario],
    rol: RolUsuario,
) -> None:
    csrf = _autenticar(client, usuarios_denegados[rol])
    iniciales = _contar_lotes(db_session)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/lotes",
        json={
            "lotes": [
                {
                    "tipo_necesidad": "Agua",
                    "cantidad_requerida": 10,
                    "unidad": "litros",
                }
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 403
    assert _contar_lotes(db_session) == iniciales


def test_deniega_centro_distinto_del_asignado(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
) -> None:
    otro_centro = Organizacion(
        tipo=TipoOrganizacion.CENTRO_COORDINADOR,
        nombre="Otro centro",
    )
    db_session.add(otro_centro)
    db_session.flush()
    emergencia.centro_coordinador_id = otro_centro.id
    db_session.flush()
    csrf = _autenticar(client, coordinador)
    iniciales = _contar_lotes(db_session)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/lotes",
        json={
            "lotes": [
                {
                    "tipo_necesidad": "Agua",
                    "cantidad_requerida": 10,
                    "unidad": "litros",
                }
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 403
    assert _contar_lotes(db_session) == iniciales


def test_primer_centro_reclama_emergencia_y_otro_no_edita_sus_lotes(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
) -> None:
    otro_centro = Organizacion(
        tipo=TipoOrganizacion.CENTRO_COORDINADOR,
        nombre="Centro competidor",
    )
    db_session.add(otro_centro)
    db_session.flush()
    otro_coordinador = Usuario(
        organizacion_id=otro_centro.id,
        email="otro-coordinador@centro.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.COORDINADOR_REGIONAL,
    )
    db_session.add(otro_coordinador)
    db_session.flush()

    csrf = _autenticar(client, coordinador)
    alta = client.post(
        f"/api/v1/emergencias/{emergencia.id}/lotes",
        json={
            "lotes": [
                {
                    "tipo_necesidad": "Agua",
                    "cantidad_requerida": 10,
                    "unidad": "litros",
                }
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert alta.status_code == 201
    lote_id = alta.json()[0]["id"]
    lote_version = alta.json()[0]["version"]
    db_session.expire_all()
    emergencia_asignada = db_session.get(Emergencia, emergencia.id)
    assert emergencia_asignada is not None
    assert emergencia_asignada.centro_coordinador_id == coordinador.organizacion_id

    csrf_otro = _autenticar(client, otro_coordinador)
    edicion = client.post(
        f"/api/v1/emergencias/{emergencia.id}/lotes",
        json={
            "lotes": [
                {
                    "id": lote_id,
                    "version": lote_version,
                    "tipo_necesidad": "Agua",
                    "cantidad_requerida": 999,
                    "unidad": "litros",
                }
            ]
        },
        headers={"X-CSRF-Token": csrf_otro},
    )

    assert edicion.status_code == 403
    db_session.expire_all()
    lote = db_session.get(Lote, lote_id)
    assert lote is not None
    assert lote.cantidad_requerida == Decimal(10)


def test_permite_centro_asignado(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    db_session.flush()
    csrf = _autenticar(client, coordinador)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/lotes",
        json={
            "lotes": [
                {
                    "tipo_necesidad": "Agua",
                    "cantidad_requerida": 10,
                    "unidad": "litros",
                }
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 201


def test_hace_rollback_ante_fallo_de_persistencia(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csrf = _autenticar(client, coordinador)
    iniciales = _contar_lotes(db_session)

    def commit_fallido() -> None:
        raise IntegrityError("INSERT", {}, Exception("restricción simulada"))

    monkeypatch.setattr(db_session, "commit", commit_fallido)

    response = client.post(
        f"/api/v1/emergencias/{emergencia.id}/lotes",
        json={
            "lotes": [
                {
                    "tipo_necesidad": "Agua",
                    "cantidad_requerida": 10,
                    "unidad": "litros",
                }
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422
    db_session.rollback()
    assert _contar_lotes(db_session) == iniciales


def test_lista_borradores_y_publicados_del_centro_asignado(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
    municipio: Organizacion,
    operador: Usuario,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    db_session.flush()
    borrador = _lote(db_session, emergencia, coordinador, tipo="Agua potable")
    publicado = _lote(
        db_session,
        emergencia,
        coordinador,
        tipo="Colchones",
        estado=EstadoLote.PUBLICADO,
    )
    otra = Emergencia(
        municipio_id=municipio.id,
        creada_por_usuario_id=operador.id,
        gravedad=GravedadEmergencia.BAJA,
        zona="Otra zona",
        descripcion="Otra emergencia",
        centro_coordinador_id=centro.id,
    )
    db_session.add(otra)
    db_session.flush()
    _lote(db_session, otra, coordinador, tipo="Ajeno")
    _autenticar(client, coordinador)

    response = client.get(f"/api/v1/emergencias/{emergencia.id}/lotes")

    assert response.status_code == 200
    payload = response.json()
    assert [(item["id"], item["estado"]) for item in payload] == [
        (borrador.id, EstadoLote.BORRADOR.value),
        (publicado.id, EstadoLote.PUBLICADO.value),
    ]
    assert payload[0]["tipo_necesidad"] == "Agua potable"
    assert payload[0]["descripcion"] == "Necesidad prioritaria"
    assert Decimal(payload[0]["cantidad_requerida"]) == Decimal(1000)
    assert payload[0]["unidad"] == "litros"


def test_lista_lo_guardado_para_retomar_la_edicion(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
) -> None:
    csrf = _autenticar(client, coordinador)
    alta = client.post(
        f"/api/v1/emergencias/{emergencia.id}/lotes",
        json={
            "lotes": [
                {
                    "tipo_necesidad": "Agua",
                    "cantidad_requerida": 10,
                    "unidad": "litros",
                }
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert alta.status_code == 201

    consulta = client.get(f"/api/v1/emergencias/{emergencia.id}/lotes")

    assert consulta.status_code == 200
    assert consulta.json() == alta.json()


def test_lista_vacia_sin_reclamar_emergencia_sin_centro(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
) -> None:
    lote = _lote(db_session, emergencia, coordinador)
    _autenticar(client, coordinador)

    response = client.get(f"/api/v1/emergencias/{emergencia.id}/lotes")

    assert response.status_code == 200
    assert response.json() == []
    assert db_session.get(Lote, lote.id) is not None
    db_session.expire_all()
    emergencia_guardada = db_session.get(Emergencia, emergencia.id)
    assert emergencia_guardada is not None
    assert emergencia_guardada.centro_coordinador_id is None


def test_listar_rechaza_emergencia_inexistente(
    client: TestClient, coordinador: Usuario
) -> None:
    _autenticar(client, coordinador)

    response = client.get("/api/v1/emergencias/999999/lotes")

    assert response.status_code == 404


def test_listar_deniega_centro_distinto_del_asignado(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
) -> None:
    otro_centro = Organizacion(
        tipo=TipoOrganizacion.CENTRO_COORDINADOR,
        nombre="Centro ajeno",
    )
    db_session.add(otro_centro)
    db_session.flush()
    emergencia.centro_coordinador_id = otro_centro.id
    db_session.flush()
    _lote(db_session, emergencia, coordinador)
    _autenticar(client, coordinador)

    response = client.get(f"/api/v1/emergencias/{emergencia.id}/lotes")

    assert response.status_code == 403
    assert "Agua potable" not in response.text


def test_listar_exige_sesion(client: TestClient, emergencia: Emergencia) -> None:
    response = client.get(f"/api/v1/emergencias/{emergencia.id}/lotes")

    assert response.status_code == 401


@pytest.mark.parametrize(
    "rol",
    [
        RolUsuario.OPERADOR_MUNICIPAL,
        RolUsuario.AUDITOR_DIRECTIVO,
    ],
)
def test_listar_deniega_roles_que_no_consultan_lotes(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    usuarios_denegados: dict[RolUsuario, Usuario],
    rol: RolUsuario,
) -> None:
    _lote(db_session, emergencia, coordinador)
    _autenticar(client, usuarios_denegados[rol])

    response = client.get(f"/api/v1/emergencias/{emergencia.id}/lotes")

    assert response.status_code == 403
    assert "Agua potable" not in response.text


def test_listar_ong_ve_solo_lotes_publicados(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    usuarios_denegados: dict[RolUsuario, Usuario],
) -> None:
    _lote(db_session, emergencia, coordinador, tipo="Sin publicar")
    publicado = _lote(
        db_session,
        emergencia,
        coordinador,
        tipo="Agua potable",
        estado=EstadoLote.PUBLICADO,
    )
    _autenticar(client, usuarios_denegados[RolUsuario.REPRESENTANTE_ONG])

    response = client.get(f"/api/v1/emergencias/{emergencia.id}/lotes")

    assert response.status_code == 200
    cuerpo = response.json()
    assert [lote["id"] for lote in cuerpo] == [publicado.id]
    assert "Sin publicar" not in response.text


def test_servicio_listar_rechaza_ong_sin_organizacion(
    db_session: Session, emergencia: Emergencia
) -> None:
    representante_suelto = Usuario(
        organizacion_id=None,
        email="suelto-listar-ong@rescuesync.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.REPRESENTANTE_ONG,
    )

    with pytest.raises(servicio_lotes.OngNoAutorizadaError):
        servicio_lotes.listar_lotes(db_session, representante_suelto, emergencia.id)


def test_servicio_listar_rechaza_coordinador_sin_centro(
    db_session: Session, emergencia: Emergencia
) -> None:
    coordinador_suelto = Usuario(
        organizacion_id=None,
        email="suelto-listar@centro.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.COORDINADOR_REGIONAL,
    )

    with pytest.raises(servicio_lotes.CentroNoAutorizadoError):
        servicio_lotes.listar_lotes(db_session, coordinador_suelto, emergencia.id)


def _url_lote(emergencia: Emergencia, lote_id: int) -> str:
    return f"/api/v1/emergencias/{emergencia.id}/lotes/{lote_id}"


def test_elimina_borrador_y_conserva_los_demas(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    db_session.flush()
    eliminado = _lote(db_session, emergencia, coordinador, tipo="Agua potable")
    conservado = _lote(db_session, emergencia, coordinador, tipo="Abrigo")
    csrf = _autenticar(client, coordinador)

    response = client.delete(
        _url_lote(emergencia, eliminado.id), headers={"X-CSRF-Token": csrf}
    )

    assert response.status_code == 204
    assert response.content == b""
    listado = client.get(f"/api/v1/emergencias/{emergencia.id}/lotes")
    assert [item["id"] for item in listado.json()] == [conservado.id]
    db_session.expire_all()
    assert db_session.get(Lote, eliminado.id) is None
    emergencia_guardada = db_session.get(Emergencia, emergencia.id)
    assert emergencia_guardada is not None
    assert emergencia_guardada.estado is EstadoEmergencia.REGISTRADA
    assert _contar_convocatorias(db_session, emergencia.id) == 0


def test_eliminar_dos_veces_responde_no_encontrado(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    db_session.flush()
    lote = _lote(db_session, emergencia, coordinador)
    csrf = _autenticar(client, coordinador)

    primera = client.delete(
        _url_lote(emergencia, lote.id), headers={"X-CSRF-Token": csrf}
    )
    segunda = client.delete(
        _url_lote(emergencia, lote.id), headers={"X-CSRF-Token": csrf}
    )

    assert primera.status_code == 204
    assert segunda.status_code == 404


@pytest.mark.parametrize(
    "estado",
    [EstadoLote.PUBLICADO, EstadoLote.CERRADO, EstadoLote.CANCELADO],
)
def test_rechaza_eliminar_lote_fuera_de_borrador(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
    estado: EstadoLote,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    db_session.flush()
    lote = _lote(db_session, emergencia, coordinador, estado=estado)
    csrf = _autenticar(client, coordinador)

    response = client.delete(
        _url_lote(emergencia, lote.id), headers={"X-CSRF-Token": csrf}
    )

    assert response.status_code == 409
    db_session.expire_all()
    assert db_session.get(Lote, lote.id) is not None


def test_no_elimina_borrador_referenciado_por_una_convocatoria(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    db_session.flush()
    lote = _lote(db_session, emergencia, coordinador)
    convocatoria = Convocatoria(
        emergencia_id=emergencia.id,
        numero=1,
        cierra_en=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(convocatoria)
    db_session.flush()
    db_session.add(
        ConvocatoriaLote(
            convocatoria_id=convocatoria.id,
            lote_id=lote.id,
            cantidad_publicada=Decimal(1000),
            unidad_publicada="litros",
        )
    )
    # Confirma el escenario para que el rollback del servicio solo deshaga
    # el intento de eliminación.
    db_session.commit()
    csrf = _autenticar(client, coordinador)

    response = client.delete(
        _url_lote(emergencia, lote.id), headers={"X-CSRF-Token": csrf}
    )

    assert response.status_code == 409
    db_session.expire_all()
    assert db_session.get(Lote, lote.id) is not None


def test_rechaza_eliminar_lote_de_otra_emergencia(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
    municipio: Organizacion,
    operador: Usuario,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    otra = Emergencia(
        municipio_id=municipio.id,
        creada_por_usuario_id=operador.id,
        gravedad=GravedadEmergencia.MEDIA,
        zona="Otra zona",
        descripcion="Otra emergencia",
        centro_coordinador_id=centro.id,
    )
    db_session.add(otra)
    db_session.flush()
    ajeno = _lote(db_session, otra, coordinador)
    csrf = _autenticar(client, coordinador)

    response = client.delete(
        _url_lote(emergencia, ajeno.id), headers={"X-CSRF-Token": csrf}
    )

    assert response.status_code == 404
    db_session.expire_all()
    assert db_session.get(Lote, ajeno.id) is not None


def test_eliminar_rechaza_lote_o_emergencia_inexistentes(
    client: TestClient,
    emergencia: Emergencia,
    coordinador: Usuario,
) -> None:
    csrf = _autenticar(client, coordinador)

    sin_lote = client.delete(
        _url_lote(emergencia, 999999), headers={"X-CSRF-Token": csrf}
    )
    sin_emergencia = client.delete(
        "/api/v1/emergencias/999999/lotes/1", headers={"X-CSRF-Token": csrf}
    )

    assert sin_lote.status_code == 404
    assert sin_emergencia.status_code == 404


def test_eliminar_deniega_centro_distinto_del_asignado(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
) -> None:
    otro_centro = Organizacion(
        tipo=TipoOrganizacion.CENTRO_COORDINADOR,
        nombre="Centro que no elimina",
    )
    db_session.add(otro_centro)
    db_session.flush()
    emergencia.centro_coordinador_id = otro_centro.id
    db_session.flush()
    lote = _lote(db_session, emergencia, coordinador)
    csrf = _autenticar(client, coordinador)

    response = client.delete(
        _url_lote(emergencia, lote.id), headers={"X-CSRF-Token": csrf}
    )

    assert response.status_code == 403
    db_session.expire_all()
    assert db_session.get(Lote, lote.id) is not None


def test_eliminar_exige_sesion(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
) -> None:
    lote = _lote(db_session, emergencia, coordinador)

    response = client.delete(_url_lote(emergencia, lote.id))

    assert response.status_code == 401
    assert db_session.get(Lote, lote.id) is not None


@pytest.mark.parametrize("token", [None, "token-invalido"])
def test_eliminar_exige_csrf_vigente(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    centro: Organizacion,
    token: str | None,
) -> None:
    emergencia.centro_coordinador_id = centro.id
    db_session.flush()
    lote = _lote(db_session, emergencia, coordinador)
    _autenticar(client, coordinador)
    headers = {"X-CSRF-Token": token} if token is not None else {}

    response = client.delete(_url_lote(emergencia, lote.id), headers=headers)

    assert response.status_code == 403
    db_session.expire_all()
    assert db_session.get(Lote, lote.id) is not None


@pytest.mark.parametrize(
    "rol",
    [
        RolUsuario.OPERADOR_MUNICIPAL,
        RolUsuario.REPRESENTANTE_ONG,
        RolUsuario.AUDITOR_DIRECTIVO,
    ],
)
def test_eliminar_deniega_roles_que_no_gestionan_lotes(
    client: TestClient,
    db_session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    usuarios_denegados: dict[RolUsuario, Usuario],
    rol: RolUsuario,
) -> None:
    lote = _lote(db_session, emergencia, coordinador)
    csrf = _autenticar(client, usuarios_denegados[rol])

    response = client.delete(
        _url_lote(emergencia, lote.id), headers={"X-CSRF-Token": csrf}
    )

    assert response.status_code == 403
    db_session.expire_all()
    assert db_session.get(Lote, lote.id) is not None


def test_servicio_eliminar_rechaza_coordinador_sin_centro(
    db_session: Session, emergencia: Emergencia, coordinador: Usuario
) -> None:
    lote = _lote(db_session, emergencia, coordinador)
    coordinador_suelto = Usuario(
        organizacion_id=None,
        email="suelto-eliminar@centro.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.COORDINADOR_REGIONAL,
    )

    with pytest.raises(servicio_lotes.CentroNoAutorizadoError):
        servicio_lotes.eliminar_lote(
            db_session, coordinador_suelto, emergencia.id, lote.id
        )


def test_postgresql_rechaza_cantidad_no_positiva(
    db_session: Session, emergencia: Emergencia, coordinador: Usuario
) -> None:
    db_session.add(
        Lote(
            emergencia_id=emergencia.id,
            creado_por_usuario_id=coordinador.id,
            tipo_necesidad="Agua",
            cantidad_requerida=Decimal(0),
            unidad="litros",
        )
    )

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    assert isinstance(error.value.orig, PsycopgError)
    assert error.value.orig.diag.constraint_name == "ck_lote_cantidad_positiva"


def test_postgresql_rechaza_tipo_vacio(
    db_session: Session, emergencia: Emergencia, coordinador: Usuario
) -> None:
    db_session.add(
        Lote(
            emergencia_id=emergencia.id,
            creado_por_usuario_id=coordinador.id,
            tipo_necesidad="   ",
            cantidad_requerida=Decimal(10),
            unidad="litros",
        )
    )

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    assert isinstance(error.value.orig, PsycopgError)
    assert error.value.orig.diag.constraint_name == "ck_lote_tipo_no_vacio"


def test_servicio_rechaza_coordinador_sin_centro(
    db_session: Session, emergencia: Emergencia
) -> None:
    coordinador_suelto = Usuario(
        organizacion_id=None,
        email="suelto@centro.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.COORDINADOR_REGIONAL,
    )

    with pytest.raises(servicio_lotes.CentroNoAutorizadoError):
        servicio_lotes.guardar_lotes(
            db_session,
            coordinador_suelto,
            emergencia.id,
            [
                LoteItem(
                    tipo_necesidad="Agua",
                    cantidad_requerida=Decimal(10),
                    unidad="litros",
                )
            ],
        )


def test_openapi_documenta_lotes_en_borrador(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    operacion = response.json()["paths"]["/api/v1/emergencias/{emergencia_id}/lotes"][
        "post"
    ]
    assert operacion["responses"]["201"]["description"]
    assert operacion["summary"]
    assert operacion["description"]


def test_openapi_documenta_listado_de_lotes(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    operacion = response.json()["paths"]["/api/v1/emergencias/{emergencia_id}/lotes"][
        "get"
    ]
    assert operacion["summary"]
    assert operacion["description"]
    assert {"200", "401", "403", "404"} <= set(operacion["responses"])


def test_openapi_documenta_eliminacion_de_borradores(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    operacion = response.json()["paths"][
        "/api/v1/emergencias/{emergencia_id}/lotes/{lote_id}"
    ]["delete"]
    assert operacion["summary"]
    assert operacion["description"]
    assert {"204", "401", "403", "404", "409"} <= set(operacion["responses"])
