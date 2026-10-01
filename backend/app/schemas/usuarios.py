from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from app.db.models.enums import RolUsuario, TipoOrganizacion


class OrganizacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    tipo: TipoOrganizacion


class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    rol: RolUsuario
    organizacion: OrganizacionResponse | None
    activo: bool
    requiere_cambio_password: bool
    creado_en: datetime
    actualizado_en: datetime


class UsuarioCreate(BaseModel):
    email: EmailStr
    rol: RolUsuario
    organizacion_id: int | None = Field(default=None, gt=0)

    @field_validator("email", mode="before")
    @classmethod
    def normalizar_email(cls, valor: object) -> object:
        """Elimina espacios accidentales antes de validar el correo."""

        return valor.strip() if isinstance(valor, str) else valor


class UsuarioUpdate(BaseModel):
    email: EmailStr | None = None
    rol: RolUsuario | None = None
    organizacion_id: int | None = Field(default=None, gt=0)
    activo: bool | None = None

    @field_validator("email", mode="before")
    @classmethod
    def normalizar_email(cls, valor: object) -> object:
        """Elimina espacios accidentales antes de validar el correo."""

        return valor.strip() if isinstance(valor, str) else valor

    @model_validator(mode="after")
    def validar_campos(self) -> "UsuarioUpdate":
        """Rechaza parches vacíos y valores nulos en campos no anulables."""

        if not self.model_fields_set:
            raise ValueError("se debe indicar al menos un campo para modificar")
        for campo in ("email", "rol", "activo"):
            if campo in self.model_fields_set and getattr(self, campo) is None:
                raise ValueError(f"{campo} no puede ser nulo")
        return self


class PasswordTemporalRequest(BaseModel):
    password: SecretStr = Field(min_length=8, max_length=128)
