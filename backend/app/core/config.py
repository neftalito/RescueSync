from functools import lru_cache
from secrets import token_urlsafe
from typing import Literal, Self

from pydantic import Field, PrivateAttr, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


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
    bonita_process_version: str = "1.1"
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

    @field_validator("session_secret", mode="before")
    @classmethod
    def normalizar_session_secret(cls, valor: object) -> object:
        """Interpreta una variable vacía como configuración no provista."""

        return None if valor == "" else valor

    @field_validator("session_secret")
    @classmethod
    def validar_session_secret(cls, valor: SecretStr | None) -> SecretStr | None:
        """Rechaza secretos configurados que no sean suficientemente robustos."""

        if valor is not None and len(valor.get_secret_value()) < 32:
            raise ValueError("SESSION_SECRET debe tener al menos 32 caracteres")
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
        if self.session_cookie_samesite == "none" and not self.cookies_seguras:
            raise ValueError("SameSite=None requiere cookies Secure")
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
