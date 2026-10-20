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
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    crear_token_csrf,
    crear_valor_sesion,
    generar_password_hash,
)
from app.db.models import (
    AccesoNacional,
    AprovisionamientoNacional,
    Organizacion,
    RolUsuario,
    TipoOrganizacion,
    Usuario,
)
from app.db.session import get_db
from app.main import app

PASSWORD = "Clave-segura-2026"


@pytest.fixture(autouse=True)
def configuracion_alta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        get_settings(),
        "nacional_encryption_key",
        SecretStr(Fernet.generate_key().decode()),
    )
    monkeypatch.setattr(get_settings(), "nacional_aprovisionamiento_login", None)


@pytest.fixture
def administrador(db_session: Session) -> Usuario:
    usuario = Usuario(
        email="admin-organizaciones@rescuesync.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.ADMINISTRADOR,
    )
    db_session.add(usuario)
    db_session.flush()
    return usuario


@pytest.fixture
def client(
    db_session: Session,
    administrador: Usuario,
) -> Iterator[TestClient]:
    def usar_sesion_de_prueba() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = usar_sesion_de_prueba
    with TestClient(app) as test_client:
        test_client.cookies.set(
            "rescuesync_session",
            crear_valor_sesion(administrador.id, administrador.version_sesion),
            path="/api/v1",
        )
        yield test_client
    app.dependency_overrides.clear()


def _csrf(usuario: Usuario) -> dict[str, str]:
    return {
        "X-CSRF-Token": crear_token_csrf(usuario.id, usuario.version_sesion),
    }


@pytest.mark.parametrize(
    ("tipo", "nombre"),
    [
        ("MUNICIPIO", "Municipio de Prueba"),
        ("CENTRO_COORDINADOR", "Centro Coordinador de Prueba"),
        ("ONG", "ONG de Prueba"),
    ],
)
def test_administrador_crea_cada_tipo_de_organizacion(
    client: TestClient,
    db_session: Session,
    administrador: Usuario,
    tipo: str,
    nombre: str,
) -> None:
    response = client.post(
        "/api/v1/organizaciones",
        headers=_csrf(administrador),
        json={"nombre": f"  {nombre}  ", "tipo": tipo},
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": response.json()["id"],
        "nombre": nombre,
        "tipo": tipo,
        "activa": True,
        "ong_nacional_id": None,
    }
    organizacion = db_session.get(Organizacion, response.json()["id"])
    assert organizacion is not None
    assert organizacion.nombre == nombre


