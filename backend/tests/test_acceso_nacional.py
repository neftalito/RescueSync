"""Renovación institucional y protección de credenciales y transacciones."""

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session
from test_inventario import CUENTA_ID, NACIONAL, ONG_ID, TOKEN, csrf, remoto
from test_inventario import representante as fixture_representante

from app.db.models import (
    AccesoNacional,
    Organizacion,
    RolUsuario,
    TipoOrganizacion,
    Usuario,
)
from app.db.session import engine, get_db
from app.integrations.nacional.cliente import ClienteNacional, ErrorNacional
from app.main import app
from app.schemas.inventario import CredencialTecnica
from app.scripts import acceso_nacional as cli
from app.services.acceso_nacional import (
    cifrador,
    credencial,
    ejecutar_nacional,
    importar_credencial,
)
from app.services.inventario import estado_conexion, vincular_ong

representante = fixture_representante


@pytest.fixture
def cliente() -> Iterator[ClienteNacional]:
    remoto_cliente = ClienteNacional(NACIONAL, 10)
    yield remoto_cliente
    remoto_cliente.close()


def configurar(db: Session, usuario: Usuario) -> AccesoNacional:
    assert usuario.organizacion_id is not None and usuario.organizacion is not None
    assert usuario.organizacion.ong_nacional_id is not None
    acceso = AccesoNacional(
        organizacion_id=usuario.organizacion_id,
        ong_id=usuario.organizacion.ong_nacional_id,
        cuenta_id=CUENTA_ID,
        configuracion_id=uuid4(),
        identificador_login="tecnica-ong",
        secreto_cifrado=cifrador().encrypt(b"secreto-institucional").decode(),
    )
    db.add(acceso)
    db.commit()
    return acceso


def test_renueva_y_comparte_token_entre_representantes(
    db_session: Session, representante: Usuario, cliente: ClienteNacional
) -> None:
    configurar(db_session, representante)
    otro = Usuario(
        email="otro-representante@example.org",
        password_hash=representante.password_hash,
        organizacion_id=representante.organizacion_id,
        rol=RolUsuario.REPRESENTANTE_ONG,
    )
    db_session.add(otro)
    db_session.commit()
    assert estado_conexion(db_session, representante).estado == "LISTA"
    with respx.mock as mock:
        remoto(mock)
        assert credencial(db_session, representante, cliente) == (ONG_ID, TOKEN)
        assert credencial(db_session, otro, cliente) == (ONG_ID, TOKEN)
        assert mock.routes[0].call_count == 1
        acceso = db_session.get(
            AccesoNacional, representante.organizacion_id, populate_existing=True
        )
        assert acceso is not None and TOKEN not in acceso.token_cifrado
        acceso.expira_en = datetime.now(UTC) + timedelta(seconds=15)
        db_session.commit()
        credencial(db_session, otro, cliente)
        assert mock.routes[0].call_count == 2


def test_credencial_rechazada_detiene_nuevos_logins(
    db_session: Session, representante: Usuario, cliente: ClienteNacional
) -> None:
    configurar(db_session, representante)
    with respx.mock as mock:
        login = mock.post(f"{NACIONAL}/login").respond(401)
        for _ in range(2):
            with pytest.raises(ErrorNacional, match="revisión"):
                credencial(db_session, representante, cliente)
        assert login.call_count == 1
    assert estado_conexion(db_session, representante).estado == "REQUIERE_REVISION"


def test_renueva_401_pero_no_repite_escritura(
    db_session: Session, representante: Usuario, cliente: ClienteNacional
) -> None:
    configurar(db_session, representante)
    with respx.mock as mock:
        remoto(mock)
        llamadas = 0

        def escribir(ong: UUID, token: str) -> None:
            nonlocal llamadas
            llamadas += 1
            raise ErrorNacional(401, "Token rechazado")

        with pytest.raises(ErrorNacional, match="renovó"):
            ejecutar_nacional(
                db_session, representante, cliente, escribir, escritura=True
            )
        assert llamadas == 1


