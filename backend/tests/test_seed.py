import json
import re
from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    AccesoNacional,
    Convocatoria,
    Emergencia,
    Lote,
    Oferta,
    Organizacion,
    Usuario,
)
from app.db.models.aprovisionamiento import AprovisionamientoNacional
from app.db.session import get_db
from app.integrations.nacional.cliente import ClienteNacional
from app.main import app
from app.scripts.seed import aprovisionar_ongs_demo, seed_development_data
from app.services.acceso_nacional import cifrador
from app.services.auth import autenticar_usuario


@pytest.fixture(autouse=True)
def cifrado_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        get_settings(),
        "nacional_encryption_key",
        SecretStr(Fernet.generate_key().decode()),
    )
    monkeypatch.setattr(
        get_settings(), "nacional_aprovisionamiento_login", "emisor-seed"
    )
    monkeypatch.setattr(
        get_settings(),
        "nacional_aprovisionamiento_password",
        SecretStr("secreto-emisor"),
    )


EMAILS = (
    "municipio@rescuesync.org",
    "coordinador@rescuesync.org",
    "ong@rescuesync.org",
    "redmedica@rescuesync.org",
    "auditor@rescuesync.org",
    "admin@rescuesync.org",
)
ORGANIZACIONES = (
    "Municipalidad de Puerto Esperanza",
    "Centro Coordinador Litoral",
    "Ayuda Sin Fronteras",
    "Red Médica Solidaria",
)
ZONAS = (
    "Arroyo Sur — datos demo",
    "Corredor Norte — datos demo",
)


def _contar(session: Session, modelo: type[object], condicion: object) -> int:
    cantidad = session.scalar(select(func.count()).select_from(modelo).where(condicion))
    assert cantidad is not None
    return cantidad


def test_seed_es_idempotente_y_crea_un_usuario_vigente_por_rol(
    db_session: Session,
) -> None:
    primer_resultado = seed_development_data(db_session)
    segundo_resultado = seed_development_data(db_session)

    assert primer_resultado == segundo_resultado
    assert _contar(db_session, Usuario, Usuario.email.in_(EMAILS)) == 6
    assert (
        _contar(db_session, Organizacion, Organizacion.nombre.in_(ORGANIZACIONES)) == 4
    )
    assert _contar(db_session, Emergencia, Emergencia.zona.in_(ZONAS)) == 2

    roles = set()
    for cuenta in primer_resultado.cuentas:
        password = (
            get_settings().admin_initial_password.get_secret_value()
            if cuenta.rol.value == "ADMINISTRADOR"
            else f"{cuenta.email.partition('@')[0]}123"
        )
        usuario = autenticar_usuario(
            db_session,
            cuenta.email,
            password,
        )
        assert usuario is not None
        roles.add(usuario.rol)
    assert roles == {cuenta.rol for cuenta in primer_resultado.cuentas}


def test_seed_solo_cuentas_prepara_ongs_sin_crear_emergencias_ni_ofertas(
    db_session: Session,
) -> None:
    resultado = seed_development_data(db_session, solo_cuentas=True)

    assert {cuenta.email for cuenta in resultado.cuentas} == set(EMAILS)
    assert resultado.emergencias == resultado.lotes_publicados == resultado.ofertas == 0
    assert db_session.scalar(select(func.count()).select_from(Emergencia)) == 0
    assert db_session.scalar(select(func.count()).select_from(Oferta)) == 0
    assert (
        db_session.scalar(select(func.count()).select_from(AprovisionamientoNacional))
        == 2
    )


