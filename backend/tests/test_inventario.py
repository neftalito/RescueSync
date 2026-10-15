"""Adaptador nacional con permisos locales, CSRF y credenciales cifradas."""

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    crear_token_csrf,
    crear_valor_sesion,
    generar_password_hash,
)
from app.db.models import (
    AccesoNacional,
    Organizacion,
    RolUsuario,
    TipoOrganizacion,
    Usuario,
)
from app.db.session import get_db
from app.integrations.nacional.cliente import ClienteNacional, ErrorNacional
from app.main import app
from app.schemas.inventario import CredencialTecnica
from app.services.acceso_nacional import credencial, importar_credencial
from app.services.inventario import estado_conexion

NACIONAL = str(get_settings().nacional_base_url).rstrip("/")
TOKEN = "jwt-nacional-confidencial"
CUENTA_ID = uuid4()
ONG_ID = uuid4()
RECURSO_ID = uuid4()
CAPACIDAD_ID = uuid4()
RECURSO = {
    "id": str(RECURSO_ID),
    "ongId": str(ONG_ID),
    "capacidadId": str(CAPACIDAD_ID),
    "codigoInterno": "AMB-01",
    "nombre": "Ambulancias",
    "capacidad": "Ambulancias",
    "unidad": "vehículos",
    "admiteFracciones": False,
    "cantidadTotal": "10.000",
    "cantidadComprometida": "4.000",
    "cantidadDisponible": "6.000",
    "activo": True,
    "actualizadoEn": "2026-10-08T12:00:00Z",
}