def test_otra_ong_no_reutiliza_acceso(
    db_session: Session, representante: Usuario, cliente: ClienteNacional
) -> None:
    configurar(db_session, representante)
    ong = Organizacion(
        nombre="Segunda ONG", tipo=TipoOrganizacion.ONG, ong_nacional_id=uuid4()
    )
    db_session.add(ong)
    db_session.flush()
    otro = Usuario(
        email="otra-ong@example.org",
        password_hash=representante.password_hash,
        rol=RolUsuario.REPRESENTANTE_ONG,
        organizacion_id=ong.id,
    )
    db_session.add(otro)
    db_session.commit()
    with respx.mock as mock:
        with pytest.raises(ErrorNacional, match="configurar"):
            credencial(db_session, otro, cliente)
        assert not mock.calls


def test_configuracion_cambiada_durante_login_no_guarda_token(
    db_session: Session, representante: Usuario, cliente: ClienteNacional
) -> None:
    acceso = configurar(db_session, representante)
    with respx.mock as mock:
        remoto(mock)

        def cambiar(_: httpx.Request) -> httpx.Response:
            acceso.configuracion_id = uuid4()
            db_session.commit()
            return httpx.Response(
                200,
                json={
                    "id": str(CUENTA_ID),
                    "ongId": str(ONG_ID),
                    "rol": "ONG",
                    "proposito": "TECNICA_ONG",
                },
            )

        mock.get(f"{NACIONAL}/me").mock(side_effect=cambiar)
        with pytest.raises(ErrorNacional, match="cambió"):
            credencial(db_session, representante, cliente)
    assert (
        db_session.get(
            AccesoNacional, representante.organizacion_id, populate_existing=True
        ).token_cifrado
        is None
    )


def test_logout_no_desconecta_a_la_ong(
    db_session: Session, representante: Usuario
) -> None:
    from app.core.security import crear_valor_sesion

    configurar(db_session, representante)

    def database() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = database
    try:
        with TestClient(app) as client:
            client.cookies.set(
                "rescuesync_session",
                crear_valor_sesion(representante.id),
                path="/api/v1",
            )
            assert (
                client.post(
                    "/api/v1/auth/logout", headers=csrf(representante)
                ).status_code
                == 204
            )
            assert estado_conexion(db_session, representante).estado == "LISTA"
    finally:
        app.dependency_overrides.clear()


def test_cambiar_vinculo_elimina_credencial(
    db_session: Session, representante: Usuario
) -> None:
    configurar(db_session, representante)
    vincular_ong(db_session, representante.organizacion_id, uuid4())
    assert (
        db_session.get(
            AccesoNacional, representante.organizacion_id, populate_existing=True
        )
        is None
    )


def test_importar_rechaza_cuenta_personal(
    db_session: Session, representante: Usuario, cliente: ClienteNacional
) -> None:
    with respx.mock as mock:
        remoto(mock)
        mock.get(f"{NACIONAL}/me").respond(
            200,
            json={
                "id": str(CUENTA_ID),
                "rol": "ONG",
                "ongId": str(ONG_ID),
                "proposito": "PERSONAL",
            },
        )
        with pytest.raises(ErrorNacional, match="técnica"):
            importar_credencial(
                db_session,
                representante.organizacion_id,
                CredencialTecnica(
                    cuenta_id=CUENTA_ID,
                    ong_id=ONG_ID,
                    identificador_login="personal",
                    password="clave-personal",
                ),
                cliente,
            )
    assert db_session.get(AccesoNacional, representante.organizacion_id) is None


