"""Catálogo técnico y validación de las referencias que captura coordinación."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
import respx
from pydantic import SecretStr

from app.core.config import get_settings
from app.integrations.nacional.cliente import ClienteNacional, ErrorNacional
from app.schemas.lote import LoteItem
from app.services.referencias_nacionales import capacidades_para_lotes, catalogo_tecnico


@pytest.fixture
def cliente() -> Iterator[ClienteNacional]:
    remoto = ClienteNacional("https://nacional.example.test/api/v1", 2)
    try:
        yield remoto
    finally:
        remoto.close()


@pytest.mark.parametrize("rol", ["INTEGRACION", "ADMIN_NACIONAL", "ONG"])
def test_catalogo_verifica_cuenta_tecnica_y_no_devuelve_credenciales(
    cliente: ClienteNacional, monkeypatch: pytest.MonkeyPatch, rol: str
) -> None:
    monkeypatch.setattr(get_settings(), "nacional_catalogo_login", "cuenta-tecnica")
    monkeypatch.setattr(
        get_settings(),
        "nacional_catalogo_password",
        SecretStr("secreto-solo-de-prueba"),
    )
    with respx.mock(assert_all_called=False) as mock:
        mock.post("https://nacional.example.test/api/v1/login").respond(
            200,
            json={
                "access_token": "jwt-de-prueba",
                "token_type": "bearer",
                "expires_in": 1800,
            },
        )
        mock.get("https://nacional.example.test/api/v1/me").respond(
            200, json={"id": str(uuid4()), "rol": rol, "ongId": None}
        )
        consulta = mock.get("https://nacional.example.test/api/v1/capacidades").respond(
            200, json=[]
        )
        if rol == "ONG":
            with pytest.raises(ErrorNacional) as error:
                catalogo_tecnico(cliente)
            assert error.value.status == 403 and not consulta.called
        else:
            assert catalogo_tecnico(cliente) == [] and consulta.called
            assert (
                consulta.calls[0].request.headers["Authorization"]
                == "Bearer jwt-de-prueba"
            )


def test_catalogo_sin_configuracion_falla_sin_http(
    cliente: ClienteNacional, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "nacional_catalogo_login", None)
    with respx.mock() as mock, pytest.raises(ErrorNacional) as error:
        catalogo_tecnico(cliente)
    assert error.value.status == 503 and not mock.calls


@pytest.mark.parametrize(
    "unidad,cantidad", [("unidades", "1"), ("personas", "1.5"), ("personas", "2")]
)
def test_lote_valida_unidad_y_fracciones_del_catalogo(
    cliente: ClienteNacional,
    monkeypatch: pytest.MonkeyPatch,
    unidad: str,
    cantidad: str,
) -> None:
    capacidad_id = uuid4()
    monkeypatch.setattr(get_settings(), "nacional_catalogo_login", "tecnico")
    monkeypatch.setattr(
        get_settings(), "nacional_catalogo_password", SecretStr("secreto-prueba")
    )
    item = LoteItem(
        tipo_necesidad="Personal",
        unidad=unidad,
        cantidad_requerida=cantidad,
        capacidad_nacional_id=capacidad_id,
    )
    with respx.mock() as mock:
        mock.post("https://nacional.example.test/api/v1/login").respond(
            200,
            json={"access_token": "jwt", "token_type": "bearer", "expires_in": 1800},
        )
        mock.get("https://nacional.example.test/api/v1/me").respond(
            200, json={"id": str(uuid4()), "rol": "INTEGRACION", "ongId": None}
        )
        mock.get("https://nacional.example.test/api/v1/capacidades").respond(
            200,
            json=[
                {
                    "id": str(capacidad_id),
                    "codigo": "PERSONAL",
                    "nombre": "Personal",
                    "tipo": "PERSONAL",
                    "unidad": "personas",
                    "admiteFracciones": False,
                }
            ],
        )
        if unidad == "personas" and cantidad == "2":
            assert (
                capacidades_para_lotes(cliente, [item])[capacidad_id].unidad
                == "personas"
            )
        else:
            with pytest.raises(ErrorNacional) as error:
                capacidades_para_lotes(cliente, [item])
            assert error.value.status == 422
