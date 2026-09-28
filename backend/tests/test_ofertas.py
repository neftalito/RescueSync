from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import get_args

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes import ofertas as ofertas_route
from app.core.security import crear_token_csrf, crear_valor_sesion
from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    EstadoConvocatoria,
    EstadoLote,
    EstadoOferta,
    EstadoSincronizacionBonita,
    GravedadEmergencia,
    Lote,
    Oferta,
    OfertaVersion,
    Organizacion,
    RolUsuario,
    TipoAporte,
    TipoOrganizacion,
    Usuario,
)
from app.db.session import get_db
from app.main import app

ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


@dataclass(frozen=True)
class Escenario:
    emergencia: Emergencia
    convocatoria: Convocatoria
    lote_agua: Lote
    lote_kits: Lote
    lote_sin_publicar: Lote
    ong: Organizacion
    representante: Usuario
    otra_ong: Organizacion
    operador_municipal: Usuario


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def usar_sesion_de_prueba() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = usar_sesion_de_prueba
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(ofertas_route.exigir_ong_con_csrf, None)
        usuario_ong_depends = get_args(ofertas_route.UsuarioOng)[1]
        app.dependency_overrides.pop(usuario_ong_depends.dependency, None)


def _autenticar_sin_csrf(client: TestClient, usuario: Usuario) -> None:
    """Bypasea auth + CSRF: usa esto para tests que ejercitan el servicio."""
    app.dependency_overrides[ofertas_route.exigir_ong_con_csrf] = lambda: usuario


def _autenticar_solo_rol(client: TestClient, usuario: Usuario) -> None:
    """Bypasea solo la resolución de usuario/rol; el CSRF corre real."""
    usuario_ong_depends = get_args(ofertas_route.UsuarioOng)[1]
    app.dependency_overrides[usuario_ong_depends.dependency] = lambda: usuario


def _autenticar_con_cookie(client: TestClient, usuario: Usuario) -> str:
    """Autentica con una sesión real (cookie + CSRF), sin overrides de dependencia."""
    client.cookies.set("rescuesync_session", crear_valor_sesion(usuario.id))
    return crear_token_csrf(usuario.id)


def _organizacion(
    session: Session, tipo: TipoOrganizacion, nombre: str
) -> Organizacion:
    organizacion = Organizacion(tipo=tipo, nombre=nombre)
    session.add(organizacion)
    session.flush()
    return organizacion


def _usuario(
    session: Session, organizacion: Organizacion, rol: RolUsuario, email: str
) -> Usuario:
    usuario = Usuario(
        organizacion_id=organizacion.id,
        email=email,
        password_hash=ARGON2_HASH,
        rol=rol,
    )
    session.add(usuario)
    session.flush()
    return usuario