@pytest.fixture
def representante(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Usuario:
    monkeypatch.setattr(
        get_settings(),
        "nacional_encryption_key",
        SecretStr(Fernet.generate_key().decode()),
    )
    ong = Organizacion(
        tipo=TipoOrganizacion.ONG, nombre="Inventario ONG", ong_nacional_id=ONG_ID
    )
    db_session.add(ong)
    db_session.flush()
    usuario = Usuario(
        email="inventario@rescuesync.org",
        rol=RolUsuario.REPRESENTANTE_ONG,
        organizacion_id=ong.id,
        password_hash=generar_password_hash("password-seguro123"),
    )
    db_session.add(usuario)
    db_session.commit()
    return usuario


@pytest.fixture
def client(db_session: Session, representante: Usuario) -> Iterator[TestClient]:
    def database() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = database
    with TestClient(app) as test_client:
        test_client.cookies.set(
            "rescuesync_session",
            crear_valor_sesion(representante.id, representante.version_sesion),
            path="/api/v1",
        )
        yield test_client
    app.dependency_overrides.clear()


def csrf(usuario: Usuario) -> dict[str, str]:
    return {"X-CSRF-Token": crear_token_csrf(usuario.id, usuario.version_sesion)}


def remoto(mock: respx.MockRouter, ong_id: str = str(ONG_ID)) -> None:
    mock.post(f"{NACIONAL}/login").respond(
        200, json={"access_token": TOKEN, "token_type": "bearer", "expires_in": 1800}
    )
    mock.get(f"{NACIONAL}/me").respond(
        200,
        json={
            "id": str(CUENTA_ID),
            "rol": "ONG",
            "ongId": ong_id,
            "proposito": "TECNICA_ONG",
        },
    )


def conexion(client: TestClient, usuario: Usuario) -> httpx.Response:
    session = next(app.dependency_overrides[get_db]())
    cliente = ClienteNacional(NACIONAL, 10)
    try:
        importar_credencial(
            session,
            usuario.organizacion_id,
            CredencialTecnica(
                cuenta_id=CUENTA_ID,
                ong_id=ONG_ID,
                identificador_login="ong@nacional.org",
                password="password-nacional123",
            ),
            cliente,
        )
        session.commit()
        credencial(session, usuario, cliente)
    except ErrorNacional as error:
        session.rollback()
        return httpx.Response(error.status)
    finally:
        cliente.close()
    return client.get("/api/v1/mi-ong/conexion")


CERTIFICACION = {
    "id": str(uuid4()),
    "codigo": "SANITARIA",
    "revision": 1,
    "nombre": "Respuesta sanitaria",
    "activa": True,
    "alcances": [
        {
            "capacidadId": str(CAPACIDAD_ID),
            "codigo": "PARAMEDICOS",
            "nombre": "Personal paramédico",
            "tipo": "PERSONAL",
            "unidad": "personas",
            "admiteFracciones": False,
            "activa": True,
            "riesgoMaximo": "ALTA",
        }
    ],
}
PERFIL = {
    "ongId": str(ONG_ID),
    "estadoOng": "HABILITADA",
    "evaluadoEn": "2026-10-14T12:00:00Z",
    "acreditaciones": [
        {
            "id": str(uuid4()),
            "certificacion": CERTIFICACION,
            "emisor": "Autoridad",
            "numeroCredencial": "OFICIAL-1",
            "vigenteDesde": "2025-01-01T00:00:00Z",
            "vigenteHasta": "2026-01-01T00:00:00Z",
            "estado": "OTORGADA",
            "estadoVigencia": "VENCIDA",
            "revocadaEn": None,
            "motivoRevocacion": None,
            "motivos": [
                {
                    "codigo": "ACREDITACION_VENCIDA",
                    "mensaje": "La acreditación venció.",
                    "capacidadId": None,
                }
            ],
        }
    ],
    "capacidadesHabilitadas": [],
    "motivosInstitucionales": [],
}


def test_consulta_certificaciones_de_la_ong_vinculada_sin_exponer_token(
    client: TestClient,
    representante: Usuario,
) -> None:
    with respx.mock as mock:
        remoto(mock)
        assert conexion(client, representante).status_code == 200
        perfil = mock.get(f"{NACIONAL}/ongs/{ONG_ID}/certificaciones").respond(
            200, json=PERFIL
        )
        catalogo = mock.get(f"{NACIONAL}/certificaciones").respond(
            200, json=[CERTIFICACION]
        )
        response = client.get(
            "/api/v1/mi-ong/certificaciones", params={"ongId": str(uuid4())}
        )
        assert response.status_code == 200 and response.json() == PERFIL
        assert (
            response.headers["cache-control"] == "no-store"
            and TOKEN not in response.text
        )
        assert perfil.calls[0].request.headers["authorization"] == f"Bearer {TOKEN}"
        response = client.get("/api/v1/mi-ong/catalogo-certificaciones")
        assert response.json() == [CERTIFICACION] and catalogo.called
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "modo,esperado",
    [
        ("timeout", 504),
        ("caida", 503),
        ("json", 502),
        ("ong-ajena", 502),
        ("401", 503),
        ("403", 403),
        ("404", 404),
    ],
)
def test_certificaciones_traduce_fallos_y_desconecta_credenciales_rechazadas(
    client: TestClient,
    representante: Usuario,
    db_session: Session,
    modo: str,
    esperado: int,
) -> None:
    with respx.mock as mock:
        remoto(mock)
        assert conexion(client, representante).status_code == 200
        ruta = mock.get(f"{NACIONAL}/ongs/{ONG_ID}/certificaciones")
        if modo == "timeout":
            ruta.side_effect = httpx.ReadTimeout("dato-interno-confidencial")
        elif modo == "caida":
            ruta.side_effect = httpx.ConnectError("dato-interno-confidencial")
        elif modo == "json":
            ruta.respond(200, json={"sql": "dato-interno-confidencial"})
        elif modo == "ong-ajena":
            ruta.respond(200, json={**PERFIL, "ongId": str(uuid4())})
        else:
            ruta.respond(int(modo), json={"detail": "dato-interno-confidencial"})
        response = client.get("/api/v1/mi-ong/certificaciones")
        assert response.status_code == esperado
        assert (
            "dato-interno-confidencial" not in response.text
            and TOKEN not in response.text
        )
        acceso = db_session.get(
            AccesoNacional, representante.organizacion_id, populate_existing=True
        )
        assert acceso is not None
        assert acceso.requiere_revision == (modo == "401")


def test_certificaciones_exigen_conexion_y_rol_local(
    client: TestClient,
    representante: Usuario,
    db_session: Session,
) -> None:
    assert client.get("/api/v1/mi-ong/certificaciones").status_code == 503
    representante.rol = RolUsuario.AUDITOR_DIRECTIVO
    representante.organizacion_id = None
    db_session.commit()
    assert client.get("/api/v1/mi-ong/certificaciones").status_code == 403


