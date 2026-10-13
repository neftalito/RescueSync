from functools import lru_cache
from secrets import token_urlsafe
from typing import Literal, Self

from pydantic import (
    AnyHttpUrl,
    EmailStr,
    Field,
    PrivateAttr,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

BONITA_CALLBACK_TOKEN_DESARROLLO = "dev-only-rescuesync-bonita-callback-token"
"""Token compartido por Compose en desarrollo; nunca es válido en producción."""

ADMIN_INITIAL_PASSWORD_DESARROLLO = "administrador123"
"""Clave pública del entorno local; nunca es válida en producción."""


class Settings(BaseSettings):
    _session_secret_desarrollo: str = PrivateAttr(
        default_factory=lambda: token_urlsafe(48)
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "RescueSync API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173"]

    database_url_override: str | None = Field(
        default=None,
        validation_alias="DATABASE_URL",
    )
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "rescuesync"
    postgres_user: str = "rescuesync"
    postgres_password: str = "rescuesync_dev"

    bonita_base_url: str = "http://bonita:8080/bonita"
    bonita_username: str = "install"
    bonita_password: SecretStr = SecretStr("install")
    bonita_process_name: str = "RescueSync"
    bonita_process_version: str = "1.2"
    bonita_callback_token: SecretStr | None = None
    bonita_client_connect_timeout_seconds: float = Field(default=3.0, gt=0, le=60)
    bonita_client_read_timeout_seconds: float = Field(default=10.0, gt=0, le=120)

    session_secret: SecretStr | None = Field(
        default=None,
        validation_alias="SESSION_SECRET",
    )
    session_cookie_name: str = "rescuesync_session"
    session_max_age_seconds: int = Field(default=28_800, ge=300, le=604_800)
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_cookie_secure: bool | None = None

    admin_email: EmailStr = "admin@rescuesync.org"
    admin_initial_password: SecretStr = SecretStr(ADMIN_INITIAL_PASSWORD_DESARROLLO)

    smtp_host: str = "mailpit"
    smtp_port: int = Field(default=1025, ge=1, le=65_535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False
    smtp_sender_email: EmailStr = "no-reply@rescuesync.org"
    smtp_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    frontend_public_url: AnyHttpUrl = "http://localhost:5173"
    nacional_base_url: AnyHttpUrl = "http://host.docker.internal:8001/api/v1"
    nacional_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    @field_validator(
        "session_secret",
        "bonita_callback_token",
        "smtp_username",
        "smtp_password",
        mode="before",
    )
    @classmethod
    def normalizar_secreto_vacio(cls, valor: object) -> object:
        """Interpreta una variable vacía como configuración no provista."""

        return None if valor == "" else valor

    @field_validator("bonita_callback_token")
    @classmethod
    def validar_bonita_callback_token(cls, valor: SecretStr | None) -> SecretStr | None:
        """Exige que el token de los callbacks de Bonita sea difícil de adivinar."""

        if valor is not None and len(valor.get_secret_value()) < 32:
            raise ValueError("BONITA_CALLBACK_TOKEN debe tener al menos 32 caracteres")
        return valor

    @field_validator("session_secret")
    @classmethod
    def validar_session_secret(cls, valor: SecretStr | None) -> SecretStr | None:
        """Rechaza secretos configurados que no sean suficientemente robustos."""

        if valor is not None and len(valor.get_secret_value()) < 32:
            raise ValueError("SESSION_SECRET debe tener al menos 32 caracteres")
        return valor

    @field_validator("admin_initial_password")
    @classmethod
    def validar_admin_initial_password(cls, valor: SecretStr) -> SecretStr:
        """Exige que la contraseña inicial cumpla la política local."""

        if not 8 <= len(valor.get_secret_value()) <= 128:
            raise ValueError(
                "ADMIN_INITIAL_PASSWORD debe tener entre 8 y 128 caracteres"
            )
        return valor

    @model_validator(mode="after")
    def exigir_secret_en_produccion(self) -> Self:
        """Impide iniciar con configuraciones de sesión inseguras."""

        if self.app_env.casefold() == "production" and self.session_secret is None:
            raise ValueError("SESSION_SECRET es obligatorio en producción")
        if (
            self.app_env.casefold() == "production"
            and self.session_cookie_secure is False
        ):
            raise ValueError("las cookies de sesión deben ser Secure en producción")
        if self.app_env.casefold() == "production" and (
            self.bonita_callback_token is None
            or self.bonita_callback_token.get_secret_value()
            == BONITA_CALLBACK_TOKEN_DESARROLLO
        ):
            raise ValueError(
                "BONITA_CALLBACK_TOKEN propio es obligatorio en producción"
            )
        if (
            self.app_env.casefold() == "production"
            and self.admin_initial_password.get_secret_value()
            == ADMIN_INITIAL_PASSWORD_DESARROLLO
        ):
            raise ValueError(
                "ADMIN_INITIAL_PASSWORD propio es obligatorio en producción"
            )
        if self.session_cookie_samesite == "none" and not self.cookies_seguras:
            raise ValueError("SameSite=None requiere cookies Secure")
        if (self.smtp_username is None) is not (self.smtp_password is None):
            raise ValueError("SMTP_USERNAME y SMTP_PASSWORD deben configurarse juntos")
        return self

    @property
    def clave_firma_sesion(self) -> str:
        """Devuelve la clave configurada o una efímera exclusiva de desarrollo."""

        if self.session_secret is not None:
            return self.session_secret.get_secret_value()
        return self._session_secret_desarrollo

    @property
    def cookies_seguras(self) -> bool:
        """Activa cookies Secure por defecto fuera del entorno de desarrollo."""

        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.app_env.casefold() not in {"development", "test"}

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url_override:
            return self.database_url_override

        url = URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )
        return url.render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