@pytest.fixture
def escenario(db_session: Session) -> Escenario:
    ahora = datetime.now(UTC)
    municipio = _organizacion(db_session, TipoOrganizacion.MUNICIPIO, "Municipio CB")
    ong = _organizacion(db_session, TipoOrganizacion.ONG, "ONG CB")
    otra_ong = _organizacion(db_session, TipoOrganizacion.ONG, "Otra ONG")
    operador = _usuario(
        db_session, municipio, RolUsuario.OPERADOR_MUNICIPAL, "op@cb.org"
    )
    representante = _usuario(
        db_session, ong, RolUsuario.REPRESENTANTE_ONG, "ong@cb.org"
    )
    emergencia = Emergencia(
        municipio_id=municipio.id,
        creada_por_usuario_id=operador.id,
        gravedad=GravedadEmergencia.CRITICA,
        zona="Zona CB",
        descripcion="Emergencia para ofertas",
        bonita_process_instance_id=4242,
        bonita_sync=EstadoSincronizacionBonita.VINCULADA,
    )
    db_session.add(emergencia)
    db_session.flush()

    lote_agua = Lote(
        emergencia_id=emergencia.id,
        creado_por_usuario_id=operador.id,
        tipo_necesidad="Agua",
        cantidad_requerida=Decimal(1000),
        unidad="litros",
        estado=EstadoLote.PUBLICADO,
    )
    lote_kits = Lote(
        emergencia_id=emergencia.id,
        creado_por_usuario_id=operador.id,
        tipo_necesidad="Kits",
        cantidad_requerida=Decimal(10),
        unidad="kits",
        estado=EstadoLote.PUBLICADO,
    )
    lote_sin_publicar = Lote(
        emergencia_id=emergencia.id,
        creado_por_usuario_id=operador.id,
        tipo_necesidad="Mantas",
        cantidad_requerida=Decimal(50),
        unidad="unidades",
    )
    db_session.add_all([lote_agua, lote_kits, lote_sin_publicar])
    db_session.flush()

    convocatoria = Convocatoria(
        emergencia_id=emergencia.id,
        numero=1,
        estado=EstadoConvocatoria.ABIERTA,
        publicada_en=ahora - timedelta(minutes=5),
        cierra_en=ahora + timedelta(days=1),
    )
    db_session.add(convocatoria)
    db_session.flush()

    for lote in (lote_agua, lote_kits):
        db_session.add(
            ConvocatoriaLote(
                convocatoria_id=convocatoria.id,
                lote_id=lote.id,
                cantidad_publicada=lote.cantidad_requerida,
                unidad_publicada=lote.unidad,
            )
        )
    db_session.flush()

    return Escenario(
        emergencia=emergencia,
        convocatoria=convocatoria,
        lote_agua=lote_agua,
        lote_kits=lote_kits,
        lote_sin_publicar=lote_sin_publicar,
        ong=ong,
        representante=representante,
        otra_ong=otra_ong,
        operador_municipal=operador,
    )


def _payload(
    convocatoria_id: int,
    items: list[dict[str, object]],
    observaciones: str | None = "Donación inicial",
) -> dict[str, object]:
    return {
        "convocatoria_id": convocatoria_id,
        "observaciones": observaciones,
        "items": items,
    }


def _item(
    lote_id: int,
    cantidad: object = 500,
    unidad: str = "litros",
    tipo: TipoAporte = TipoAporte.RECURSO,
    descripcion: str = "Bidones de agua potable",
) -> dict[str, object]:
    return {
        "lote_id": lote_id,
        "tipo": tipo.value,
        "descripcion": descripcion,
        "cantidad_ofrecida": cantidad,
        "unidad": unidad,
    }


def _crear(client: TestClient, body: dict[str, object]) -> object:
    return client.post(
        "/api/v1/ofertas",
        json=body,
        headers={"X-CSRF-Token": "token-de-prueba"},
    )


# --- Camino feliz -----------------------------------------------------------


def test_crea_oferta_con_un_item_valido(
    client: TestClient, escenario: Escenario
) -> None:
    _autenticar_sin_csrf(client, escenario.representante)

    body = _payload(
        escenario.convocatoria.id,
        [_item(escenario.lote_agua.id, cantidad=500, unidad="litros")],
    )
    response = _crear(client, body)

    assert response.status_code == 201
    payload = response.json()
    assert payload["estado"] == "PRESENTADA"
    assert payload["version_actual"] == 1
    assert payload["ong_creadora_id"] == escenario.ong.id
    assert payload["creada_por_usuario_id"] == escenario.representante.id
    assert len(payload["items"]) == 1
    assert payload["items"][0]["lote_id"] == escenario.lote_agua.id
    assert payload["items"][0]["unidad"] == "litros"
    assert Decimal(str(payload["items"][0]["cantidad_ofrecida"])) == Decimal(500)


def test_crea_oferta_con_multiples_items_en_distintos_lotes(
    client: TestClient, escenario: Escenario
) -> None:
    _autenticar_sin_csrf(client, escenario.representante)

    body = _payload(
        escenario.convocatoria.id,
        [
            _item(escenario.lote_agua.id, cantidad=200, unidad="litros"),
            _item(
                escenario.lote_kits.id,
                cantidad=3,
                unidad="kits",
                descripcion="Kits de higiene",
            ),
        ],
    )
    response = _crear(client, body)

    assert response.status_code == 201
    assert len(response.json()["items"]) == 2


# --- Reglas de negocio del servicio -----------------------------------------