def test_conecta_sin_exponer_jwt_y_proxya_stock(
    client: TestClient, representante: Usuario, db_session: Session
) -> None:
    with respx.mock as mock:
        remoto(mock)
        assert conexion(client, representante).status_code == 200
        fila = db_session.get(AccesoNacional, representante.organizacion_id)
        assert fila is not None and TOKEN not in fila.token_cifrado
        estado = client.get("/api/v1/mi-ong/conexion")
        assert estado.status_code == 200 and estado.json()["conectada"], estado.text
        assert TOKEN not in estado.text
        ruta = mock.get(f"{NACIONAL}/ongs/{ONG_ID}/recursos").respond(
            200, json=[RECURSO]
        )
        response = client.get("/api/v1/mi-ong/recursos")
        assert response.status_code == 200 and response.json() == [RECURSO], (
            response.text
        )
        assert ruta.calls[0].request.headers["authorization"] == f"Bearer {TOKEN}"
        actualizacion = mock.patch(
            f"{NACIONAL}/ongs/{ONG_ID}/recursos/{RECURSO_ID}"
        ).respond(
            200,
            json={**RECURSO, "cantidadTotal": "12.000", "cantidadDisponible": "8.000"},
        )
        response = client.patch(
            f"/api/v1/mi-ong/recursos/{RECURSO_ID}",
            headers=csrf(representante),
            json={"cantidadTotal": "12", "actualizadoEn": RECURSO["actualizadoEn"]},
        )
        assert response.status_code == 200 and actualizacion.called
        assert (
            client.delete(
                "/api/v1/mi-ong/conexion", headers=csrf(representante)
            ).status_code
            == 405
        )


def test_cuenta_de_otra_ong_y_falta_de_vinculo_rechazados(
    client: TestClient, representante: Usuario, db_session: Session
) -> None:
    with respx.mock as mock:
        remoto(mock, str(uuid4()))
        assert conexion(client, representante).status_code == 403
        assert db_session.get(AccesoNacional, representante.organizacion_id) is None
        representante.organizacion.ong_nacional_id = None
        db_session.commit()
        assert client.get("/api/v1/mi-ong/recursos").status_code == 409


def test_conexion_expirada_se_renueva_y_version_local_no_elimina_acceso(
    client: TestClient, representante: Usuario, db_session: Session
) -> None:
    with respx.mock as mock:
        remoto(mock)
        assert conexion(client, representante).status_code == 200
        fila = db_session.get(AccesoNacional, representante.organizacion_id)
        assert fila is not None
        fila.expira_en = datetime.now(UTC) - timedelta(seconds=1)
        db_session.commit()
        assert client.get("/api/v1/mi-ong/conexion").json()["conectada"] is False
        mock.get(f"{NACIONAL}/ongs/{ONG_ID}/recursos").respond(200, json=[RECURSO])
        assert client.get("/api/v1/mi-ong/recursos").status_code == 200
        representante.version_sesion += 1
        db_session.commit()
        assert estado_conexion(db_session, representante).estado == "LISTA"


@pytest.mark.parametrize("status", [401, 403, 409, 422, 500])
def test_error_remoto_seguro(
    client: TestClient, representante: Usuario, status: int
) -> None:
    with respx.mock as mock:
        remoto(mock)
        assert conexion(client, representante).status_code == 200
        mock.get(f"{NACIONAL}/ongs/{ONG_ID}/recursos").respond(
            status, json={"detail": "sql interno " + TOKEN}
        )
        response = client.get("/api/v1/mi-ong/recursos")
        assert response.status_code == (
            502 if status == 500 else 503 if status == 401 else status
        )
        assert TOKEN not in response.text and "sql interno" not in response.text
        if status == 401:
            assert (
                client.get("/api/v1/mi-ong/conexion").json()["estado"]
                == "REQUIERE_REVISION"
            )


def test_timeout_no_reintenta_escritura(
    client: TestClient, representante: Usuario
) -> None:
    with respx.mock as mock:
        remoto(mock)
        assert conexion(client, representante).status_code == 200
        ruta = mock.post(f"{NACIONAL}/ongs/{ONG_ID}/recursos").mock(
            side_effect=httpx.ReadTimeout("detalle-sensible")
        )
        response = client.post(
            "/api/v1/mi-ong/recursos",
            headers=csrf(representante),
            json={
                "capacidadId": str(CAPACIDAD_ID),
                "codigoInterno": "AMB-02",
                "nombre": "Ambulancia",
                "cantidadTotal": "2",
            },
        )
        assert response.status_code == 504 and ruta.call_count == 1
        assert "detalle-sensible" not in response.text


