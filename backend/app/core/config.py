from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
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

    bonita_base_url: str = "http://host.docker.internal:8080/bonita"
    bonita_username: str = "install"
    bonita_password: str = "install"
    bonita_process_definition_id: str = ""

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

