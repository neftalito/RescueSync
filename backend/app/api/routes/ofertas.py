"""Registro de ofertas básicas de una ONG sobre lotes publicados."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import GestorTiempoRealDep, requerir_operacion
from app.core.permissions import OperacionProtegida
from app.core.security import verificar_token_csrf
from app.db.models import Oferta, Usuario
from app.db.session import get_db
from app.schemas import ErrorResponse
from app.schemas.convocatoria import EmergenciaResumenResponse
from app.schemas.oferta import (
    OfertaCreateRequest,
    OfertaItemResponse,
    OfertaPropiaResponse,
    OfertaResponse,
)
from app.services import ofertas as servicio
from app.services.notificaciones import clave_oferta_recibida
from app.services.tiempo_real import programar_evento_confirmado

router = APIRouter()

UsuarioOng = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.PRESENTAR_OFERTA)),
]
UsuarioConsultaOfertas = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.CONSULTAR_OFERTAS_PROPIAS)),
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


def _respuesta(oferta: Oferta) -> OfertaResponse:
    """Arma la respuesta a partir de la versión vigente de la oferta."""

    version = next(v for v in oferta.versiones if v.numero == oferta.version_actual)
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
    gestor_tiempo_real: GestorTiempoRealDep,
) -> OfertaResponse:
    try:
        oferta = servicio.registrar_oferta(session, usuario, datos)
    except servicio.OfertaError as error:
        raise HTTPException(
            status_code=_CODIGOS_ERROR[type(error)], detail=str(error)
        ) from error

    programar_evento_confirmado(
        gestor_tiempo_real,
        session,
        clave_oferta_recibida(oferta.id),
    )
    return _respuesta(oferta)


@router.get(
    "",
    response_model=list[OfertaPropiaResponse],
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}},
    summary="Listar mis ofertas",
    description=(
        "Devuelve las ofertas presentadas por la ONG activa del usuario "
        "autenticado, con el contexto de la emergencia, sin exponer ofertas "
        "de otra organización. Solo REPRESENTANTE_ONG."
    ),
)
def listar_mis_ofertas(
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioConsultaOfertas,
) -> list[OfertaPropiaResponse]:
    """Consulta las ofertas de la ONG del usuario sin modificar nada."""

    try:
        ofertas = servicio.listar_ofertas_propias(session, usuario)
    except servicio.OfertaError as error:
        raise HTTPException(
            status_code=_CODIGOS_ERROR[type(error)], detail=str(error)
        ) from error
    return [
        OfertaPropiaResponse(
            **_respuesta(oferta).model_dump(),
            emergencia=EmergenciaResumenResponse.model_validate(
                oferta.convocatoria.emergencia
            ),
        )
        for oferta in ofertas
    ]