def test_csrf_roles_y_logout(
    client: TestClient, representante: Usuario, db_session: Session
) -> None:
    assert client.post("/api/v1/mi-ong/recursos", json={}).status_code == 403
    with respx.mock as mock:
        remoto(mock)
        assert conexion(client, representante).status_code == 200
        assert (
            client.post("/api/v1/auth/logout", headers=csrf(representante)).status_code
            == 204
        )
        assert db_session.get(AccesoNacional, representante.organizacion_id) is not None
        client.cookies.clear()
        assert client.get("/api/v1/mi-ong/recursos").status_code == 401
    representante.rol = RolUsuario.AUDITOR_DIRECTIVO
    representante.organizacion = None
    db_session.commit()
    client.cookies.set(
        "rescuesync_session", crear_valor_sesion(representante.id), path="/api/v1"
    )
    assert client.get("/api/v1/mi-ong/conexion").status_code == 403
    assert (
        client.post(
            "/api/v1/mi-ong/registro-nacional",
            headers=csrf(representante),
            json=REGISTRO,
        ).status_code
        == 403
    )


def test_solo_admin_vincula_y_revoca_conexiones(
    client: TestClient, representante: Usuario, db_session: Session
) -> None:
    ruta = f"/api/v1/organizaciones/{representante.organizacion_id}/vinculo-nacional"
    assert (
        client.patch(
            ruta, headers=csrf(representante), json={"ong_nacional_id": str(ONG_ID)}
        ).status_code
        == 403
    )
    with respx.mock as mock:
        remoto(mock)
        assert conexion(client, representante).status_code == 200
    admin = Usuario(
        email="admin-inventario@rescuesync.org",
        rol=RolUsuario.ADMINISTRADOR,
        password_hash=generar_password_hash("admin-seguro123"),
    )
    db_session.add(admin)
    db_session.commit()
    client.cookies.set(
        "rescuesync_session", crear_valor_sesion(admin.id), path="/api/v1"
    )
    assert (
        client.patch(
            ruta, headers=csrf(admin), json={"ong_nacional_id": str(uuid4())}
        ).status_code
        == 200
    )
    assert db_session.get(AccesoNacional, representante.organizacion_id) is None


def test_admin_rechaza_vinculo_duplicado_y_preserva_el_anterior(
    client: TestClient,
    representante: Usuario,
    db_session: Session,
) -> None:
    ruta = f"/api/v1/organizaciones/{representante.organizacion_id}/vinculo-nacional"
    otra_id = uuid4()
    otra = Organizacion(
        tipo=TipoOrganizacion.ONG, nombre="Otra ONG nacional", ong_nacional_id=otra_id
    )
    admin = Usuario(
        email="admin-vinculo-duplicado@rescuesync.org",
        rol=RolUsuario.ADMINISTRADOR,
        password_hash=generar_password_hash("password-seguro123"),
    )
    db_session.add_all([otra, admin])
    db_session.commit()
    client.cookies.set(
        "rescuesync_session", crear_valor_sesion(admin.id), path="/api/v1"
    )
    response = client.patch(
        ruta, headers=csrf(admin), json={"ong_nacional_id": str(otra_id)}
    )
    assert response.status_code == 409
    assert representante.organizacion.ong_nacional_id == ONG_ID


def test_respuesta_nacional_malformada_se_traduce_sin_exponerla(
    client: TestClient,
    representante: Usuario,
) -> None:
    with respx.mock as mock:
        remoto(mock)
        assert conexion(client, representante).status_code == 200
        mock.get(f"{NACIONAL}/ongs/{ONG_ID}/recursos").respond(
            200, text="dato-interno " + TOKEN
        )
        response = client.get("/api/v1/mi-ong/recursos")
        assert response.status_code == 502
        assert TOKEN not in response.text


REGISTRO = {"emailContacto": "contacto@example.org"}


@pytest.fixture
def alta_nacional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        get_settings(), "nacional_aprovisionamiento_login", "emisor-local"
    )
    monkeypatch.setattr(
        get_settings(),
        "nacional_aprovisionamiento_password",
        SecretStr("secreto-emisor"),
    )


def mock_alta(mock: respx.MockRouter) -> respx.Route:
    mock.post(f"{NACIONAL}/login").respond(
        200, json={"access_token": TOKEN, "token_type": "bearer", "expires_in": 1800}
    )
    return mock.put(
        re.compile(re.escape(NACIONAL) + r"/integraciones/ongs/.*")
    ).respond(
        200,
        json={
            "ong": {
                "id": str(ONG_ID),
                "nombre": "Inventario ONG",
                "estado": "PENDIENTE",
            },
            "cuentaId": str(CUENTA_ID),
            "identificadorLogin": "tecnica-ong",
        },
    )


