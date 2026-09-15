import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_produccion_exige_secret_estable() -> None:
    with pytest.raises(ValidationError, match="SESSION_SECRET es obligatorio"):
        Settings(_env_file=None, app_env="production", SESSION_SECRET="")


def test_produccion_activa_cookie_secure_por_defecto() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        SESSION_SECRET="s" * 32,
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
