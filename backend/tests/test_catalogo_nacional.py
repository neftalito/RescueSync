"""Administración delegada del catálogo: RBAC local, CSRF y rol nacional."""

import json
from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    crear_token_csrf,
    crear_valor_sesion,
    generar_password_hash,
)
from app.db.models import Organizacion, RolUsuario, TipoOrganizacion, Usuario
from app.db.session import get_db
from app.main import app

NACIONAL = str(get_settings().nacional_base_url).rstrip("/")
URL = "/api/v1/catalogo-nacional"
TOKEN = "jwt-catalogo-de-prueba"
DATOS = {
    "codigo": "ALIMENTOS",
    "nombre": "Alimentos",
    "tipo": "SUMINISTRO",
    "unidad": "kg",
    "admiteFracciones": True,
}
CAPACIDAD = {"id": str(uuid4()), **DATOS}


@pytest.fixture
def usuarios(db_session: Session) -> dict[RolUsuario, Usuario]:
    resultado = {}
    for rol in RolUsuario:
        tipo = {
            RolUsuario.OPERADOR_MUNICIPAL: TipoOrganizacion.MUNICIPIO,
            RolUsuario.COORDINADOR_REGIONAL: TipoOrganizacion.CENTRO_COORDINADOR,
            RolUsuario.REPRESENTANTE_ONG: TipoOrganizacion.ONG,
        }.get(rol)
        organizacion = (
            Organizacion(nombre=f"Catálogo {rol}", tipo=tipo) if tipo else None
        )
        if organizacion:
            db_session.add(organizacion)
            db_session.flush()
        usuario = Usuario(
            email=f"catalogo-{rol.lower()}@example.org",
            rol=rol,
            password_hash=generar_password_hash("password-de-prueba"),
            organizacion_id=organizacion.id if organizacion else None,
        )
        db_session.add(usuario)
        db_session.flush()
        resultado[rol] = usuario
    return resultado


