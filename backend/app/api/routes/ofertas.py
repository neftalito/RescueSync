"""Registro de ofertas básicas de una ONG sobre lotes publicados."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import requerir_operacion
from app.core.permissions import OperacionProtegida
from app.core.security import verificar_token_csrf
from app.db.models import Usuario
from app.db.session import get_db
from app.schemas import ErrorResponse
from app.schemas.oferta import OfertaCreateRequest, OfertaItemResponse, OfertaResponse
from app.services import ofertas as servicio

router = APIRouter()

UsuarioOng = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.PRESENTAR_OFERTA)),
]


def exigir_ong_con_csrf(
    usuario: UsuarioOng,
    token_csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Usuario:
    if not verificar_token_csrf(token_csrf, usuario.id, usuario.version_sesion):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El token CSRF no es válido.",
        )
    return usuario


UsuarioPresentaOferta = Annotated[Usuario, Depends(exigir_ong_con_csrf)]

RESPUESTAS_ERROR: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
}
_CODIGOS_ERROR: dict[type[servicio.OfertaError], int] = {
    servicio.OngNoAutorizadaError: status.HTTP_403_FORBIDDEN,
    servicio.ConvocatoriaNoEncontradaError: status.HTTP_404_NOT_FOUND,
    servicio.ConvocatoriaNoReceptivaError: status.HTTP_409_CONFLICT,
    servicio.LoteNoOfertableError: status.HTTP_404_NOT_FOUND,
    servicio.UnidadIncompatibleError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    servicio.DatosOfertaInvalidosError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


@router.post(
    "",
    response_model=OfertaResponse,
    status_code=status.HTTP_201_CREATED,
    responses=RESPUESTAS_ERROR,
    summary="Registrar una oferta básica",
    description=(
        "Registra una oferta de la ONG autenticada sobre uno o más lotes "
        "publicados de una convocatoria abierta. Valida tipo de aporte y "
        "cantidades positivas. Rechaza lotes inexistentes, no publicados o "
        "de otra convocatoria. La transacción es atómica. Solo "
        "REPRESENTANTE_ONG con token CSRF vigente."
    ),
)
def crear_oferta(
    datos: OfertaCreateRequest,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioPresentaOferta,
) -> OfertaResponse:
    try:
        oferta = servicio.registrar_oferta(session, usuario, datos)
    except servicio.OfertaError as error:
        raise HTTPException(
            status_code=_CODIGOS_ERROR[type(error)], detail=str(error)
        ) from error

    version = oferta.versiones[0]
    return OfertaResponse(
        id=oferta.id,
        convocatoria_id=oferta.convocatoria_id,
        emergencia_id=oferta.convocatoria.emergencia_id,
        ong_creadora_id=oferta.ong_creadora_id,
        creada_por_usuario_id=oferta.creada_por_usuario_id,
        estado=oferta.estado,
        version_actual=oferta.version_actual,
        observaciones=version.observaciones,
        presentada_en=version.presentada_en,
        creada_en=oferta.creada_en,
        items=[OfertaItemResponse.model_validate(item) for item in version.items],
    )