def test_rechaza_si_el_usuario_no_representa_una_ong(
    client: TestClient, escenario: Escenario
) -> None:
    _autenticar_sin_csrf(client, escenario.operador_municipal)

    body = _payload(
        escenario.convocatoria.id,
        [_item(escenario.lote_agua.id)],
    )
    response = _crear(client, body)

    assert response.status_code == 403


def test_rechaza_convocatoria_inexistente(
    client: TestClient, escenario: Escenario
) -> None:
    _autenticar_sin_csrf(client, escenario.representante)

    body = _payload(999_999_999, [_item(escenario.lote_agua.id)])
    response = _crear(client, body)

    assert response.status_code == 404


def test_rechaza_convocatoria_cerrada(
    client: TestClient, escenario: Escenario, db_session: Session
) -> None:
    escenario.convocatoria.estado = EstadoConvocatoria.CERRADA
    escenario.convocatoria.cerrada_en = datetime.now(UTC)
    db_session.flush()
    _autenticar_sin_csrf(client, escenario.representante)

    body = _payload(escenario.convocatoria.id, [_item(escenario.lote_agua.id)])
    response = _crear(client, body)

    assert response.status_code == 409


def test_rechaza_convocatoria_fuera_de_ventana_aunque_este_abierta(
    client: TestClient, escenario: Escenario, db_session: Session
) -> None:
    escenario.convocatoria.cierra_en = datetime.now(UTC) - timedelta(minutes=1)
    db_session.flush()
    _autenticar_sin_csrf(client, escenario.representante)

    body = _payload(escenario.convocatoria.id, [_item(escenario.lote_agua.id)])
    response = _crear(client, body)

    assert response.status_code == 409


def test_rechaza_lote_no_publicado_en_la_convocatoria(
    client: TestClient, escenario: Escenario
) -> None:
    _autenticar_sin_csrf(client, escenario.representante)

    body = _payload(
        escenario.convocatoria.id,
        [_item(escenario.lote_sin_publicar.id, unidad="unidades")],
    )
    response = _crear(client, body)

    assert response.status_code == 404


def test_rechaza_lote_asociado_que_ya_no_esta_publicado(
    client: TestClient, escenario: Escenario, db_session: Session
) -> None:
    escenario.lote_agua.estado = EstadoLote.CANCELADO
    db_session.commit()
    _autenticar_sin_csrf(client, escenario.representante)

    response = _crear(
        client,
        _payload(
            escenario.convocatoria.id,
            [_item(escenario.lote_agua.id, unidad="litros")],
        ),
    )

    assert response.status_code == 404
    assert "no está publicado" in response.json()["detail"]


def test_rechaza_unidad_que_no_coincide_con_la_publicada(
    client: TestClient, escenario: Escenario
) -> None:
    _autenticar_sin_csrf(client, escenario.representante)

    body = _payload(
        escenario.convocatoria.id,
        [_item(escenario.lote_agua.id, unidad="kg")],
    )
    response = _crear(client, body)

    assert response.status_code == 422


# --- Validación de schema (Pydantic) ----------------------------------------


def test_rechaza_cantidad_ofrecida_no_positiva(
    client: TestClient, escenario: Escenario
) -> None:
    _autenticar_sin_csrf(client, escenario.representante)

    body = _payload(
        escenario.convocatoria.id,
        [_item(escenario.lote_agua.id, cantidad=0)],
    )
    response = _crear(client, body)

    assert response.status_code == 422


def test_rechaza_oferta_sin_items(client: TestClient, escenario: Escenario) -> None:
    _autenticar_sin_csrf(client, escenario.representante)

    body = _payload(escenario.convocatoria.id, [])
    response = _crear(client, body)

    assert response.status_code == 422


def test_rechaza_lotes_duplicados_en_la_misma_oferta(
    client: TestClient, escenario: Escenario
) -> None:
    _autenticar_sin_csrf(client, escenario.representante)

    body = _payload(
        escenario.convocatoria.id,
        [
            _item(escenario.lote_agua.id, cantidad=100),
            _item(escenario.lote_agua.id, cantidad=200),
        ],
    )
    response = _crear(client, body)

    assert response.status_code == 422


# --- Autenticación / CSRF ----------------------------------------------------


