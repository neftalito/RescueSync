from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from app.db.models.enums import RolUsuario, TipoOrganizacion


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalizar_email(cls, valor: object) -> object:
        """Elimina espacios accidentales antes de validar el correo."""

        return valor.strip() if isinstance(valor, str) else valor


class OrganizacionSesion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    tipo: TipoOrganizacion


class UsuarioSesion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    rol: RolUsuario
    organizacion: OrganizacionSesion | None
    requiere_cambio_password: bool


class SesionResponse(BaseModel):
    usuario: UsuarioSesion
    csrf_token: str


class CambioPasswordRequest(BaseModel):
    password_actual: SecretStr = Field(min_length=8, max_length=128)
    password_nueva: SecretStr = Field(min_length=8, max_length=128)
