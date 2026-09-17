from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import (
    crear_token_csrf,
    crear_valor_sesion,
    generar_password_hash,
    verificar_password,
)
from app.db.models import Organizacion, RolUsuario, TipoOrganizacion, Usuario
from app.db.session import get_db
from app.main import app

PASSWORD = "Clave-segura-2026"


@pytest.fixture
def administrador(db_session: Session) -> Usuario:
    usuario = Usuario(
        email="admin-pruebas@rescuesync.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.ADMINISTRADOR,
    )
    db_session.add(usuario)
    db_session.flush()
    return usuario


@pytest.fixture
def municipio(db_session: Session) -> Organizacion:
    organizacion = Organizacion(
        tipo=TipoOrganizacion.MUNICIPIO,
        nombre="Municipio Administración",
    )
    db_session.add(organizacion)
    db_session.flush()
    return organizacion


@pytest.fixture
def client(db_session: Session, administrador: Usuario) -> Iterator[TestClient]:
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


def test_administrador_lista_usuarios_y_organizaciones(
    client: TestClient,
    administrador: Usuario,
    municipio: Organizacion,
) -> None:
    usuarios = client.get("/api/v1/usuarios")
    organizaciones = client.get("/api/v1/organizaciones")

    assert usuarios.status_code == 200
    assert any(usuario["email"] == administrador.email for usuario in usuarios.json())
    assert organizaciones.status_code == 200
    assert {
        "id": municipio.id,
        "nombre": municipio.nombre,
        "tipo": "MUNICIPIO",
    } in organizaciones.json()


def test_gestion_usuarios_exige_rol_administrador(
    client: TestClient,
    db_session: Session,
    administrador: Usuario,
    municipio: Organizacion,
) -> None:
    operador = Usuario(
        email="operador-sin-permiso@rescuesync.org",
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

    response = client.get("/api/v1/usuarios")

    assert response.status_code == 403
    client.cookies.set(
        "rescuesync_session",
        crear_valor_sesion(administrador.id, administrador.version_sesion),
        path="/api/v1",
    )


def test_gestion_usuarios_bloquea_admin_con_cambio_pendiente(
    client: TestClient,
    db_session: Session,
    administrador: Usuario,
) -> None:
    administrador.requiere_cambio_password = True
    db_session.flush()

    response = client.get("/api/v1/usuarios")

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Debés cambiar tu contraseña antes de continuar."
    }


def test_administrador_crea_edita_desactiva_y_reactiva_usuario(
    client: TestClient,
    db_session: Session,
    administrador: Usuario,
    municipio: Organizacion,
) -> None:
    alta = client.post(
        "/api/v1/usuarios",
        headers=_csrf(administrador),
        json={
            "email": " NUEVO@RESCUESYNC.ORG ",
            "password": "Temporal-2026",
            "rol": "OPERADOR_MUNICIPAL",
            "organizacion_id": municipio.id,
        },
    )
    assert alta.status_code == 201
    usuario_id = alta.json()["id"]
    usuario = db_session.get(Usuario, usuario_id)
    assert usuario is not None
    assert usuario.email == "nuevo@rescuesync.org"
    assert usuario.requiere_cambio_password is True
    assert verificar_password("Temporal-2026", usuario.password_hash)

    edicion = client.patch(
        f"/api/v1/usuarios/{usuario_id}",
        headers=_csrf(administrador),
        json={
            "email": "auditor-editado@rescuesync.org",
            "rol": "AUDITOR_DIRECTIVO",
            "organizacion_id": None,
        },
    )
    assert edicion.status_code == 200
    assert edicion.json()["rol"] == "AUDITOR_DIRECTIVO"
    assert edicion.json()["organizacion"] is None

    baja = client.delete(
        f"/api/v1/usuarios/{usuario_id}",
        headers=_csrf(administrador),
    )
    assert baja.status_code == 204
    db_session.refresh(usuario)
    assert usuario.activo is False
    assert usuario.version_sesion == 2

    reactivacion = client.patch(
        f"/api/v1/usuarios/{usuario_id}",
        headers=_csrf(administrador),
        json={"activo": True},
    )
    assert reactivacion.status_code == 200
    assert reactivacion.json()["activo"] is True


def test_alta_rechaza_email_duplicado(
    client: TestClient,
    administrador: Usuario,
) -> None:
    duplicado = client.post(
        "/api/v1/usuarios",
        headers=_csrf(administrador),
        json={
            "email": administrador.email.upper(),
            "password": "Temporal-2026",
            "rol": "AUDITOR_DIRECTIVO",
            "organizacion_id": None,
        },
    )

    assert duplicado.status_code == 409


def test_alta_rechaza_organizacion_incompatible(
    client: TestClient,
    administrador: Usuario,
    municipio: Organizacion,
) -> None:
    incompatible = client.post(
        "/api/v1/usuarios",
        headers=_csrf(administrador),
        json={
            "email": "ong-invalida@rescuesync.org",
            "password": "Temporal-2026",
            "rol": "REPRESENTANTE_ONG",
            "organizacion_id": municipio.id,
        },
    )

    assert incompatible.status_code == 422


def test_administrador_no_puede_quitarse_su_propio_acceso(
    client: TestClient,
    administrador: Usuario,
) -> None:
    response = client.delete(
        f"/api/v1/usuarios/{administrador.id}",
        headers=_csrf(administrador),
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "No podés quitar tu propio acceso de administrador."
    }


def test_restablecer_password_es_temporal_e_invalida_sesiones(
    client: TestClient,
    db_session: Session,
    administrador: Usuario,
) -> None:
    usuario = Usuario(
        email="auditor-reset@rescuesync.org",
        password_hash=generar_password_hash(PASSWORD),
        rol=RolUsuario.AUDITOR_DIRECTIVO,
    )
    db_session.add(usuario)
    db_session.flush()
    version_anterior = usuario.version_sesion

    response = client.put(
        f"/api/v1/usuarios/{usuario.id}/password",
        headers=_csrf(administrador),
        json={"password": "Temporal-nueva-2026"},
    )

    assert response.status_code == 200
    db_session.refresh(usuario)
    assert usuario.requiere_cambio_password is True
    assert usuario.version_sesion == version_anterior + 1
    assert verificar_password("Temporal-nueva-2026", usuario.password_hash)


def test_administrador_debe_usar_cambio_personal_para_su_clave(
    client: TestClient,
    administrador: Usuario,
) -> None:
    response = client.put(
        f"/api/v1/usuarios/{administrador.id}/password",
        headers=_csrf(administrador),
        json={"password": "Temporal-nueva-2026"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Usá el cambio de contraseña personal para modificar tu propia clave."
    }
