"""Consulta, creación, edición y eliminación de lotes de necesidades en borrador."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    ClienteNacionalDep,
    GestorTiempoRealDep,
    requerir_operacion,
)
from app.api.paginacion import PaginacionDep
from app.core.permissions import OperacionProtegida
from app.core.security import verificar_token_csrf
from app.db.models import RolUsuario, Usuario
from app.db.session import get_db
from app.integrations.nacional.cliente import ErrorNacional
from app.schemas import ErrorResponse
from app.schemas.inventario import CapacidadResponse
from app.schemas.lote import LotePublicadoPublicoResponse, LoteResponse, LotesRequest
from app.services import lotes as servicio
from app.services.referencias_nacionales import capacidades_para_lotes, catalogo_tecnico

router = APIRouter()

UsuarioCoordinador = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.GESTIONAR_LOTES)),
]
UsuarioConsultaLotes = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.CONSULTAR_LOTES_PUBLICADOS)),
]
EmergenciaId = Annotated[int, Path(gt=0)]
LoteId = Annotated[int, Path(gt=0)]


def exigir_coordinador_con_csrf(
    usuario: UsuarioCoordinador,
    token_csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Usuario:
    """Reautentica al coordinador y exige su token CSRF antes de cambiar estado."""

    if not verificar_token_csrf(token_csrf, usuario.id, usuario.version_sesion):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El token CSRF no es válido.",
        )
    return usuario


UsuarioGestionaLotes = Annotated[Usuario, Depends(exigir_coordinador_con_csrf)]

RESPUESTAS_ERROR: dict[int | str, dict[str, object]] = {
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
    504: {"model": ErrorResponse},
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
}
_CODIGOS_ERROR: dict[type[servicio.LoteError], int] = {
    servicio.EmergenciaNoEncontradaError: status.HTTP_404_NOT_FOUND,
    servicio.CentroNoAutorizadoError: status.HTTP_403_FORBIDDEN,
    servicio.OngNoAutorizadaError: status.HTTP_403_FORBIDDEN,
    servicio.LoteNoEncontradoError: status.HTTP_404_NOT_FOUND,
    servicio.LoteNoEditableError: status.HTTP_409_CONFLICT,
    servicio.EstadoEmergenciaInvalidoError: status.HTTP_409_CONFLICT,
    servicio.LoteDesactualizadoError: status.HTTP_409_CONFLICT,
    servicio.DatosLoteInvalidosError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


@router.post(
    "/{emergencia_id}/lotes",
    response_model=list[LoteResponse],
    status_code=status.HTTP_201_CREATED,
    responses=RESPUESTAS_ERROR,
    summary="Crear o editar lotes en borrador",
    description=(
        "Registra uno o más lotes con tipo y cantidad positiva para la "
        "emergencia. Los ítems sin `id` se crean y los que traen `id` deben "
        "incluir su `version`, pertenecer a la emergencia y seguir en borrador. "
        "Una versión obsoleta responde 409. Guardar nunca publica la "
        "convocatoria. Solo el centro coordinador con token CSRF vigente."
    ),
)
def guardar_lotes(
    emergencia_id: EmergenciaId,
    datos: LotesRequest,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioGestionaLotes,
    cliente_nacional: ClienteNacionalDep,
    gestor_tiempo_real: GestorTiempoRealDep,
) -> list[LoteResponse]:
    """Valida con Pydantic, guarda en una transacción y devuelve los lotes."""

    try:
        capacidades = capacidades_para_lotes(cliente_nacional, datos.lotes)
        lotes = servicio.guardar_lotes(
            session, usuario, emergencia_id, datos.lotes, capacidades
        )
    except ErrorNacional as error:
        session.rollback()
        raise HTTPException(error.status, str(error)) from error
    except servicio.LoteError as error:
        session.rollback()
        raise HTTPException(
            status_code=_CODIGOS_ERROR[type(error)], detail=str(error)
        ) from error
    gestor_tiempo_real.programar_metricas()
    return [LoteResponse.model_validate(lote) for lote in lotes]


@router.get(
    "/catalogos/capacidades-nacionales",
    response_model=list[CapacidadResponse],
    summary="Consultar capacidades nacionales para lotes",
    responses={
        codigo: {"model": ErrorResponse} for codigo in (401, 403, 502, 503, 504)
    },
)
def capacidades_nacionales(
    usuario: UsuarioConsultaLotes,
    cliente_nacional: ClienteNacionalDep,
) -> list[CapacidadResponse]:
    if usuario.rol != RolUsuario.COORDINADOR_REGIONAL:
        raise HTTPException(403, "El catálogo de coordinación requiere un coordinador.")
    try:
        return catalogo_tecnico(cliente_nacional)
    except ErrorNacional as error:
        raise HTTPException(error.status, str(error)) from error


@router.get(
    "/{emergencia_id}/lotes",
    response_model=list[LoteResponse | LotePublicadoPublicoResponse],
    status_code=status.HTTP_200_OK,
    responses={
        codigo: RESPUESTAS_ERROR[codigo]
        for codigo in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )
    },
    summary="Listar los lotes de una emergencia",
    description=(
        "Devuelve los lotes de la emergencia según quién consulta. El centro "
        "coordinador asignado ve todos los lotes, en borrador o publicados, "
        "ordenados por alta, para retomar su edición; si aún no tiene centro, "
        "la lista está vacía y la consulta no la reclama. Una ONG activa ve "
        "únicamente los lotes ya publicados. El campo `estado` indica cuáles "
        "siguen siendo editables."
    ),
)
def listar_lotes(
    paginacion: PaginacionDep,
    emergencia_id: EmergenciaId,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioConsultaLotes,
) -> list[LoteResponse | LotePublicadoPublicoResponse]:
    """Consulta los lotes del centro autenticado sin modificar la emergencia."""

    try:
        lotes = servicio.listar_lotes(session, usuario, emergencia_id, paginacion)
    except servicio.LoteError as error:
        raise _error_http(error) from error
    if usuario.rol is RolUsuario.REPRESENTANTE_ONG:
        return [LotePublicadoPublicoResponse.model_validate(lote) for lote in lotes]
    return [LoteResponse.model_validate(lote) for lote in lotes]


@router.delete(
    "/{emergencia_id}/lotes/{lote_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        codigo: RESPUESTAS_ERROR[codigo]
        for codigo in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
        )
    },
    summary="Eliminar un lote en borrador",
    description=(
        "Quita definitivamente un lote que sigue en borrador. Un lote "
        "publicado, cerrado o cancelado responde 409 y se conserva. Repetir "
        "la eliminación responde 404. Solo el centro coordinador asignado con "
        "token CSRF vigente."
    ),
)
def eliminar_lote(
    emergencia_id: EmergenciaId,
    lote_id: LoteId,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioGestionaLotes,
) -> None:
    """Elimina el borrador en una transacción propia."""

    try:
        servicio.eliminar_lote(session, usuario, emergencia_id, lote_id)
    except servicio.LoteError as error:
        raise _error_http(error) from error


def _error_http(error: servicio.LoteError) -> HTTPException:
    """Traduce un error de dominio de lotes a su respuesta HTTP."""

    return HTTPException(status_code=_CODIGOS_ERROR[type(error)], detail=str(error))
