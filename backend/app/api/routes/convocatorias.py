"""Publicación explícita de la convocatoria de una emergencia."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.dependencies import requerir_operacion
from app.core.permissions import OperacionProtegida
from app.core.security import verificar_token_csrf
from app.db.models import Convocatoria, Usuario
from app.db.session import get_db
from app.schemas import ErrorResponse
from app.schemas.convocatoria import ConvocatoriaResponse, LotePublicadoResponse
from app.services import convocatorias as servicio

router = APIRouter()

UsuarioCoordinador = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.PUBLICAR_CONVOCATORIA)),
]
EmergenciaId = Annotated[int, Path(gt=0)]


def exigir_coordinador_con_csrf(
    usuario: UsuarioCoordinador,
    token_csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Usuario:
    """Reautentica al coordinador y exige su token CSRF antes de publicar."""

    if not verificar_token_csrf(token_csrf, usuario.id, usuario.version_sesion):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El token CSRF no es válido.",
        )
    return usuario


UsuarioPublicaConvocatoria = Annotated[Usuario, Depends(exigir_coordinador_con_csrf)]

RESPUESTAS_ERROR: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
}
_CODIGOS_ERROR: dict[type[servicio.ConvocatoriaError], int] = {
    servicio.EmergenciaNoEncontradaError: status.HTTP_404_NOT_FOUND,
    servicio.CentroNoAutorizadoError: status.HTTP_403_FORBIDDEN,
    servicio.EstadoEmergenciaInvalidoError: status.HTTP_409_CONFLICT,
    servicio.SinLotesValidosError: status.HTTP_409_CONFLICT,
    servicio.DatosConvocatoriaInvalidosError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def _respuesta(convocatoria: Convocatoria) -> ConvocatoriaResponse:
    """Arma la respuesta con los lotes ordenados de forma determinista."""

    return ConvocatoriaResponse(
        id=convocatoria.id,
        emergencia_id=convocatoria.emergencia_id,
        numero=convocatoria.numero,
        estado=convocatoria.estado,
        publicada_en=convocatoria.publicada_en,
        cierra_en=convocatoria.cierra_en,
        lotes=[
            LotePublicadoResponse.model_validate(publicacion)
            for publicacion in sorted(convocatoria.lotes, key=lambda p: p.lote_id)
        ],
    )


@router.post(
    "/{emergencia_id}/publicar",
    response_model=ConvocatoriaResponse,
    status_code=status.HTTP_201_CREATED,
    responses=RESPUESTAS_ERROR,
    summary="Publicar la convocatoria de una emergencia",
    description=(
        "Exige al menos un lote en borrador, crea la convocatoria y "
        "transiciona la emergencia a PUBLICADA de forma atómica. Solo el "
        "centro coordinador asignado, con token CSRF vigente. La "
        "sincronización con la tarea humana de Bonita queda para un ticket "
        "de seguimiento: `cierra_en` se guarda con un valor provisorio."
    ),
)
def publicar_convocatoria(
    emergencia_id: EmergenciaId,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioPublicaConvocatoria,
) -> ConvocatoriaResponse:
    """Valida el estado en base de datos y publica la convocatoria."""

    try:
        convocatoria = servicio.publicar_convocatoria(session, usuario, emergencia_id)
    except servicio.ConvocatoriaError as error:
        raise HTTPException(
            status_code=_CODIGOS_ERROR[type(error)], detail=str(error)
        ) from error
    return _respuesta(convocatoria)