def test_registro_vincula_y_configura_acceso_sin_credenciales_personales(
    client: TestClient,
    representante: Usuario,
    db_session: Session,
    alta_nacional: None,
) -> None:
    representante.organizacion.ong_nacional_id = None
    db_session.commit()
    with respx.mock as mock:
        ruta = mock_alta(mock)
        response = client.post(
            "/api/v1/mi-ong/registro-nacional", headers=csrf(representante), json={}
        )
        assert response.status_code == 201 and response.json()["id"] == str(ONG_ID)
        assert response.headers["cache-control"] == "no-store"
        enviado = json.loads(ruta.calls[0].request.content)
        assert (
            enviado["nombre"] == "Inventario ONG" and enviado["emailContacto"] is None
        )
        assert len(enviado["password"]) >= 32
        assert enviado["password"] not in response.text
        assert representante.organizacion.ong_nacional_id == ONG_ID
        assert db_session.get(AccesoNacional, representante.organizacion_id) is not None


def test_registro_exige_csrf_y_ong_sin_vinculo(
    client: TestClient, representante: Usuario
) -> None:
    with respx.mock:
        assert (
            client.post("/api/v1/mi-ong/registro-nacional", json=REGISTRO).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/mi-ong/registro-nacional",
                headers=csrf(representante),
                json=REGISTRO,
            ).status_code
            == 409
        )


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("nombre", "Otro"),
        ("rol", "ADMIN_NACIONAL"),
        ("identificadorInstitucional", "auto"),
        ("password", "corta"),
        ("emailContacto", "inválido"),
    ],
)
def test_registro_rechaza_datos_invalidos_sin_llamada_remota(
    client: TestClient, representante: Usuario, campo: str, valor: str
) -> None:
    with respx.mock:
        response = client.post(
            "/api/v1/mi-ong/registro-nacional",
            headers=csrf(representante),
            json={**REGISTRO, campo: valor},
        )
        assert response.status_code == 422


@pytest.mark.parametrize("status", [409, 422, 500])
def test_registro_traduce_fallos_sin_vincular_ong(
    client: TestClient,
    representante: Usuario,
    db_session: Session,
    status: int,
    alta_nacional: None,
) -> None:
    representante.organizacion.ong_nacional_id = None
    db_session.commit()
    with respx.mock as mock:
        ruta = mock_alta(mock)
        ruta.respond(status, json={"detail": "sql interno secreto"})
        response = client.post(
            "/api/v1/mi-ong/registro-nacional",
            headers=csrf(representante),
            json=REGISTRO,
        )
        assert response.status_code == (502 if status == 500 else status)
        assert "sql interno" not in response.text
        assert representante.organizacion.ong_nacional_id is None


def test_timeout_registro_no_reintenta_ni_autovincula(
    client: TestClient, representante: Usuario, db_session: Session, alta_nacional: None
) -> None:
    representante.organizacion.ong_nacional_id = None
    db_session.commit()
    with respx.mock as mock:
        ruta = mock_alta(mock)
        ruta.mock(side_effect=httpx.ReadTimeout("secreto"))
        response = client.post(
            "/api/v1/mi-ong/registro-nacional",
            headers=csrf(representante),
            json=REGISTRO,
        )
        assert response.status_code == 504 and ruta.call_count == 1
        assert representante.organizacion.ong_nacional_id is None


@pytest.mark.parametrize("cantidad", ["0", "0.000", "-1", "NaN", "1.0001"])
def test_cantidad_no_positiva_o_invalida_se_rechaza_localmente(
    client: TestClient, representante: Usuario, cantidad: str
) -> None:
    with respx.mock:
        alta = {
            "capacidadId": str(CAPACIDAD_ID),
            "codigoInterno": "INVALIDO",
            "nombre": "Inválido",
            "cantidadTotal": cantidad,
        }
        assert (
            client.post(
                "/api/v1/mi-ong/recursos", headers=csrf(representante), json=alta
            ).status_code
            == 422
        )
        assert (
            client.patch(
                f"/api/v1/mi-ong/recursos/{RECURSO_ID}",
                headers=csrf(representante),
                json={
                    "cantidadTotal": cantidad,
                    "actualizadoEn": RECURSO["actualizadoEn"],
                },
            ).status_code
            == 422
        )
