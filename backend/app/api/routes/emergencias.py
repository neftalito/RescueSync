"""Alta municipal de emergencias para la Entrega 2."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import requerir_operacion
from app.core.permissions import OperacionProtegida
from app.core.security import verificar_token_csrf
from app.db.models import Usuario
from app.db.session import get_db
from app.schemas import ErrorResponse
from app.schemas.emergencia import EmergenciaCreate, EmergenciaResponse
from app.services import emergencias as servicio

router = APIRouter()

UsuarioMunicipal = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.REGISTRAR_EMERGENCIA)),
]


def exigir_municipio_con_csrf(
    usuario: UsuarioMunicipal,
    token_csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Usuario:
    """Reautentica al municipio y exige su token CSRF antes de cambiar estado."""

    if not verificar_token_csrf(token_csrf, usuario.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El token CSRF no es válido.",
        )
    return usuario


UsuarioRegistraEmergencia = Annotated[Usuario, Depends(exigir_municipio_con_csrf)]


@router.post(
    "",
    response_model=EmergenciaResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
    summary="Registrar una emergencia municipal",
    description=(
        "Persiste una emergencia con gravedad, zona y descripción en estado "
        "REGISTRADA para el municipio autenticado y la deja PENDIENTE de "
        "vinculación con Bonita. Solo OPERADOR_MUNICIPAL con token CSRF vigente."
    ),
)
def crear_emergencia(
    datos: EmergenciaCreate,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioRegistraEmergencia,
) -> EmergenciaResponse:
    """Valida con Pydantic, persiste con rollback y devuelve la emergencia creada."""

    try:
        emergencia = servicio.registrar_emergencia(session, usuario, datos)
    except servicio.MunicipioInvalidoError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error
    except servicio.DatosEmergenciaInvalidosError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return EmergenciaResponse.model_validate(emergencia)
