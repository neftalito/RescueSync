from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.db.models.enums import TipoOrganizacion


class OrganizacionCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=160)
    tipo: TipoOrganizacion
    email_contacto: EmailStr | None = None

    @field_validator("nombre", mode="before")
    @classmethod
    def normalizar_nombre(cls, valor: object) -> object:
        """Elimina espacios exteriores antes de validar y persistir el nombre."""

        return valor.strip() if isinstance(valor, str) else valor


class OrganizacionUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    tipo: TipoOrganizacion | None = None
    activa: bool | None = None

    @field_validator("nombre", mode="before")
    @classmethod
    def normalizar_nombre(cls, valor: object) -> object:
        """Elimina espacios exteriores antes de validar el nuevo nombre."""

        return valor.strip() if isinstance(valor, str) else valor

    @model_validator(mode="after")
    def validar_campos(self) -> "OrganizacionUpdate":
        """Rechaza parches vacíos y valores nulos en campos no anulables."""

        if not self.model_fields_set:
            raise ValueError("se debe indicar al menos un campo para modificar")
        for campo in self.model_fields_set:
            if getattr(self, campo) is None:
                raise ValueError(f"{campo} no puede ser nulo")
        return self


class OrganizacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    tipo: TipoOrganizacion
    activa: bool
    ong_nacional_id: UUID | None = None
