import pytest
from pydantic import ValidationError

from app.core.config import (
    ADMIN_INITIAL_PASSWORD_DESARROLLO,
    BONITA_CALLBACK_TOKEN_DESARROLLO,
    Settings,
)


def test_produccion_exige_secret_estable() -> None:
    with pytest.raises(ValidationError, match="SESSION_SECRET es obligatorio"):
        Settings(_env_file=None, app_env="production", SESSION_SECRET="")


def test_produccion_activa_cookie_secure_por_defecto() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        SESSION_SECRET="s" * 32,
        bonita_callback_token="p" * 64,
        admin_initial_password="Clave-productiva-2026",
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
            admin_initial_password="Clave-productiva-2026",
        )


def test_produccion_acepta_un_callback_token_propio() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        SESSION_SECRET="s" * 32,
        bonita_callback_token="p" * 64,
        admin_initial_password="Clave-productiva-2026",
    )

    assert settings.bonita_callback_token is not None


def test_produccion_rechaza_password_publica_del_administrador() -> None:
    with pytest.raises(
        ValidationError,
        match="ADMIN_INITIAL_PASSWORD propio es obligatorio en producción",
    ):
        Settings(
            _env_file=None,
            app_env="production",
            SESSION_SECRET="s" * 32,
            bonita_callback_token="p" * 64,
            admin_initial_password=ADMIN_INITIAL_PASSWORD_DESARROLLO,
        )


def test_administrador_inicial_tiene_defaults_documentados() -> None:
    settings = Settings(_env_file=None)

    assert str(settings.admin_email) == "admin@rescuesync.org"
    assert settings.admin_initial_password.get_secret_value() == "administrador123"


def test_password_inicial_del_administrador_respeta_la_politica() -> None:
    with pytest.raises(
        ValidationError,
        match="ADMIN_INITIAL_PASSWORD debe tener entre 8 y 128 caracteres",
    ):
        Settings(_env_file=None, admin_initial_password="corta")
