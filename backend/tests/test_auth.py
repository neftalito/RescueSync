import time
from collections.abc import Iterator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.dependencies import requerir_operacion
from app.core.config import get_settings
from app.core.permissions import OperacionProtegida
from app.core.security import (
    crear_token_csrf,
    crear_valor_sesion,
    generar_password_hash,
)
from app.db.models import Organizacion, RolUsuario, TipoOrganizacion, Usuario
from app.db.session import SessionLocal, get_db
from app.main import app
from app.services.auth import PasswordActualIncorrectaError, cambiar_password_propia

PASSWORD = "Una-clave-segura-2026"

ROLES_CON_ORGANIZACION: dict[RolUsuario, tuple[TipoOrganizacion, str, str]] = {
    RolUsuario.OPERADOR_MUNICIPAL: (
        TipoOrganizacion.MUNICIPIO,
        "Municipio RBAC",
        "municipio-rbac@rescuesync.org",
    ),
    RolUsuario.COORDINADOR_REGIONAL: (
        TipoOrganizacion.CENTRO_COORDINADOR,
        "Centro RBAC",
        "coordinador-rbac@rescuesync.org",
    ),
    RolUsuario.REPRESENTANTE_ONG: (
        TipoOrganizacion.ONG,
        "ONG RBAC",
        "ong-rbac@rescuesync.org",
    ),
}

ROLES_FUNCIONALES_POR_OPERACION: dict[
    OperacionProtegida,
    frozenset[RolUsuario],
] = {
    OperacionProtegida.REGISTRAR_EMERGENCIA: frozenset({RolUsuario.OPERADOR_MUNICIPAL}),
    OperacionProtegida.GESTIONAR_LOTES: frozenset({RolUsuario.COORDINADOR_REGIONAL}),
    OperacionProtegida.GESTIONAR_CATALOGO_NACIONAL: frozenset(
        {RolUsuario.ADMINISTRADOR}
    ),
    OperacionProtegida.PRESENTAR_OFERTA: frozenset({RolUsuario.REPRESENTANTE_ONG}),
}


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
def usuarios_por_rol(db_session: Session) -> dict[RolUsuario, Usuario]:
    """Crea un contexto vigente representativo para cada rol local."""

    password_hash = generar_password_hash(PASSWORD)
    usuarios: dict[RolUsuario, Usuario] = {}

    for rol, (tipo, nombre, email) in ROLES_CON_ORGANIZACION.items():
        organizacion = Organizacion(tipo=tipo, nombre=nombre)
        db_session.add(organizacion)
        db_session.flush()
        usuario = Usuario(
            organizacion_id=organizacion.id,
            email=email,
            password_hash=password_hash,
            rol=rol,
        )
        db_session.add(usuario)
        db_session.flush()
        usuarios[rol] = usuario

    auditor = Usuario(
        organizacion_id=None,
        email="auditor-rbac@rescuesync.org",
        password_hash=password_hash,
        rol=RolUsuario.AUDITOR_DIRECTIVO,
    )
    db_session.add(auditor)
    db_session.flush()
    usuarios[RolUsuario.AUDITOR_DIRECTIVO] = auditor
    administrador = Usuario(
        organizacion_id=None,
        email="admin-rbac@rescuesync.org",
        password_hash=password_hash,
        rol=RolUsuario.ADMINISTRADOR,
    )
    db_session.add(administrador)
    db_session.flush()
    usuarios[RolUsuario.ADMINISTRADOR] = administrador
    return usuarios


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
        "requiere_cambio_password": False,
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


def test_cambio_password_renueva_sesion_e_invalida_la_anterior(
    client: TestClient,
    db_session: Session,
    usuario_municipal: Usuario,
) -> None:
    login = _iniciar_sesion(client)
    csrf = login.json()["csrf_token"]
    cookie_anterior = client.cookies.get("rescuesync_session")

    response = client.post(
        "/api/v1/auth/password",
        headers={"X-CSRF-Token": csrf},
        json={
            "password_actual": PASSWORD,
            "password_nueva": "Otra-clave-segura-2026",
        },
    )

    assert response.status_code == 200
    assert response.json()["usuario"]["requiere_cambio_password"] is False
    assert usuario_municipal.version_sesion == 2
    assert client.get("/api/v1/auth/me").status_code == 200

    client.cookies.set(
        "rescuesync_session",
        cookie_anterior,
        path="/api/v1",
    )
    assert client.get("/api/v1/auth/me").status_code == 401
    db_session.expire_all()


