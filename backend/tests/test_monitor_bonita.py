"""Alertas durables de errores de Bonita, aisladas de casos y usuarios ajenos."""

from collections.abc import Iterator

import pytest
import respx
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Emergencia, Notificacion, RolUsuario, Usuario
from app.integrations.bonita.cliente import (
    ClienteBonita,
    ConfiguracionBonita,
    ErrorBonita,
)
from app.scripts.seed import seed_development_data
from app.services.monitor_bonita import comprobar_tareas_bonita

BASE = "http://bonita:8080/bonita"


@pytest.fixture(autouse=True)
def cifrado_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        get_settings(),
        "nacional_encryption_key",
        SecretStr(Fernet.generate_key().decode()),
    )


@pytest.fixture
def cliente() -> Iterator[ClienteBonita]:
    with ClienteBonita(ConfiguracionBonita.desde_settings(get_settings())) as cliente:
        yield cliente


@pytest.fixture
def escenario(db_session: Session) -> Session:
    seed_development_data(db_session, incluir_dashboard=False)
    emergencia = db_session.scalars(select(Emergencia).order_by(Emergencia.id)).first()
    assert emergencia is not None
    emergencia.bonita_process_instance_id = 4201
    db_session.add(
        Usuario(
            email="auditor-inactivo@prueba.org",
            rol=RolUsuario.AUDITOR_DIRECTIVO,
            activo=False,
            password_hash=db_session.scalars(select(Usuario.password_hash)).first(),
        )
    )
    db_session.flush()
    return db_session


def login(router: respx.MockRouter) -> None:
    router.post(f"{BASE}/loginservice").respond(
        204, headers={"set-cookie": "X-Bonita-API-Token=prueba; Path=/bonita"}
    )


def test_fallo_notifica_solo_auditores_activos_sin_duplicar_sondeos(
    escenario: Session, cliente: ClienteBonita
) -> None:
    with respx.mock(assert_all_called=True) as router:
        login(router)
        ruta = router.get(f"{BASE}/API/bpm/flowNode").respond(
            200,
            json=[
                {
                    "id": "31",
                    "rootCaseId": "4201",
                    "name": "Validar ofertas",
                    "state": "failed",
                },
                {
                    "id": "32",
                    "rootCaseId": "9999",
                    "name": "Caso ajeno",
                    "state": "failed",
                },
            ],
        )
        notificaciones = comprobar_tareas_bonita(escenario, cliente)
        repetidas = comprobar_tareas_bonita(escenario, cliente)
    assert ruta.calls[0].request.url.params["f"] == "state=failed"
    assert len(notificaciones) == 1
    assert repetidas == []
    assert notificaciones[0].tipo.value == "TAREA_BONITA_FALLIDA"
    assert "Validar ofertas" in notificaciones[0].mensaje
    usuario = escenario.get(Usuario, notificaciones[0].usuario_id)
    assert (
        usuario is not None
        and usuario.rol == RolUsuario.AUDITOR_DIRECTIVO
        and usuario.activo
    )


def test_motor_no_disponible_no_inventa_una_tarea_fallida(
    escenario: Session, cliente: ClienteBonita
) -> None:
    with respx.mock(assert_all_called=True) as router:
        login(router)
        router.get(f"{BASE}/API/bpm/flowNode").respond(503)
        with pytest.raises(ErrorBonita):
            comprobar_tareas_bonita(escenario, cliente)
    assert escenario.scalar(select(func.count()).select_from(Notificacion)) == 0
