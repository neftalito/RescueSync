"""Pruebas del buzón persistente y su canal WebSocket autenticado."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.core.security import (
    crear_token_csrf,
    crear_valor_sesion,
    generar_password_hash,
)
from app.db.models import (
    Convocatoria,
    Emergencia,
    GravedadEmergencia,
    Notificacion,
    Organizacion,
    RolUsuario,
    TipoNotificacion,
    TipoOrganizacion,
    Usuario,
)
from app.db.session import get_db
from app.main import app
from app.schemas.notificacion import NotificacionResponse
from app.services.notificaciones import notificar_emergencia_registrada
from app.services.tiempo_real import GestorTiempoReal

PASSWORD = "Una-clave-segura-2026"
ORIGEN_FRONTEND = "http://localhost:5173"


@pytest.fixture
def usuarios(db_session: Session) -> dict[str, Usuario]:
    municipio = Organizacion(
        tipo=TipoOrganizacion.MUNICIPIO,
        nombre="Municipio Notificaciones",
    )
    centro = Organizacion(
        tipo=TipoOrganizacion.CENTRO_COORDINADOR,
        nombre="Centro Notificaciones",
    )
    ong = Organizacion(
        tipo=TipoOrganizacion.ONG,
        nombre="ONG Notificaciones",
    )
    db_session.add_all([municipio, centro, ong])
    db_session.flush()
    password_hash = generar_password_hash(PASSWORD)
    creados = {
        "municipio": Usuario(
            organizacion_id=municipio.id,
            email="municipio-notificaciones@rescuesync.org",
            password_hash=password_hash,
            rol=RolUsuario.OPERADOR_MUNICIPAL,
        ),
        "coordinador": Usuario(
            organizacion_id=centro.id,
            email="coordinador-notificaciones@rescuesync.org",
            password_hash=password_hash,
            rol=RolUsuario.COORDINADOR_REGIONAL,
        ),
        "coordinador_inactivo": Usuario(
            organizacion_id=centro.id,
            email="coordinador-inactivo-notificaciones@rescuesync.org",
            password_hash=password_hash,
            rol=RolUsuario.COORDINADOR_REGIONAL,
            activo=False,
        ),
        "ong": Usuario(
            organizacion_id=ong.id,
            email="ong-notificaciones@rescuesync.org",
            password_hash=password_hash,
            rol=RolUsuario.REPRESENTANTE_ONG,
        ),
    }
    db_session.add_all(creados.values())
    db_session.flush()
    for usuario in creados.values():
        db_session.refresh(usuario)
    return creados


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


def _crear_notificacion(
    db_session: Session,
    usuario: Usuario,
    clave: str,
) -> Notificacion:
    notificacion = Notificacion(
        usuario_id=usuario.id,
        clave_evento=clave,
        tipo=TipoNotificacion.EMERGENCIA_REGISTRADA,
        titulo="Nueva emergencia pendiente",
        mensaje="Se registró una emergencia que requiere lotes.",
        ruta="/emergencias/31/lotes",
    )
    db_session.add(notificacion)
    db_session.commit()
    db_session.refresh(notificacion)
    return notificacion


def test_distribuye_el_evento_solo_a_usuarios_del_rol_activo(
    db_session: Session,
    usuarios: dict[str, Usuario],
) -> None:
    notificar_emergencia_registrada(
        db_session,
        emergencia_id=31,
        zona="Ribera norte",
    )
    db_session.commit()

    destinatarios = {
        item.usuario_id for item in db_session.scalars(select(Notificacion)).all()
    }
    assert usuarios["coordinador"].id in destinatarios
    assert usuarios["coordinador_inactivo"].id not in destinatarios
    assert usuarios["municipio"].id not in destinatarios
    assert usuarios["ong"].id not in destinatarios


@pytest.mark.parametrize("evento", ["publicada", "cerrada"])
@pytest.mark.parametrize("leida", [False, True])
def test_migracion_corrige_avisos_municipales_sin_alterar_lecturas_ni_otros_buzones(
    db_session: Session,
    usuarios: dict[str, Usuario],
    evento: str,
    leida: bool,
) -> None:
    operador = usuarios["municipio"]
    otro_municipio = Organizacion(
        nombre="Otro municipio", tipo=TipoOrganizacion.MUNICIPIO
    )
    db_session.add(otro_municipio)
    db_session.flush()
    otro_operador = Usuario(
        email="otro-municipio-notificaciones@prueba.org",
        rol=RolUsuario.OPERADOR_MUNICIPAL,
        organizacion_id=otro_municipio.id,
        password_hash=operador.password_hash,
    )
    emergencia = Emergencia(
        municipio_id=operador.organizacion_id,
        creada_por_usuario_id=operador.id,
        gravedad=GravedadEmergencia.ALTA,
        zona="Ribera norte",
        descripcion="Inundación con familias evacuadas",
    )
    db_session.add_all([otro_operador, emergencia])
    db_session.flush()
    fecha = datetime(2026, 10, 19, 12, tzinfo=UTC)
    convocatoria = Convocatoria(
        emergencia_id=emergencia.id,
        numero=1,
        publicada_en=fecha,
        cierra_en=fecha + timedelta(hours=2),
    )
    db_session.add(convocatoria)
    db_session.flush()
    mensaje_anterior = (
        "El centro coordinador publicó la convocatoria de la emergencia."
        if evento == "publicada"
        else "Cerró la convocatoria y las ofertas están siendo evaluadas."
    )
    avisos = [
        Notificacion(
            usuario_id=destinatario.id,
            clave_evento=f"convocatoria:{convocatoria.id}:{evento}",
            tipo=TipoNotificacion.EMERGENCIA_ESTADO_ACTUALIZADO,
            titulo="Emergencia publicada"
            if evento == "publicada"
            else "Emergencia en evaluación",
            mensaje=mensaje_anterior,
            ruta="/",
            creada_en=fecha,
            leida_en=fecha if leida else None,
        )
        for destinatario in (operador, otro_operador, usuarios["ong"])
    ]
    db_session.add_all(avisos)
    db_session.flush()

    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "alembic")
    )
    revision = ScriptDirectory.from_config(config).get_revision("20261020_0016")
    assert revision is not None
    with Operations.context(MigrationContext.configure(db_session.connection())):
        revision.module.upgrade()
        revision.module.upgrade()
    db_session.expire_all()

    propia, ajena, ong = avisos
    prefijo = (
        "El centro coordinador publicó la convocatoria de la emergencia en "
        if evento == "publicada"
        else "Cerró la convocatoria y las ofertas están siendo evaluadas. Emergencia en "
    )
    assert propia.mensaje == f"{prefijo}{emergencia.zona}: {emergencia.descripcion}"
    assert propia.ruta == f"/emergencias/{emergencia.id}/ejecucion"
    for aviso in avisos:
        assert aviso.creada_en == fecha
        assert aviso.leida_en == (fecha if leida else None)
    for aviso in (ajena, ong):
        assert aviso.mensaje == mensaje_anterior
        assert aviso.ruta == "/"

    with Operations.context(MigrationContext.configure(db_session.connection())):
        revision.module.downgrade()
    db_session.expire_all()
    assert propia.mensaje == mensaje_anterior
    assert propia.ruta == "/"
    assert propia.creada_en == fecha
    assert propia.leida_en == (fecha if leida else None)


def test_buzon_no_expone_notificaciones_de_otro_usuario_y_exige_csrf(
    client: TestClient,
    db_session: Session,
    usuarios: dict[str, Usuario],
) -> None:
    propia = _crear_notificacion(db_session, usuarios["coordinador"], "evento:propio")
    ajena = _crear_notificacion(db_session, usuarios["ong"], "evento:ajeno")
    csrf = _autenticar(client, usuarios["coordinador"])

    listado = client.get("/api/v1/notificaciones")

    assert listado.status_code == 200
    assert [item["id"] for item in listado.json()] == [propia.id]
    assert client.patch(f"/api/v1/notificaciones/{propia.id}/leida").status_code == 403
    assert (
        client.patch(
            f"/api/v1/notificaciones/{ajena.id}/leida",
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 404
    )

    marcada = client.patch(
        f"/api/v1/notificaciones/{propia.id}/leida",
        headers={"X-CSRF-Token": csrf},
    )

    assert marcada.status_code == 200
    assert marcada.json()["leida_en"] is not None


def test_marca_todas_las_notificaciones_propias_sin_afectar_otro_buzon(
    client: TestClient,
    db_session: Session,
    usuarios: dict[str, Usuario],
) -> None:
    primera = _crear_notificacion(
        db_session,
        usuarios["coordinador"],
        "evento:primero-pendiente",
    )
    segunda = _crear_notificacion(
        db_session,
        usuarios["coordinador"],
        "evento:segundo-pendiente",
    )
    ajena = _crear_notificacion(db_session, usuarios["ong"], "evento:ajeno-pendiente")
    csrf = _autenticar(client, usuarios["coordinador"])

    sin_csrf = client.patch("/api/v1/notificaciones/leidas")
    respuesta = client.patch(
        "/api/v1/notificaciones/leidas",
        headers={"X-CSRF-Token": csrf},
    )
    db_session.refresh(primera)
    db_session.refresh(segunda)
    db_session.refresh(ajena)

    assert sin_csrf.status_code == 403
    assert respuesta.status_code == 200
    assert respuesta.json()["cantidad_actualizada"] == 2
    assert primera.leida_en is not None
    assert segunda.leida_en == primera.leida_en
    assert ajena.leida_en is None

    repetida = client.patch(
        "/api/v1/notificaciones/leidas",
        headers={"X-CSRF-Token": csrf},
    )

    assert repetida.status_code == 200
    assert repetida.json()["cantidad_actualizada"] == 0


def test_websocket_entrega_solo_al_usuario_autenticado(
    client: TestClient,
    db_session: Session,
    usuarios: dict[str, Usuario],
) -> None:
    usuario = usuarios["coordinador"]
    notificacion = _crear_notificacion(db_session, usuario, "evento:websocket")
    _autenticar(client, usuario)

    with client.websocket_connect(
        "/api/v1/notificaciones/ws",
        headers={"Origin": ORIGEN_FRONTEND},
    ) as websocket:
        gestor = app.state.gestor_tiempo_real
        assert isinstance(gestor, GestorTiempoReal)
        gestor.programar([NotificacionResponse.model_validate(notificacion)])
        mensaje = websocket.receive_json()

    assert mensaje["evento"] == "notificacion.creada"
    assert mensaje["notificacion"]["id"] == notificacion.id
    assert mensaje["notificacion"]["usuario_id"] == usuario.id


def test_websocket_actualiza_metricas_solo_en_conexiones_auditoras(
    client: TestClient, db_session: Session, usuarios: dict[str, Usuario]
) -> None:
    auditor = Usuario(
        email="auditor-socket@prueba.org",
        rol=RolUsuario.AUDITOR_DIRECTIVO,
        password_hash=usuarios["ong"].password_hash,
    )
    db_session.add(auditor)
    db_session.flush()
    client.cookies.set("rescuesync_session", crear_valor_sesion(auditor.id))
    with client.websocket_connect(
        "/api/v1/notificaciones/ws", headers={"origin": ORIGEN_FRONTEND}
    ) as socket_auditor:
        usuario = usuarios["ong"]
        client.cookies.set("rescuesync_session", crear_valor_sesion(usuario.id))
        with client.websocket_connect(
            "/api/v1/notificaciones/ws", headers={"origin": ORIGEN_FRONTEND}
        ) as socket_ong:
            gestor = app.state.gestor_tiempo_real
            notificacion = _crear_notificacion(db_session, usuario, "socket:control")
            gestor.programar_metricas()
            gestor.programar([NotificacionResponse.model_validate(notificacion)])
            assert socket_auditor.receive_json() == {"evento": "metricas.actualizadas"}
            assert socket_ong.receive_json()["evento"] == "notificacion.creada"


def test_websocket_rechaza_origen_no_permitido(
    client: TestClient,
    usuarios: dict[str, Usuario],
) -> None:
    _autenticar(client, usuarios["coordinador"])

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "/api/v1/notificaciones/ws",
            headers={"Origin": "https://sitio-malicioso.example"},
        ),
    ):
        pass


def test_websocket_rechaza_una_conexion_sin_sesion(
    client: TestClient,
) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "/api/v1/notificaciones/ws",
            headers={"Origin": ORIGEN_FRONTEND},
        ),
    ):
        pass


def test_modelo_usa_fechas_con_zona_horaria(
    db_session: Session,
    usuarios: dict[str, Usuario],
) -> None:
    notificacion = _crear_notificacion(db_session, usuarios["ong"], "evento:fecha")
    respuesta = NotificacionResponse.model_validate(notificacion)

    assert respuesta.creada_en <= datetime.now(UTC)
    assert respuesta.creada_en.tzinfo is not None