def test_cache_no_confirma_cambios_del_llamador(
    representante: Usuario, cliente: ClienteNacional
) -> None:
    """Usa conexiones reales independientes: renovar no confirma cambios de usuario."""
    with Session(engine, expire_on_commit=False) as setup:
        ong = Organizacion(
            nombre=f"ONG transacción {uuid4()}",
            tipo=TipoOrganizacion.ONG,
            ong_nacional_id=uuid4(),
        )
        setup.add(ong)
        setup.flush()
        usuario = Usuario(
            email=f"{uuid4()}@example.org",
            password_hash=representante.password_hash,
            rol=RolUsuario.REPRESENTANTE_ONG,
            organizacion_id=ong.id,
        )
        setup.add(usuario)
        setup.commit()
        configurar(setup, usuario)
        usuario_id, ong_local_id, ong_id, email = (
            usuario.id,
            ong.id,
            ong.ong_nacional_id,
            usuario.email,
        )
    try:
        barrera = Barrier(2)

        def autenticar(_: httpx.Request) -> httpx.Response:
            barrera.wait(timeout=5)
            return httpx.Response(
                200,
                json={"access_token": TOKEN, "token_type": "bearer", "expires_in": 300},
            )

        def worker() -> tuple[UUID, str]:
            with Session(engine) as db:
                return credencial(db, db.get(Usuario, usuario_id), cliente)

        with respx.mock as mock, ThreadPoolExecutor(max_workers=2) as executor:
            remoto(mock, str(ong_id))
            mock.post(f"{NACIONAL}/login").mock(side_effect=autenticar)
            futuros = [executor.submit(worker) for _ in range(2)]
            assert all(f.result(timeout=10) == (ong_id, TOKEN) for f in futuros)
        with Session(engine) as caller, respx.mock as mock:
            remoto(mock, str(ong_id))
            actual = caller.get(Usuario, usuario_id)
            actual.email = "cambio-no-confirmado@example.org"
            caller.flush()
            credencial(caller, actual, cliente, renovar=True)
            caller.rollback()
        with Session(engine) as check:
            assert check.get(Usuario, usuario_id).email == email
            assert check.get(AccesoNacional, ong_local_id).token_cifrado is not None
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(
                delete(AccesoNacional).where(
                    AccesoNacional.organizacion_id == ong_local_id
                )
            )
            cleanup.execute(delete(Usuario).where(Usuario.id == usuario_id))
            cleanup.execute(delete(Organizacion).where(Organizacion.id == ong_local_id))
            cleanup.commit()


def test_401_renueva_y_repite_consulta_una_vez(
    db_session: Session, representante: Usuario, cliente: ClienteNacional
) -> None:
    configurar(db_session, representante)
    with respx.mock as mock:
        remoto(mock)
        consulta = mock.get(f"{NACIONAL}/ongs/{ONG_ID}/recursos")
        consulta.side_effect = [httpx.Response(401), httpx.Response(200, json=[])]
        resultado = ejecutar_nacional(
            db_session,
            representante,
            cliente,
            lambda ong, token: cliente.recursos(token, ong),
        )
        assert resultado == [] and consulta.call_count == 2
        assert mock.routes[0].call_count == 2
    assert estado_conexion(db_session, representante).estado == "LISTA"


def test_importacion_administrativa_exige_archivo_privado_y_no_imprime_secretos(
    db_session: Session,
    representante: Usuario,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    admin = Usuario(
        email="admin-importacion@example.org",
        password_hash=representante.password_hash,
        rol=RolUsuario.ADMINISTRADOR,
    )
    db_session.add(admin)
    db_session.commit()
    organizacion_id = representante.organizacion_id
    archivo = tmp_path / "credencial.json"
    archivo.write_text(
        json.dumps(
            {
                "cuentaId": str(CUENTA_ID),
                "ongId": str(ONG_ID),
                "identificadorLogin": "tecnica-ong",
                "password": "secreto-importado",
            }
        )
    )
    args = [
        "--login",
        admin.email,
        "--organizacion",
        str(organizacion_id),
        "--archivo",
        str(archivo),
    ]
    monkeypatch.setattr(cli, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(cli, "getpass", lambda _: "password-seguro123")
    with respx.mock as mock:
        assert cli.main(args) == 1
        assert not mock.calls
    archivo.chmod(0o600)
    with respx.mock as mock:
        remoto(mock)
        assert cli.main(args) == 0
    assert "secreto-importado" not in capsys.readouterr().out
    acceso = db_session.get(AccesoNacional, organizacion_id)
    assert acceso is not None and "secreto-importado" not in acceso.secreto_cifrado
