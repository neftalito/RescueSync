"""Mantiene alineados el `.bar` de `docs/` y el contrato escrito en el backend."""

from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest

from app.integrations.bonita.deploy import Config, ensure_bar_matches_contract

DOCS = Path(__file__).resolve().parents[4] / "docs"

pytestmark = pytest.mark.skipif(
    not DOCS.is_dir(),
    reason="docs/ no está montado (contenedor de desarrollo); se verifica en CI.",
)


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch) -> Config:
    for nombre, valor in {
        "BONITA_BASE_URL": "http://bonita:8080/bonita",
        "BONITA_USERNAME": "install",
        "BONITA_PASSWORD": "install",
        "ADMIN_EMAIL": "admin@rescuesync.org",
        "ADMIN_INITIAL_PASSWORD": "administrador123",
        "BONITA_BAR_PATH": str(DOCS),
        "BONITA_NATIONAL_API_LOGIN": "integracion-prueba",
        "BONITA_NATIONAL_API_PASSWORD": "secreto-solo-pruebas",
        "BONITA_CALLBACK_TOKEN": "t" * 40,
        "BONITA_PROCESS_NAME": "RescueSync",
        "BONITA_PROCESS_VERSION": "1.5",
    }.items():
        monkeypatch.setenv(nombre, valor)
    return Config.from_environment()


def _bar_versionado() -> Path:
    bars = sorted(DOCS.glob("*.bar"))
    assert len(bars) == 1, f"docs/ debe contener un único .bar: {bars}"
    return bars[0]


def test_el_bar_versionado_coincide_con_contratos(config: Config) -> None:
    ensure_bar_matches_contract(_bar_versionado(), config)


def test_el_bar_define_todos_los_parametros_que_inyecta_el_deploy(
    config: Config,
) -> None:
    with ZipFile(_bar_versionado()) as archive:
        root = ElementTree.fromstring(archive.read("process-design.xml"))

    definidos = {
        elemento.get("name")
        for elemento in root.iter()
        if elemento.tag.rsplit("}", 1)[-1] == "parameter"
    }
    inyectados = {nombre for nombre, _ in config.process_parameters}
    assert definidos == inyectados