@pytest.fixture
def catalogo_client(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setattr(get_settings(), "nacional_catalogo_login", "catalogo-prueba")
    monkeypatch.setattr(
        get_settings(),
        "nacional_catalogo_password",
        SecretStr("password-nacional-prueba"),
    )

    def database() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def autenticar(client: TestClient, usuario: Usuario) -> dict[str, str]:
    client.cookies.set(
        "rescuesync_session", crear_valor_sesion(usuario.id), path="/api/v1"
    )
    return {"X-CSRF-Token": crear_token_csrf(usuario.id)}


def remoto(mock: respx.MockRouter, rol: str = "ADMIN_NACIONAL") -> None:
    mock.post(f"{NACIONAL}/login").respond(
        200, json={"access_token": TOKEN, "token_type": "bearer", "expires_in": 1800}
    )
    mock.get(f"{NACIONAL}/me").respond(
        200, json={"id": str(uuid4()), "rol": rol, "ongId": None}
    )


@pytest.mark.parametrize("codigo", ["ALIMENTOS_SIN_GLUTEN", "ALIMENTOS-SIN-GLUTEN"])
def test_admin_consulta_unidades_y_crea_sin_exponer_credenciales(
    catalogo_client: TestClient,
    usuarios: dict[RolUsuario, Usuario],
    codigo: str,
) -> None:
    datos = {**DATOS, "codigo": codigo}
    capacidad = {**CAPACIDAD, "codigo": codigo}
    headers = autenticar(catalogo_client, usuarios[RolUsuario.ADMINISTRADOR])
    with respx.mock as mock:
        remoto(mock)
        mock.get(f"{NACIONAL}/unidades").respond(
            200, json=[{"codigo": "kg", "nombre": "Kilogramos"}]
        )
        mock.get(f"{NACIONAL}/capacidades").respond(200, json=[capacidad])
        alta = mock.post(f"{NACIONAL}/capacidades").respond(201, json=capacidad)

        unidades = catalogo_client.get(f"{URL}/unidades")
        listado = catalogo_client.get(f"{URL}/capacidades")
        creada = catalogo_client.post(f"{URL}/capacidades", headers=headers, json=datos)

        assert unidades.status_code == listado.status_code == 200
        assert creada.status_code == 201 and creada.json() == capacidad
        assert creada.headers["cache-control"] == "no-store"
        assert TOKEN not in creada.text and "password" not in creada.text
        assert json.loads(alta.calls[0].request.content) == datos
        assert alta.calls[0].request.headers["Authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize(
    "rol", [rol for rol in RolUsuario if rol != RolUsuario.ADMINISTRADOR]
)
def test_roles_locales_no_administrativos_no_llaman_a_nacional(
    catalogo_client: TestClient,
    usuarios: dict[RolUsuario, Usuario],
    rol: RolUsuario,
) -> None:
    headers = autenticar(catalogo_client, usuarios[rol])
    with respx.mock() as mock:
        assert catalogo_client.get(f"{URL}/capacidades").status_code == 403
        assert catalogo_client.get(f"{URL}/unidades").status_code == 403
        assert (
            catalogo_client.post(
                f"{URL}/capacidades", headers=headers, json=DATOS
            ).status_code
            == 403
        )
        assert not mock.calls


def test_crear_requiere_sesion_y_csrf_sin_hacer_http(
    catalogo_client: TestClient,
    usuarios: dict[RolUsuario, Usuario],
) -> None:
    with respx.mock() as mock:
        assert catalogo_client.post(f"{URL}/capacidades", json=DATOS).status_code == 401
        autenticar(catalogo_client, usuarios[RolUsuario.ADMINISTRADOR])
        assert catalogo_client.post(f"{URL}/capacidades", json=DATOS).status_code == 403
        assert not mock.calls


def test_cuenta_integracion_lee_pero_no_crea_capacidades(
    catalogo_client: TestClient,
    usuarios: dict[RolUsuario, Usuario],
) -> None:
    headers = autenticar(catalogo_client, usuarios[RolUsuario.ADMINISTRADOR])
    with respx.mock as mock:
        remoto(mock, "INTEGRACION")
        mock.get(f"{NACIONAL}/unidades").respond(200, json=[])
        assert catalogo_client.get(f"{URL}/unidades").status_code == 200
        creada = catalogo_client.post(f"{URL}/capacidades", headers=headers, json=DATOS)
        assert creada.status_code == 403 and "ADMIN_NACIONAL" in creada.text
        assert not any(
            call.request.method == "POST"
            and call.request.url.path.endswith("/capacidades")
            for call in mock.calls
        )


@pytest.mark.parametrize("estado", [403, 409, 422, 504])
def test_errores_remotos_son_seguros_y_no_se_reintenta_el_alta(
    catalogo_client: TestClient,
    usuarios: dict[RolUsuario, Usuario],
    estado: int,
) -> None:
    headers = autenticar(catalogo_client, usuarios[RolUsuario.ADMINISTRADOR])
    with respx.mock as mock:
        remoto(mock)
        alta = mock.post(f"{NACIONAL}/capacidades")
        if estado == 504:
            alta.mock(side_effect=httpx.ReadTimeout("secreto-remoto"))
        else:
            alta.respond(estado, json={"detail": "secreto-remoto"})
        response = catalogo_client.post(
            f"{URL}/capacidades", headers=headers, json=DATOS
        )
        assert response.status_code == estado
        assert "secreto-remoto" not in response.text and TOKEN not in response.text
        assert alta.call_count == 1


def test_administrador_no_puede_crear_unidades(
    catalogo_client: TestClient,
    usuarios: dict[RolUsuario, Usuario],
) -> None:
    headers = autenticar(catalogo_client, usuarios[RolUsuario.ADMINISTRADOR])
    with respx.mock() as mock:
        response = catalogo_client.post(
            f"{URL}/unidades",
            headers=headers,
            json={"codigo": "nueva", "nombre": "Nueva"},
        )
        assert response.status_code == 405 and not mock.calls