def test_alta_rechaza_una_organizacion_duplicada(
    client: TestClient,
    db_session: Session,
    administrador: Usuario,
) -> None:
    db_session.add(Organizacion(tipo=TipoOrganizacion.ONG, nombre="Rescate Solidario"))
    db_session.flush()

    response = client.post(
        "/api/v1/organizaciones",
        headers=_csrf(administrador),
        json={"nombre": "Rescate Solidario", "tipo": "ONG"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Ya existe una organización de ese tipo con el mismo nombre."
    }


def test_edita_desactiva_y_recupera_sin_reactivar_usuarios(
    client: TestClient,
    db_session: Session,
    administrador: Usuario,
) -> None:
    organizacion = Organizacion(
        tipo=TipoOrganizacion.MUNICIPIO,
        nombre="Municipio Original",
    )
    db_session.add(organizacion)
    db_session.flush()
    operador = Usuario(
        email="operador-organizacion@rescuesync.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.OPERADOR_MUNICIPAL,
        organizacion_id=organizacion.id,
    )
    db_session.add(operador)
    db_session.flush()

    edicion = client.patch(
        f"/api/v1/organizaciones/{organizacion.id}",
        headers=_csrf(administrador),
        json={"nombre": "Municipio Renombrado"},
    )
    assert edicion.status_code == 200
    assert edicion.json()["nombre"] == "Municipio Renombrado"

    cambio_tipo = client.patch(
        f"/api/v1/organizaciones/{organizacion.id}",
        headers=_csrf(administrador),
        json={"tipo": "ONG"},
    )
    assert cambio_tipo.status_code == 409

    version_anterior = operador.version_sesion
    baja = client.delete(
        f"/api/v1/organizaciones/{organizacion.id}",
        headers=_csrf(administrador),
    )
    assert baja.status_code == 204
    db_session.refresh(organizacion)
    db_session.refresh(operador)
    assert organizacion.activa is False
    assert operador.activo is False
    assert operador.version_sesion == version_anterior + 1

    baja_repetida = client.delete(
        f"/api/v1/organizaciones/{organizacion.id}",
        headers=_csrf(administrador),
    )
    assert baja_repetida.status_code == 204
    db_session.refresh(operador)
    assert operador.version_sesion == version_anterior + 1

    recuperacion = client.patch(
        f"/api/v1/organizaciones/{organizacion.id}",
        headers=_csrf(administrador),
        json={"activa": True},
    )
    assert recuperacion.status_code == 200
    assert recuperacion.json()["activa"] is True
    db_session.refresh(operador)
    assert operador.activo is False


def test_listado_incluye_organizaciones_inactivas(
    client: TestClient,
    db_session: Session,
) -> None:
    organizacion = Organizacion(
        tipo=TipoOrganizacion.ONG,
        nombre="ONG Inactiva",
        activa=False,
    )
    db_session.add(organizacion)
    db_session.flush()

    response = client.get("/api/v1/organizaciones")

    assert response.status_code == 200
    assert {
        "id": organizacion.id,
        "nombre": "ONG Inactiva",
        "tipo": "ONG",
        "activa": False,
        "ong_nacional_id": None,
    } in response.json()


def test_alta_exige_csrf_y_rol_administrador(
    client: TestClient,
    db_session: Session,
    administrador: Usuario,
) -> None:
    sin_csrf = client.post(
        "/api/v1/organizaciones",
        json={"nombre": "ONG sin CSRF", "tipo": "ONG"},
    )
    assert sin_csrf.status_code == 403

    municipio = Organizacion(
        tipo=TipoOrganizacion.MUNICIPIO,
        nombre="Municipio sin permisos",
    )
    db_session.add(municipio)
    db_session.flush()
    operador = Usuario(
        email="operador-sin-permisos@rescuesync.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.OPERADOR_MUNICIPAL,
        organizacion_id=municipio.id,
    )
    db_session.add(operador)
    db_session.flush()
    client.cookies.set(
        "rescuesync_session",
        crear_valor_sesion(operador.id, operador.version_sesion),
        path="/api/v1",
    )

    sin_rol = client.post(
        "/api/v1/organizaciones",
        headers=_csrf(operador),
        json={"nombre": "ONG sin rol", "tipo": "ONG"},
    )

    assert sin_rol.status_code == 403
    client.cookies.set(
        "rescuesync_session",
        crear_valor_sesion(administrador.id, administrador.version_sesion),
        path="/api/v1",
    )


def test_crear_ong_sin_correo_configura_acceso_automatico(
    client: TestClient,
    db_session: Session,
    administrador: Usuario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "nacional_aprovisionamiento_login", "emisor-local")
    monkeypatch.setattr(
        settings,
        "nacional_aprovisionamiento_password",
        SecretStr("secreto-integracion"),
    )
    nacional_id, cuenta_id = uuid4(), uuid4()
    with respx.mock as mock:
        base = str(settings.nacional_base_url).rstrip("/")
        mock.post(f"{base}/login").respond(
            200,
            json={
                "access_token": "token-emisor",
                "token_type": "bearer",
                "expires_in": 1800,
            },
        )
        ruta = mock.put(
            re.compile(re.escape(base) + r"/integraciones/ongs/.*")
        ).respond(
            200,
            json={
                "ong": {
                    "id": str(nacional_id),
                    "nombre": "Automática",
                    "estado": "PENDIENTE",
                },
                "cuentaId": str(cuenta_id),
                "identificadorLogin": "tecnica-ong-automatica",
            },
        )
        response = client.post(
            "/api/v1/organizaciones",
            headers=_csrf(administrador),
            json={"nombre": "Automática", "tipo": "ONG"},
        )
        assert response.status_code == 201
        assert response.json()["ong_nacional_id"] == str(nacional_id)
        request = json.loads(ruta.calls[0].request.content)
        assert request["emailContacto"] is None
        assert "identificadorInstitucional" not in request
        assert len(request["password"]) >= 32
        acceso = db_session.get(AccesoNacional, response.json()["id"])
        assert acceso is not None and acceso.cuenta_id == cuenta_id
        assert request["password"] not in response.text
        assert request["password"] not in acceso.secreto_cifrado
        assert (
            Fernet(settings.nacional_encryption_key.get_secret_value())
            .decrypt(acceso.secreto_cifrado.encode())
            .decode()
            == request["password"]
        )


def test_timeout_conserva_alta_y_reintenta_sin_duplicar(
    client: TestClient,
    db_session: Session,
    administrador: Usuario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "nacional_aprovisionamiento_login", "emisor-local")
    monkeypatch.setattr(
        settings,
        "nacional_aprovisionamiento_password",
        SecretStr("secreto-integracion"),
    )
    with respx.mock as mock:
        base = str(settings.nacional_base_url).rstrip("/")
        mock.post(f"{base}/login").respond(
            200,
            json={
                "access_token": "token-emisor",
                "token_type": "bearer",
                "expires_in": 1800,
            },
        )
        ruta = mock.put(re.compile(re.escape(base) + r"/integraciones/ongs/.*")).mock(
            side_effect=httpx.ReadTimeout("resultado incierto")
        )
        alta = client.post(
            "/api/v1/organizaciones",
            headers=_csrf(administrador),
            json={"nombre": "Reintento", "tipo": "ONG"},
        )
        assert alta.status_code == 201 and alta.json()["ong_nacional_id"] is None
        organizacion_id = alta.json()["id"]
        pendiente = db_session.get(AprovisionamientoNacional, organizacion_id)
        assert pendiente is not None
        primera = ruta.calls[0].request
        nacional_id = uuid4()
        ruta.respond(
            200,
            json={
                "ong": {
                    "id": str(nacional_id),
                    "nombre": "Reintento",
                    "estado": "PENDIENTE",
                },
                "cuentaId": str(uuid4()),
                "identificadorLogin": "tecnica-reintento",
            },
        )
        segunda = client.post(
            f"/api/v1/organizaciones/{organizacion_id}/aprovisionamiento-nacional",
            headers=_csrf(administrador),
        )
        assert segunda.status_code == 200 and segunda.json()["ong_nacional_id"] == str(
            nacional_id
        )
        assert ruta.calls[1].request.url == primera.url
        assert ruta.calls[1].request.content == primera.content
        assert (
            db_session.scalar(
                select(func.count()).select_from(AprovisionamientoNacional)
            )
            == 1
        )
        assert (
            client.post(
                f"/api/v1/organizaciones/{organizacion_id}/aprovisionamiento-nacional"
            ).status_code
            == 403
        )
