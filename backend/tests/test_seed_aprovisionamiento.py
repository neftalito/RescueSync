import json
import re
from collections.abc import Iterator
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import AccesoNacional, Organizacion
from app.db.models.aprovisionamiento import AprovisionamientoNacional
from app.integrations.nacional.cliente import ClienteNacional, ErrorNacional
from app.scripts import seed
from app.scripts.seed import aprovisionar_ongs_demo, seed_development_data
from app.services.acceso_nacional import cifrador

NOMBRE = "Ayuda Sin Fronteras"
REFERENCIA = "ayuda-sin-fronteras"


@pytest.fixture(autouse=True)
def configuracion(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(
        settings, "nacional_encryption_key", SecretStr(Fernet.generate_key().decode())
    )
    monkeypatch.setattr(settings, "nacional_aprovisionamiento_login", "emisor-seed")
    monkeypatch.setattr(
        settings, "nacional_aprovisionamiento_password", SecretStr("secreto-emisor")
    )


def _ong(session: Session) -> Organizacion:
    ong = session.scalar(select(Organizacion).where(Organizacion.nombre == NOMBRE))
    assert ong is not None
    return ong


def _legacy(session: Session) -> AccesoNacional:
    ong = _ong(session)
    pendiente = session.get(AprovisionamientoNacional, ong.id)
    if pendiente is not None:
        session.delete(pendiente)
    ong.ong_nacional_id = uuid5(NAMESPACE_URL, f"rescuesync-demo:ong:{REFERENCIA}")
    acceso = AccesoNacional(
        organizacion_id=ong.id,
        ong_id=ong.ong_nacional_id,
        cuenta_id=uuid5(NAMESPACE_URL, f"rescuesync-demo:cuenta-tecnica:{REFERENCIA}"),
        configuracion_id=uuid4(),
        identificador_login=f"demo-tecnica-{REFERENCIA}",
        secreto_cifrado=cifrador()
        .encrypt(f"demo-only-rescuesync-tecnica:{REFERENCIA}:2026".encode())
        .decode(),
        requiere_revision=True,
    )
    session.add(acceso)
    session.commit()
    return acceso


def _alta(request: httpx.Request) -> httpx.Response:
    nombre = json.loads(request.content)["nombre"]
    return httpx.Response(
        200,
        json={
            "ong": {"id": str(uuid4()), "nombre": nombre, "estado": "PENDIENTE"},
            "cuentaId": str(uuid4()),
            "identificadorLogin": f"tecnica-{nombre}",
        },
    )


@pytest.fixture
def nacional() -> Iterator[ClienteNacional]:
    cliente = ClienteNacional(str(get_settings().nacional_base_url), 1)
    try:
        yield cliente
    finally:
        cliente.close()


def test_seed_aprovisiona_cuentas_sin_crear_inventario_y_no_duplica(
    db_session: Session,
    nacional: ClienteNacional,
) -> None:
    seed_development_data(db_session, incluir_dashboard=False)
    db_session.commit()
    base = str(get_settings().nacional_base_url).rstrip("/")
    with respx.mock as mock:
        mock.post(f"{base}/login").respond(
            200,
            json={
                "access_token": "jwt-emisor",
                "token_type": "bearer",
                "expires_in": 1800,
            },
        )
        altas = mock.put(re.compile(re.escape(base) + r"/integraciones/ongs/.*")).mock(
            side_effect=_alta
        )
        aprovisionar_ongs_demo(db_session, nacional)
        assert altas.call_count == 2
        for llamada in altas.calls:
            datos = json.loads(llamada.request.content)
            ong = db_session.scalar(
                select(Organizacion).where(Organizacion.nombre == datos["nombre"])
            )
            assert ong is not None
            acceso = db_session.get(AccesoNacional, ong.id)
            pendiente = db_session.get(AprovisionamientoNacional, ong.id)
            assert acceso is not None and pendiente is not None
            assert ong.ong_nacional_id == UUID(llamada.response.json()["ong"]["id"])
            assert acceso.cuenta_id == UUID(llamada.response.json()["cuentaId"])
            assert (
                acceso.identificador_login
                == llamada.response.json()["identificadorLogin"]
            )
            assert acceso.ong_id == ong.ong_nacional_id
            assert not acceso.requiere_revision
            assert len(datos["password"]) >= 32
            assert datos["password"] not in acceso.secreto_cifrado
            assert (
                cifrador().decrypt(acceso.secreto_cifrado.encode()).decode()
                == datos["password"]
            )
            assert pendiente.secreto_cifrado == acceso.secreto_cifrado
        seed_development_data(db_session, incluir_dashboard=False)
        db_session.commit()
        aprovisionar_ongs_demo(db_session, nacional)
        assert altas.call_count == 2
        assert all(
            call.request.method == "PUT" or call.request.url.path.endswith("/login")
            for call in mock.calls
        )


def test_timeout_reutiliza_referencia_y_secreto_sin_fingir_vinculo(
    db_session: Session,
    nacional: ClienteNacional,
) -> None:
    seed_development_data(db_session, incluir_dashboard=False)
    db_session.commit()
    ong = _ong(db_session)
    ong_id = ong.id
    base = str(get_settings().nacional_base_url).rstrip("/")
    with respx.mock as mock:
        mock.post(f"{base}/login").respond(
            200,
            json={
                "access_token": "jwt-emisor",
                "token_type": "bearer",
                "expires_in": 1800,
            },
        )
        altas = mock.put(re.compile(re.escape(base) + r"/integraciones/ongs/.*")).mock(
            side_effect=httpx.ReadTimeout("timeout")
        )
        with pytest.raises(ErrorNacional, match="demoró"):
            aprovisionar_ongs_demo(db_session, nacional)
        primera = altas.calls[0].request
        db_session.expire_all()
        assert db_session.get(Organizacion, ong_id).ong_nacional_id is None
        assert db_session.get(AccesoNacional, ong_id) is None
        assert db_session.get(AprovisionamientoNacional, ong_id) is not None
        seed_development_data(db_session, incluir_dashboard=False)
        db_session.commit()
        altas.mock(side_effect=_alta)
        aprovisionar_ongs_demo(db_session, nacional)
        assert altas.calls[1].request.url == primera.url
        assert altas.calls[1].request.content == primera.content


@pytest.mark.parametrize("existe", [False, True])
def test_solo_migra_vinculo_demo_heredado_si_la_ong_nacional_no_existe(
    db_session: Session,
    nacional: ClienteNacional,
    existe: bool,
) -> None:
    seed_development_data(db_session, incluir_dashboard=False)
    db_session.commit()
    previo = _legacy(db_session)
    anterior_id = previo.ong_id
    configuracion_id = previo.configuracion_id
    organizacion_id = previo.organizacion_id
    base = str(get_settings().nacional_base_url).rstrip("/")
    with respx.mock as mock:
        mock.post(f"{base}/login").respond(
            200,
            json={
                "access_token": "jwt-emisor",
                "token_type": "bearer",
                "expires_in": 1800,
            },
        )
        mock.get(f"{base}/ongs/{anterior_id}/perfil-competencia").respond(
            200 if existe else 404,
            json={
                "ongId": str(anterior_id),
                "estadoOng": "HABILITADA",
                "nombre": "ONG de prueba",
                "evaluadoEn": "2026-10-19T00:00:00Z",
                "capacidadesDeclaradas": [],
            }
            if existe
            else {"detail": "No existe"},
        )
        altas = mock.put(re.compile(re.escape(base) + r"/integraciones/ongs/.*")).mock(
            side_effect=_alta
        )
        aprovisionar_ongs_demo(db_session, nacional)
        db_session.expire_all()
        acceso = db_session.get(AccesoNacional, organizacion_id)
        assert acceso is not None
        if existe:
            assert acceso.ong_id == anterior_id
            assert acceso.configuracion_id == configuracion_id
            assert acceso.requiere_revision
            assert altas.call_count == 1
        else:
            assert acceso.ong_id != anterior_id
            assert acceso.configuracion_id != configuracion_id
            assert not acceso.requiere_revision
            assert altas.call_count == 2


def test_no_reemplaza_credenciales_importadas_de_una_ong_demo(
    db_session: Session,
    nacional: ClienteNacional,
) -> None:
    seed_development_data(db_session, incluir_dashboard=False)
    db_session.commit()
    acceso = _legacy(db_session)
    acceso.secreto_cifrado = (
        cifrador().encrypt(b"secreto-institucional-importado").decode()
    )
    db_session.commit()
    original = acceso.secreto_cifrado
    base = str(get_settings().nacional_base_url).rstrip("/")
    with respx.mock as mock:
        mock.post(f"{base}/login").respond(
            200,
            json={
                "access_token": "jwt-emisor",
                "token_type": "bearer",
                "expires_in": 1800,
            },
        )
        altas = mock.put(re.compile(re.escape(base) + r"/integraciones/ongs/.*")).mock(
            side_effect=_alta
        )
        aprovisionar_ongs_demo(db_session, nacional)
        db_session.refresh(acceso)
        assert acceso.secreto_cifrado == original
        assert acceso.requiere_revision
        assert altas.call_count == 1


@pytest.mark.parametrize("status", [401, 403, 503])
def test_un_fallo_al_comprobar_una_ong_demo_no_borra_su_acceso(
    db_session: Session,
    nacional: ClienteNacional,
    status: int,
) -> None:
    seed_development_data(db_session, incluir_dashboard=False)
    db_session.commit()
    acceso = _legacy(db_session)
    original = (acceso.ong_id, acceso.configuracion_id, acceso.secreto_cifrado)
    base = str(get_settings().nacional_base_url).rstrip("/")
    with respx.mock as mock:
        mock.post(f"{base}/login").respond(
            200,
            json={
                "access_token": "jwt-emisor",
                "token_type": "bearer",
                "expires_in": 1800,
            },
        )
        mock.get(f"{base}/ongs/{acceso.ong_id}/perfil-competencia").respond(status)
        with pytest.raises(ErrorNacional):
            aprovisionar_ongs_demo(db_session, nacional)
        db_session.refresh(acceso)
        assert (
            acceso.ong_id,
            acceso.configuracion_id,
            acceso.secreto_cifrado,
        ) == original
        assert acceso.requiere_revision
        assert db_session.get(AprovisionamientoNacional, acceso.organizacion_id) is None


@pytest.mark.parametrize("fallo", [False, True])
def test_comando_aprovisiona_o_informa_fallo_con_solicitud_reintentable(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fallo: bool,
) -> None:
    monkeypatch.setattr(
        seed,
        "SessionLocal",
        sessionmaker(
            bind=db_session.connection(), join_transaction_mode="create_savepoint"
        ),
    )
    base = str(get_settings().nacional_base_url).rstrip("/")
    with respx.mock as mock:
        mock.post(f"{base}/login").respond(
            200,
            json={
                "access_token": "jwt-emisor",
                "token_type": "bearer",
                "expires_in": 1800,
            },
        )
        altas = mock.put(re.compile(re.escape(base) + r"/integraciones/ongs/.*"))
        if fallo:
            altas.mock(side_effect=httpx.ReadTimeout("timeout"))
        else:
            altas.mock(side_effect=_alta)
        assert seed.main() == (1 if fallo else 0)
        db_session.expire_all()
        ong = _ong(db_session)
        pendiente = db_session.get(AprovisionamientoNacional, ong.id)
        assert pendiente is not None
        salida = capsys.readouterr()
        secreto = cifrador().decrypt(pendiente.secreto_cifrado.encode()).decode()
        assert secreto not in salida.out + salida.err
        assert "jwt-emisor" not in salida.out + salida.err
        if fallo:
            assert ong.ong_nacional_id is None
            assert "Datos locales conservados" in salida.err
        else:
            assert ong.ong_nacional_id is not None
            assert db_session.get(AccesoNacional, ong.id) is not None
            assert altas.call_count == 2