def test_seed_dashboard_cubre_estados_gravedades_historia_y_ofertas_sin_duplicar(
    db_session: Session,
) -> None:
    from datetime import date

    from app.db.models import EstadoEmergencia, GravedadEmergencia, OfertaVersion
    from app.schemas.metricas import FiltrosMetricas
    from app.services.metricas import obtener_metricas

    resultado = seed_development_data(db_session)
    ids_originales = set(db_session.scalars(select(Emergencia.id)).all())
    seed_development_data(db_session)
    assert set(db_session.scalars(select(Emergencia.id)).all()) == ids_originales
    assert resultado.emergencias == 19
    assert set(db_session.scalars(select(Emergencia.estado)).all()) == set(
        EstadoEmergencia
    )
    assert set(db_session.scalars(select(Emergencia.gravedad)).all()) == set(
        GravedadEmergencia
    )
    reporte = obtener_metricas(
        db_session, FiltrosMetricas(fecha_desde=date(2020, 1, 1))
    )
    assert len([m for m in reporte.evolucion_mensual if m.cantidad]) >= 6
    assert len(reporte.cantidades_ofrecidas) >= 16
    assert all(c.cantidad > 0 for c in reporte.tipos_oferta)
    assert (
        db_session.scalar(select(func.count()).select_from(OfertaVersion))
        > resultado.ofertas
    )


def test_seed_migra_los_correos_demo_del_formato_anterior(
    db_session: Session,
) -> None:
    seed_development_data(db_session)
    usuario = db_session.scalar(
        select(Usuario).where(Usuario.email == "municipio@rescuesync.org")
    )
    assert usuario is not None
    usuario_id = usuario.id
    usuario.email = "municipio@demo.rescuesync.org"
    db_session.flush()

    seed_development_data(db_session)

    migrado = db_session.scalar(
        select(Usuario).where(Usuario.email == "municipio@rescuesync.org")
    )
    assert migrado is not None
    assert migrado.id == usuario_id
    assert (
        db_session.scalar(
            select(Usuario).where(Usuario.email == "municipio@demo.rescuesync.org")
        )
        is None
    )


def test_seed_deja_convocatoria_lotes_y_oferta_para_pruebas(
    db_session: Session,
) -> None:
    seed_development_data(db_session)
    emergencia = db_session.scalar(
        select(Emergencia).where(Emergencia.zona == "Corredor Norte — datos demo")
    )

    assert emergencia is not None
    assert _contar(db_session, Lote, Lote.emergencia_id == emergencia.id) == 3
    assert (
        _contar(
            db_session,
            Convocatoria,
            Convocatoria.emergencia_id == emergencia.id,
        )
        == 1
    )
    convocatoria = db_session.scalar(
        select(Convocatoria).where(Convocatoria.emergencia_id == emergencia.id)
    )
    assert convocatoria is not None
    assert (
        _contar(
            db_session,
            Oferta,
            and_(
                Oferta.convocatoria_id == convocatoria.id,
                Oferta.fusionada_en_oferta_id.is_(None),
            ),
        )
        == 1
    )


def test_seed_prepara_altas_sin_fabricar_uuid_ni_accesos_nacionales(
    db_session: Session,
) -> None:
    seed_development_data(db_session)
    for nombre in ("Ayuda Sin Fronteras", "Red Médica Solidaria"):
        ong = db_session.scalar(
            select(Organizacion).where(Organizacion.nombre == nombre)
        )
        assert ong is not None
        assert ong.ong_nacional_id is None
        assert db_session.get(AccesoNacional, ong.id) is None
        assert db_session.get(AprovisionamientoNacional, ong.id) is not None


