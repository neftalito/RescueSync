import pytest
from pydantic import ValidationError

from app.core.config import BONITA_CALLBACK_TOKEN_DESARROLLO, Settings


def test_produccion_exige_secret_estable() -> None:
    with pytest.raises(ValidationError, match="SESSION_SECRET es obligatorio"):
        Settings(_env_file=None, app_env="production", SESSION_SECRET="")


def test_produccion_activa_cookie_secure_por_defecto() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        SESSION_SECRET="s" * 32,
        bonita_callback_token="p" * 64,
    )

    assert settings.cookies_seguras is True


def test_samesite_none_requiere_cookie_secure() -> None:
    with pytest.raises(ValidationError, match="SameSite=None requiere cookies Secure"):
        Settings(
            _env_file=None,
            app_env="development",
            SESSION_SECRET="s" * 32,
            session_cookie_samesite="none",
            session_cookie_secure=False,
        )


def test_callback_token_de_bonita_debe_ser_robusto() -> None:
    with pytest.raises(ValidationError, match="al menos 32 caracteres"):
        Settings(_env_file=None, bonita_callback_token="corto")


def test_callback_token_vacio_equivale_a_no_configurado() -> None:
    assert (
        Settings(_env_file=None, bonita_callback_token="").bonita_callback_token is None
    )


@pytest.mark.parametrize("token", [None, BONITA_CALLBACK_TOKEN_DESARROLLO])
def test_produccion_exige_un_callback_token_propio(token: str | None) -> None:
    with pytest.raises(ValidationError, match="BONITA_CALLBACK_TOKEN propio"):
        Settings(
            _env_file=None,
            app_env="production",
            SESSION_SECRET="s" * 32,
            bonita_callback_token=token,
        )


def test_produccion_acepta_un_callback_token_propio() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        SESSION_SECRET="s" * 32,
        bonita_callback_token="p" * 64,
    )

    assert settings.bonita_callback_token is not None
