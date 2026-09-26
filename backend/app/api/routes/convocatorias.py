"""Publicación explícita de la convocatoria de una emergencia."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import requerir_operacion
from app.core.permissions import OperacionProtegida
from app.core.security import verificar_token_csrf
from app.db.models import Convocatoria, EstadoConvocatoria, Usuario
from app.db.session import get_db
from app.schemas import ErrorResponse
from app.schemas.convocatoria import (
    ConvocatoriaResponse,
    ConvocatoriaResumenResponse,
    ConvocatoriasListResponse,
    LotePublicadoResponse,
)
from app.services import convocatorias as servicio
from app.services.convocatorias import ConvocatoriaResumen

router = APIRouter()
consultas_router = APIRouter()

UsuarioCoordinador = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.PUBLICAR_CONVOCATORIA)),
]
UsuarioConsultaConvocatorias = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.CONSULTAR_CONVOCATORIAS)),
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


def _resumen(fila: ConvocatoriaResumen) -> ConvocatoriaResumenResponse:
    """Proyecta la fila del servicio al contrato HTTP del listado."""

    return ConvocatoriaResumenResponse(
        id=fila.id,
        emergencia_id=fila.emergencia_id,
        numero=fila.numero,
        estado=fila.estado,
        publicada_en=fila.publicada_en,
        cierra_en=fila.cierra_en,
        cantidad_lotes=fila.cantidad_lotes,
        gravedad=fila.gravedad,
        zona=fila.zona,
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


@consultas_router.get(
    "",
    response_model=ConvocatoriasListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
    summary="Listar las convocatorias del centro coordinador",
    description=(
        "Devuelve las convocatorias de las emergencias asignadas al centro "
        "coordinador del usuario autenticado, de la más reciente a la más "
        "antigua, con la cantidad de lotes publicados. `estado` acota el "
        "resultado a `ABIERTA`, `CERRADA` o `CANCELADA`; si se omite, llegan "
        "todas. No requiere token CSRF por ser una consulta."
    ),
)
def listar_convocatorias(
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioConsultaConvocatorias,
    estado: Annotated[EstadoConvocatoria | None, Query()] = None,
) -> ConvocatoriasListResponse:
    """Lista las convocatorias visibles para el coordinador autenticado."""

    try:
        filas = servicio.listar_convocatorias(session, usuario, estado)
    except servicio.CentroNoAutorizadoError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(error)
        ) from error
    return ConvocatoriasListResponse(items=[_resumen(fila) for fila in filas])