@pytest.mark.parametrize(
    "referencia,email",
    [
        ("ayuda-sin-fronteras", "ong@rescuesync.org"),
        ("red-medica-solidaria", "redmedica@rescuesync.org"),
    ],
)
def test_login_seed_permite_ver_recursos_sin_importar_credenciales(
    db_session: Session,
    referencia: str,
    email: str,
) -> None:
    seed_development_data(db_session)
    db_session.commit()
    ong_id, cuenta_id = uuid4(), uuid4()
    ong = db_session.scalar(
        select(Organizacion)
        .join(Usuario, Usuario.organizacion_id == Organizacion.id)
        .where(Usuario.email == email)
    )
    assert ong is not None
    pendiente = db_session.get(AprovisionamientoNacional, ong.id)
    assert pendiente is not None
    secreto = cifrador().decrypt(pendiente.secreto_cifrado.encode()).decode()
    nombre_ong = ong.nombre

    def database() -> Iterator[Session]:
        yield db_session

    def login_nacional(request: httpx.Request) -> httpx.Response:
        datos = json.loads(request.content)
        if datos["identificadorLogin"] != "emisor-seed":
            assert datos == {
                "identificadorLogin": f"tecnica-{referencia}",
                "password": secreto,
            }
        return httpx.Response(
            200,
            json={
                "access_token": "jwt-demo",
                "token_type": "bearer",
                "expires_in": 300,
            },
        )

    def alta_nacional(request: httpx.Request) -> httpx.Response:
        nombre = json.loads(request.content)["nombre"]
        return httpx.Response(
            200,
            json={
                "ong": {
                    "id": str(ong_id if nombre == nombre_ong else uuid4()),
                    "nombre": nombre,
                    "estado": "PENDIENTE",
                },
                "cuentaId": str(cuenta_id if nombre == nombre_ong else uuid4()),
                "identificadorLogin": f"tecnica-{referencia}",
            },
        )

    base = str(get_settings().nacional_base_url).rstrip("/")
    app.dependency_overrides[get_db] = database
    try:
        with respx.mock as mock, TestClient(app) as client:
            mock.post(f"{base}/login").mock(side_effect=login_nacional)
            mock.put(re.compile(re.escape(base) + r"/integraciones/ongs/.*")).mock(
                side_effect=alta_nacional
            )
            nacional = ClienteNacional(base, 1)
            try:
                aprovisionar_ongs_demo(db_session, nacional)
            finally:
                nacional.close()
            mock.get(f"{base}/me").respond(
                200,
                json={
                    "id": str(cuenta_id),
                    "ongId": str(ong_id),
                    "rol": "ONG",
                    "proposito": "TECNICA_ONG",
                },
            )
            mock.get(f"{base}/ongs/{ong_id}/recursos").respond(200, json=[])
            login = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": email.partition("@")[0] + "123"},
            )
            assert login.status_code == 200
            assert client.get("/api/v1/mi-ong/conexion").json()["estado"] == "LISTA"
            assert client.get("/api/v1/mi-ong/recursos").status_code == 200
            assert secreto not in login.text
    finally:
        app.dependency_overrides.clear()


def test_seed_conserva_acceso_importado_o_marcado_para_revision(
    db_session: Session,
) -> None:
    seed_development_data(db_session)
    ong = db_session.scalar(
        select(Organizacion).where(Organizacion.nombre == "Ayuda Sin Fronteras")
    )
    assert ong is not None
    ong.ong_nacional_id = uuid4()
    acceso = AccesoNacional(
        organizacion_id=ong.id,
        ong_id=ong.ong_nacional_id,
        cuenta_id=uuid4(),
        configuracion_id=uuid4(),
        identificador_login="tecnica-importada",
        secreto_cifrado="credencial-importada-conservada",
        requiere_revision=True,
    )
    db_session.add(acceso)
    db_session.flush()
    original = (acceso.configuracion_id, acceso.cuenta_id, acceso.secreto_cifrado)
    seed_development_data(db_session)
    db_session.flush()
    assert (
        acceso.configuracion_id,
        acceso.cuenta_id,
        acceso.secreto_cifrado,
    ) == original
    assert acceso.requiere_revision is True
    assert db_session.scalar(select(func.count()).select_from(AccesoNacional)) == 1


def test_seed_sin_clave_no_confirma_un_acceso_incompleto(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "nacional_encryption_key", None)
    with pytest.raises(ValueError, match="NACIONAL_ENCRYPTION_KEY"):
        seed_development_data(db_session)
    assert db_session.scalar(select(func.count()).select_from(Organizacion)) == 0


def test_seed_no_guarda_credenciales_demo_en_produccion(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "app_env", "production")
    with pytest.raises(ValueError, match="desarrollo y pruebas"):
        seed_development_data(db_session)
