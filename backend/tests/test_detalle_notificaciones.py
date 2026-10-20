"""Destinos del ojo: eventos históricos, privacidad y consultas sin efectos."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import crear_valor_sesion
from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    EstadoConvocatoria,
    EstadoEmergencia,
    EstadoLote,
    EstadoOferta,
    GravedadEmergencia,
    Lote,
    Notificacion,
    Oferta,
    OfertaItem,
    OfertaVersion,
    OfertaVersionParticipante,
    Organizacion,
    RolUsuario,
    TipoAporte,
    TipoNotificacion,
    TipoOrganizacion,
    TipoParticipacion,
    Usuario,
)
from app.db.session import get_db
from app.main import app
from app.services.notificaciones import (
    notificar_convocatoria_cerrada,
    notificar_convocatoria_publicada,
    notificar_oferta_recibida,
    notificar_tarea_bonita_fallida,
)


@dataclass
class Caso:
    usuarios: dict[str, Usuario]
    emergencia: Emergencia
    convocatoria: Convocatoria
    nueva: Convocatoria
    oferta: Oferta


@pytest.fixture
def caso(db_session: Session) -> Caso:
    usuarios: dict[str, Usuario] = {}
    for clave, rol, tipo in (
        ("municipio", RolUsuario.OPERADOR_MUNICIPAL, TipoOrganizacion.MUNICIPIO),
        (
            "coordinador",
            RolUsuario.COORDINADOR_REGIONAL,
            TipoOrganizacion.CENTRO_COORDINADOR,
        ),
        (
            "otro_centro",
            RolUsuario.COORDINADOR_REGIONAL,
            TipoOrganizacion.CENTRO_COORDINADOR,
        ),
        ("ong", RolUsuario.REPRESENTANTE_ONG, TipoOrganizacion.ONG),
        ("otra_ong", RolUsuario.REPRESENTANTE_ONG, TipoOrganizacion.ONG),
        ("auditor", RolUsuario.AUDITOR_DIRECTIVO, None),
        ("admin", RolUsuario.ADMINISTRADOR, None),
    ):
        organizacion = (
            Organizacion(nombre=f"Organización {clave}", tipo=tipo) if tipo else None
        )
        if organizacion:
            db_session.add(organizacion)
            db_session.flush()
        usuario = Usuario(
            email=f"{clave}@detalle.prueba.org",
            rol=rol,
            organizacion_id=organizacion.id if organizacion else None,
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",
        )
        db_session.add(usuario)
        db_session.flush()
        usuarios[clave] = usuario
    ahora = datetime.now(UTC)
    emergencia = Emergencia(
        municipio_id=usuarios["municipio"].organizacion_id,
        centro_coordinador_id=usuarios["coordinador"].organizacion_id,
        creada_por_usuario_id=usuarios["municipio"].id,
        zona="Ribera norte",
        descripcion="Inundación con evacuados",
        gravedad=GravedadEmergencia.ALTA,
        estado=EstadoEmergencia.PUBLICADA,
    )
    db_session.add(emergencia)
    db_session.flush()
    lote = Lote(
        emergencia_id=emergencia.id,
        creado_por_usuario_id=usuarios["coordinador"].id,
        tipo_necesidad="Agua potable",
        cantidad_requerida=Decimal(200),
        unidad="litros",
        estado=EstadoLote.PUBLICADO,
    )
    vieja = Convocatoria(
        emergencia_id=emergencia.id,
        numero=1,
        estado=EstadoConvocatoria.CERRADA,
        publicada_en=ahora - timedelta(days=2),
        cierra_en=ahora - timedelta(days=1),
        cerrada_en=ahora - timedelta(days=1),
    )
    nueva = Convocatoria(
        emergencia_id=emergencia.id,
        numero=2,
        publicada_en=ahora,
        cierra_en=ahora + timedelta(days=1),
    )
    db_session.add_all([lote, vieja, nueva])
    db_session.flush()
    for convocatoria, cantidad in ((vieja, "100"), (nueva, "200")):
        db_session.add(
            ConvocatoriaLote(
                convocatoria_id=convocatoria.id,
                lote_id=lote.id,
                cantidad_publicada=Decimal(cantidad),
                unidad_publicada="litros",
            )
        )
    oferta = Oferta(
        convocatoria_id=vieja.id,
        ong_creadora_id=usuarios["ong"].organizacion_id,
        creada_por_usuario_id=usuarios["ong"].id,
        estado=EstadoOferta.PRESENTADA,
    )
    db_session.add(oferta)
    db_session.flush()
    version = OfertaVersion(
        oferta_id=oferta.id,
        numero=1,
        creada_por_usuario_id=usuarios["ong"].id,
        presentada_en=ahora - timedelta(days=1, hours=1),
        observaciones="Oferta presentada",
    )
    db_session.add(version)
    db_session.flush()
    db_session.add(
        OfertaItem(
            oferta_version_id=version.id,
            convocatoria_id=vieja.id,
            lote_id=lote.id,
            tipo=TipoAporte.RECURSO,
            descripcion="Bidones de agua",
            cantidad_ofrecida=Decimal(25),
            unidad="litros",
        )
    )
    db_session.flush()
    notificar_convocatoria_publicada(
        db_session,
        convocatoria_id=vieja.id,
        emergencia_id=emergencia.id,
        municipio_id=emergencia.municipio_id,
        zona=emergencia.zona,
        descripcion=emergencia.descripcion,
    )
    notificar_convocatoria_cerrada(
        db_session,
        convocatoria_id=vieja.id,
        emergencia_id=emergencia.id,
        municipio_id=emergencia.municipio_id,
        zona=emergencia.zona,
        descripcion=emergencia.descripcion,
    )
    notificar_oferta_recibida(
        db_session,
        oferta_id=oferta.id,
        centro_coordinador_id=emergencia.centro_coordinador_id,
        zona=emergencia.zona,
    )
    notificar_tarea_bonita_fallida(
        db_session, tarea_id=42, emergencia_id=emergencia.id, nombre="Validar ofertas"
    )
    db_session.flush()
    return Caso(usuarios, emergencia, vieja, nueva, oferta)


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def sesion() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = sesion
    try:
        with TestClient(app) as cliente:
            yield cliente
    finally:
        app.dependency_overrides.pop(get_db, None)


def _aviso(session: Session, usuario: Usuario, tipo: TipoNotificacion) -> Notificacion:
    aviso = session.scalar(
        select(Notificacion).where(
            Notificacion.usuario_id == usuario.id,
            Notificacion.tipo == tipo,
        )
    )
    assert aviso is not None
    return aviso


def _autenticar(client: TestClient, usuario: Usuario) -> None:
    client.cookies.set("rescuesync_session", crear_valor_sesion(usuario.id))


def test_oferta_recibida_abre_su_ong_aportes_y_emergencia_sin_modificarla(
    client: TestClient,
    db_session: Session,
    caso: Caso,
) -> None:
    usuario = caso.usuarios["coordinador"]
    aviso = _aviso(db_session, usuario, TipoNotificacion.OFERTA_RECIBIDA)
    assert aviso.ruta == f"/notificaciones/{aviso.id}"
    _autenticar(client, usuario)
    respuesta = client.get(f"/api/v1/notificaciones/{aviso.id}/detalle")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["clase"] == "OFERTA_RECIBIDA"
    assert datos["emergencia"]["id"] == caso.emergencia.id
    assert datos["oferta"]["participantes"][0]["nombre"] == "Organización ong"
    assert datos["oferta"]["items"][0]["descripcion"] == "Bidones de agua"
    assert Decimal(datos["oferta"]["items"][0]["cantidad_ofrecida"]) == 25
    db_session.refresh(aviso)
    assert aviso.leida_en is None
    assert caso.oferta.version_actual == 1


def test_no_expone_una_version_pendiente_aunque_el_aviso_sea_anterior(
    client: TestClient,
    db_session: Session,
    caso: Caso,
) -> None:
    caso.oferta.version_actual = 2
    db_session.add(
        OfertaVersion(
            oferta_id=caso.oferta.id,
            numero=2,
            creada_por_usuario_id=caso.usuarios["ong"].id,
            observaciones="Propuesta confidencial sin confirmar",
        )
    )
    db_session.flush()
    aviso = _aviso(
        db_session, caso.usuarios["coordinador"], TipoNotificacion.OFERTA_RECIBIDA
    )
    _autenticar(client, caso.usuarios["coordinador"])
    respuesta = client.get(f"/api/v1/notificaciones/{aviso.id}/detalle")
    assert respuesta.status_code == 200
    assert respuesta.json()["oferta"]["version"] == 1
    assert "confidencial" not in respuesta.text


@pytest.mark.parametrize(
    "tipo",
    [TipoNotificacion.CONVOCATORIA_PUBLICADA, TipoNotificacion.CONVOCATORIA_CERRADA],
)
@pytest.mark.parametrize("clave_usuario", ["ong", "otra_ong"])
def test_convocatoria_exacta_cerrada_con_su_oferta_o_sin_participacion(
    client: TestClient,
    db_session: Session,
    caso: Caso,
    tipo: TipoNotificacion,
    clave_usuario: str,
) -> None:
    usuario = caso.usuarios[clave_usuario]
    aviso = _aviso(db_session, usuario, tipo)
    assert aviso.ruta == f"/notificaciones/{aviso.id}"
    _autenticar(client, usuario)
    respuesta = client.get(f"/api/v1/notificaciones/{aviso.id}/detalle")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["convocatoria"]["id"] == caso.convocatoria.id
    assert datos["convocatoria"]["id"] != caso.nueva.id
    assert datos["convocatoria"]["estado"] == "CERRADA"
    assert Decimal(datos["convocatoria"]["lotes"][0]["cantidad_publicada"]) == 100
    if clave_usuario == "ong":
        assert datos["mi_oferta"]["id"] == caso.oferta.id
    else:
        assert datos["mi_oferta"] is None
        assert "Bidones de agua" not in respuesta.text


def test_incidente_conserva_el_contexto_observado_sin_consultar_ni_ejecutar_bonita(
    client: TestClient,
    db_session: Session,
    caso: Caso,
) -> None:
    usuario = caso.usuarios["auditor"]
    aviso = _aviso(db_session, usuario, TipoNotificacion.TAREA_BONITA_FALLIDA)
    assert aviso.ruta == f"/notificaciones/{aviso.id}"
    _autenticar(client, usuario)
    respuesta = client.get(f"/api/v1/notificaciones/{aviso.id}/detalle")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["tarea_id"] == 42
    assert datos["nombre"] == "Validar ofertas"
    assert datos["estado_observado"] == "failed"
    assert datos["emergencia"]["zona"] == caso.emergencia.zona
    assert aviso.leida_en is None


@pytest.mark.parametrize(
    "clave_usuario", ["municipio", "otro_centro", "ong", "otra_ong", "auditor", "admin"]
)
def test_ningun_otro_usuario_puede_abrir_el_aviso_del_coordinador(
    client: TestClient,
    db_session: Session,
    caso: Caso,
    clave_usuario: str,
) -> None:
    aviso = _aviso(
        db_session, caso.usuarios["coordinador"], TipoNotificacion.OFERTA_RECIBIDA
    )
    _autenticar(client, caso.usuarios[clave_usuario])
    respuesta = client.get(f"/api/v1/notificaciones/{aviso.id}/detalle")
    assert respuesta.status_code == 404
    assert "Bidones" not in respuesta.text


@pytest.mark.parametrize(
    "tipo,propietario",
    [
        (TipoNotificacion.OFERTA_RECIBIDA, "coordinador"),
        (TipoNotificacion.CONVOCATORIA_CERRADA, "ong"),
        (TipoNotificacion.TAREA_BONITA_FALLIDA, "auditor"),
    ],
)
def test_revalida_el_rol_aunque_el_aviso_pertenezca_al_usuario(
    client: TestClient,
    db_session: Session,
    caso: Caso,
    tipo: TipoNotificacion,
    propietario: str,
) -> None:
    aviso = _aviso(db_session, caso.usuarios[propietario], tipo)
    aviso.usuario_id = caso.usuarios["admin"].id
    db_session.flush()
    _autenticar(client, caso.usuarios["admin"])
    assert client.get(f"/api/v1/notificaciones/{aviso.id}/detalle").status_code == 403


def test_cambio_de_centro_invalida_el_acceso_anterior(
    client: TestClient,
    db_session: Session,
    caso: Caso,
) -> None:
    aviso = _aviso(
        db_session, caso.usuarios["coordinador"], TipoNotificacion.OFERTA_RECIBIDA
    )
    caso.emergencia.centro_coordinador_id = caso.usuarios["otro_centro"].organizacion_id
    db_session.flush()
    _autenticar(client, caso.usuarios["coordinador"])
    assert client.get(f"/api/v1/notificaciones/{aviso.id}/detalle").status_code == 403


def test_ong_invitada_no_ve_los_aportes_presentados_antes_de_su_invitacion(
    client: TestClient,
    db_session: Session,
    caso: Caso,
) -> None:
    caso.oferta.version_actual = 2
    caso.oferta.estado = EstadoOferta.BORRADOR
    version = OfertaVersion(
        oferta_id=caso.oferta.id,
        numero=2,
        creada_por_usuario_id=caso.usuarios["ong"].id,
        requiere_desglose_nacional=True,
        observaciones="Propuesta conjunta pendiente",
    )
    db_session.add(version)
    db_session.flush()
    db_session.add(
        OfertaVersionParticipante(
            oferta_version_id=version.id,
            ong_id=caso.usuarios["otra_ong"].organizacion_id,
            nombre_ong="Organización otra_ong",
            rol=TipoParticipacion.MIEMBRO,
        )
    )
    db_session.flush()
    aviso = _aviso(
        db_session, caso.usuarios["otra_ong"], TipoNotificacion.CONVOCATORIA_CERRADA
    )
    _autenticar(client, caso.usuarios["otra_ong"])
    respuesta = client.get(f"/api/v1/notificaciones/{aviso.id}/detalle")
    assert respuesta.status_code == 200
    assert respuesta.json()["mi_oferta"]["version"] == 2
    assert respuesta.json()["mi_oferta"]["items"] == []
    assert "Bidones de agua" not in respuesta.text


def test_migracion_recupera_incidentes_antiguos_y_enlaces_sin_cambiar_lecturas(
    db_session: Session,
    caso: Caso,
) -> None:
    avisos = list(db_session.scalars(select(Notificacion)).all())
    fecha = datetime(2026, 10, 19, 12, tzinfo=UTC)
    for aviso in avisos:
        aviso.leida_en = fecha
    db_session.flush()
    originales = {aviso.id: (aviso.creada_en, aviso.mensaje) for aviso in avisos}
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "alembic")
    )
    revision = ScriptDirectory.from_config(config).get_revision("20261020_0017")
    assert revision is not None
    with Operations.context(MigrationContext.configure(db_session.connection())):
        revision.module.downgrade()
        revision.module.upgrade()
    db_session.expire_all()
    for aviso in avisos:
        assert (aviso.creada_en, aviso.mensaje) == originales[aviso.id]
        assert aviso.leida_en == fecha
        if aviso.usuario.rol == RolUsuario.OPERADOR_MUNICIPAL:
            assert aviso.ruta == f"/emergencias/{caso.emergencia.id}/ejecucion"
        else:
            assert aviso.ruta == f"/notificaciones/{aviso.id}"
        if aviso.tipo == TipoNotificacion.TAREA_BONITA_FALLIDA:
            assert aviso.emergencia_id == caso.emergencia.id
            assert aviso.tarea_bonita_nombre == "Validar ofertas"


def test_exige_sesion_y_rechaza_ids_inexistentes(
    client: TestClient, caso: Caso
) -> None:
    assert client.get("/api/v1/notificaciones/999999/detalle").status_code == 401
    _autenticar(client, caso.usuarios["ong"])
    assert client.get("/api/v1/notificaciones/999999/detalle").status_code == 404
