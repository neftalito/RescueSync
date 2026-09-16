from collections.abc import Iterator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.api.dependencies import requerir_roles
from app.core.security import generar_password_hash
from app.db.models import Organizacion, RolUsuario, TipoOrganizacion, Usuario
from app.db.session import get_db
from app.main import app

PASSWORD = "Una-clave-segura-2026"


@pytest.fixture
def usuario_municipal(db_session: Session) -> Usuario:
    organizacion = Organizacion(
        tipo=TipoOrganizacion.MUNICIPIO,
        nombre="Municipio de Prueba",
    )
    db_session.add(organizacion)
    db_session.flush()
    usuario = Usuario(
        organizacion_id=organizacion.id,
        email="operador@municipio.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.OPERADOR_MUNICIPAL,
    )
    db_session.add(usuario)
    db_session.flush()
    return usuario


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def usar_sesion_de_prueba() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = usar_sesion_de_prueba
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _iniciar_sesion(client: TestClient) -> Response:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "  OPERADOR@MUNICIPIO.ORG ",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200
    return response


def test_login_crea_cookie_segura_y_devuelve_contexto_vigente(
    client: TestClient,
    usuario_municipal: Usuario,
) -> None:
    response = _iniciar_sesion(client)
    payload = response.json()

    assert payload["usuario"] == {
        "id": usuario_municipal.id,
        "email": "operador@municipio.org",
        "rol": "OPERADOR_MUNICIPAL",
        "organizacion": {
            "id": usuario_municipal.organizacion_id,
            "nombre": "Municipio de Prueba",
            "tipo": "MUNICIPIO",
        },
    }
    assert isinstance(payload["csrf_token"], str)
    set_cookie = response.headers.get("set-cookie", "")
    assert "rescuesync_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/api/v1" in set_cookie

    session_response = client.get("/api/v1/auth/me")
    assert session_response.status_code == 200
    assert session_response.json()["usuario"] == payload["usuario"]


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("operador@municipio.org", "incorrecta"),
        ("nadie@municipio.org", PASSWORD),
    ],
)
def test_login_no_revela_si_el_correo_existe(
    client: TestClient,
    usuario_municipal: Usuario,
    email: str,
    password: str,
) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "El correo o la contraseña son incorrectos."}


def test_login_rechaza_usuario_inactivo(
    client: TestClient,
    db_session: Session,
    usuario_municipal: Usuario,
) -> None:
    usuario_municipal.activo = False
    db_session.flush()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": usuario_municipal.email, "password": PASSWORD},
    )

    assert response.status_code == 401


def test_sesion_deja_de_ser_valida_si_se_inactiva_la_organizacion(
    client: TestClient,
    db_session: Session,
    usuario_municipal: Usuario,
) -> None:
    _iniciar_sesion(client)
    assert usuario_municipal.organizacion is not None
    usuario_municipal.organizacion.activa = False
    db_session.flush()
    db_session.expire_all()

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_sesion_relee_rol_y_organizacion_desde_la_base(
    client: TestClient,
    db_session: Session,
    usuario_municipal: Usuario,
) -> None:
    _iniciar_sesion(client)
    usuario_municipal.rol = RolUsuario.AUDITOR_DIRECTIVO
    usuario_municipal.organizacion_id = None
    db_session.flush()
    db_session.expire_all()

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["usuario"]["rol"] == "AUDITOR_DIRECTIVO"
    assert response.json()["usuario"]["organizacion"] is None


def test_sesion_rechaza_cookie_ausente_o_manipulada(
    client: TestClient,
    usuario_municipal: Usuario,
) -> None:
    sin_cookie = client.get("/api/v1/auth/me")
    client.cookies.set(
        "rescuesync_session",
        "contenido-manipulado",
        path="/api/v1",
    )
    manipulada = client.get("/api/v1/auth/me")

    assert sin_cookie.status_code == 401
    assert manipulada.status_code == 401


def test_logout_exige_csrf_y_elimina_la_sesion(
    client: TestClient,
    usuario_municipal: Usuario,
) -> None:
    payload = _iniciar_sesion(client).json()

    sin_csrf = client.post("/api/v1/auth/logout")
    assert sin_csrf.status_code == 403
    assert client.get("/api/v1/auth/me").status_code == 200

    response = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": str(payload["csrf_token"])},
    )

    assert response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_dependencia_rbac_permite_y_deniega_roles(
    usuario_municipal: Usuario,
) -> None:
    solo_municipio = requerir_roles(RolUsuario.OPERADOR_MUNICIPAL)
    solo_ong = requerir_roles(RolUsuario.REPRESENTANTE_ONG)

    assert solo_municipio(usuario_municipal) is usuario_municipal
    with pytest.raises(HTTPException) as error:
        solo_ong(usuario_municipal)

    assert error.value.status_code == 403
    assert error.value.detail == "No tenés permisos para realizar esta operación."