def test_cambio_password_rechaza_la_clave_actual_incorrecta(
    client: TestClient,
    usuario_municipal: Usuario,
) -> None:
    login = _iniciar_sesion(client)

    response = client.post(
        "/api/v1/auth/password",
        headers={"X-CSRF-Token": login.json()["csrf_token"]},
        json={
            "password_actual": "clave-incorrecta",
            "password_nueva": "Otra-clave-segura-2026",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "La contraseña actual es incorrecta."}


def test_cambio_password_relee_un_restablecimiento_administrativo_con_bloqueo() -> None:
    email = "carrera-password@rescuesync.org"
    password_restablecida = "Clave-restablecida-2026"
    with SessionLocal.begin() as preparacion:
        preparacion.execute(delete(Usuario).where(Usuario.email == email))
        usuario = Usuario(
            email=email,
            password_hash=generar_password_hash(PASSWORD),
            rol=RolUsuario.AUDITOR_DIRECTIVO,
        )
        preparacion.add(usuario)
        preparacion.flush()
        usuario_id = usuario.id

    sesion_usuario = SessionLocal()
    try:
        usuario_desactualizado = sesion_usuario.get(Usuario, usuario_id)
        assert usuario_desactualizado is not None

        with SessionLocal.begin() as sesion_administrador:
            usuario_restablecido = sesion_administrador.get(Usuario, usuario_id)
            assert usuario_restablecido is not None
            usuario_restablecido.password_hash = generar_password_hash(
                password_restablecida
            )
            usuario_restablecido.version_sesion += 1

        with pytest.raises(PasswordActualIncorrectaError):
            cambiar_password_propia(
                sesion_usuario,
                usuario_desactualizado,
                PASSWORD,
                "Otra-clave-segura-2026",
            )
        assert usuario_desactualizado.version_sesion == 2
    finally:
        sesion_usuario.rollback()
        sesion_usuario.close()
        with SessionLocal.begin() as limpieza:
            limpieza.execute(delete(Usuario).where(Usuario.email == email))


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


def test_sesion_expirada_es_rechazada(
    client: TestClient,
    usuario_municipal: Usuario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _iniciar_sesion(client)
    instante_expirado = time.time() + get_settings().session_max_age_seconds + 1

    def obtener_instante_expirado() -> float:
        return instante_expirado

    monkeypatch.setattr(time, "time", obtener_instante_expirado)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "La sesión no es válida o expiró."}


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


@pytest.mark.parametrize("rol", list(RolUsuario))
def test_endpoint_de_sesion_reautentica_todos_los_roles(
    client: TestClient,
    usuarios_por_rol: dict[RolUsuario, Usuario],
    rol: RolUsuario,
) -> None:
    usuario = usuarios_por_rol[rol]
    client.cookies.set(
        "rescuesync_session",
        crear_valor_sesion(usuario.id),
        path="/api/v1",
    )

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["usuario"]["rol"] == rol


@pytest.mark.parametrize("rol", list(RolUsuario))
def test_endpoint_logout_reautentica_y_autoriza_todos_los_roles(
    client: TestClient,
    usuarios_por_rol: dict[RolUsuario, Usuario],
    rol: RolUsuario,
) -> None:
    usuario = usuarios_por_rol[rol]
    client.cookies.set(
        "rescuesync_session",
        crear_valor_sesion(usuario.id),
        path="/api/v1",
    )

    response = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": crear_token_csrf(usuario.id)},
    )

    assert response.status_code == 204


@pytest.mark.parametrize(
    ("operacion", "roles_permitidos"),
    list(ROLES_FUNCIONALES_POR_OPERACION.items()),
)
def test_matriz_rbac_permite_y_deniega_operaciones_para_cada_rol(
    usuarios_por_rol: dict[RolUsuario, Usuario],
    operacion: OperacionProtegida,
    roles_permitidos: frozenset[RolUsuario],
) -> None:
    autorizar = requerir_operacion(operacion)

    for rol, usuario in usuarios_por_rol.items():
        if rol in roles_permitidos:
            assert autorizar(usuario) is usuario
            continue

        with pytest.raises(HTTPException) as error:
            autorizar(usuario)

        assert error.value.status_code == 403
        assert error.value.detail == "No tenés permisos para realizar esta operación."