def test_rechaza_token_csrf_invalido(client: TestClient, escenario: Escenario) -> None:
    # Deja correr la validación real de CSRF; solo resolvemos el usuario.
    _autenticar_solo_rol(client, escenario.representante)

    body = _payload(escenario.convocatoria.id, [_item(escenario.lote_agua.id)])
    response = client.post(
        "/api/v1/ofertas",
        json=body,
        headers={"X-CSRF-Token": "token-incorrecto"},
    )

    assert response.status_code == 403


def test_rechaza_sin_header_csrf(client: TestClient, escenario: Escenario) -> None:
    _autenticar_solo_rol(client, escenario.representante)

    body = _payload(escenario.convocatoria.id, [_item(escenario.lote_agua.id)])
    response = client.post("/api/v1/ofertas", json=body)

    assert response.status_code == 403


# --- Listado "Mis ofertas" ---------------------------------------------------


def _crear_con_csrf(client: TestClient, body: dict[str, object], csrf: str) -> object:
    return client.post("/api/v1/ofertas", json=body, headers={"X-CSRF-Token": csrf})


def test_lista_solo_las_ofertas_de_la_ong_propia(
    client: TestClient, escenario: Escenario, db_session: Session
) -> None:
    csrf_propio = _autenticar_con_cookie(client, escenario.representante)
    propia = _crear_con_csrf(
        client,
        _payload(
            escenario.convocatoria.id,
            [_item(escenario.lote_agua.id, cantidad=100, unidad="litros")],
        ),
        csrf_propio,
    )
    assert propia.status_code == 201

    otra_representante = _usuario(
        db_session, escenario.otra_ong, RolUsuario.REPRESENTANTE_ONG, "otra@cb.org"
    )
    csrf_otra = _autenticar_con_cookie(client, otra_representante)
    ajena = _crear_con_csrf(
        client,
        _payload(
            escenario.convocatoria.id,
            [_item(escenario.lote_kits.id, cantidad=2, unidad="kits")],
        ),
        csrf_otra,
    )
    assert ajena.status_code == 201

    _autenticar_con_cookie(client, escenario.representante)
    response = client.get("/api/v1/ofertas")

    assert response.status_code == 200
    cuerpo = response.json()
    assert [oferta["id"] for oferta in cuerpo] == [propia.json()["id"]]
    assert all(oferta["ong_creadora_id"] == escenario.ong.id for oferta in cuerpo)


def test_lista_vacia_sin_ofertas_presentadas(
    client: TestClient, escenario: Escenario
) -> None:
    _autenticar_con_cookie(client, escenario.representante)

    response = client.get("/api/v1/ofertas")

    assert response.status_code == 200
    assert response.json() == []


def test_lista_omite_borrador_persistido_sin_fecha_de_presentacion(
    client: TestClient, escenario: Escenario, db_session: Session
) -> None:
    borrador = Oferta(
        convocatoria_id=escenario.convocatoria.id,
        ong_creadora_id=escenario.ong.id,
        creada_por_usuario_id=escenario.representante.id,
        estado=EstadoOferta.BORRADOR,
        version_actual=1,
        version_bloqueo=1,
    )
    db_session.add(borrador)
    db_session.flush()
    db_session.add(
        OfertaVersion(
            oferta_id=borrador.id,
            creada_por_usuario_id=escenario.representante.id,
            numero=1,
            observaciones="Todavía en preparación",
            presentada_en=None,
        )
    )
    db_session.flush()
    _autenticar_con_cookie(client, escenario.representante)

    response = client.get("/api/v1/ofertas")

    assert response.status_code == 200
    assert response.json() == []


def test_listar_ofertas_exige_sesion(client: TestClient) -> None:
    response = client.get("/api/v1/ofertas")

    assert response.status_code == 401


def test_listar_ofertas_deniega_a_quien_no_representa_una_ong(
    client: TestClient, escenario: Escenario
) -> None:
    _autenticar_con_cookie(client, escenario.operador_municipal)

    response = client.get("/api/v1/ofertas")

    assert response.status_code == 403


def test_openapi_documenta_listar_mis_ofertas(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    operacion = response.json()["paths"]["/api/v1/ofertas"]["get"]
    assert operacion["responses"]["200"]["description"]
    assert operacion["summary"]
    assert operacion["description"]
