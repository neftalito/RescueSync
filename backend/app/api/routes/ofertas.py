"""Registro y edición versionada de ofertas sobre lotes publicados."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    ClienteNacionalDep,
    GestorTiempoRealDep,
    requerir_operacion,
)
from app.core.permissions import OperacionProtegida
from app.core.security import verificar_token_csrf
from app.db.models import (
    EstadoConvocatoria,
    EstadoOferta,
    Oferta,
    OfertaVersion,
    Organizacion,
    Usuario,
)
from app.db.session import get_db
from app.integrations.nacional.cliente import ErrorNacional
from app.schemas import ErrorResponse
from app.schemas.convocatoria import EmergenciaResumenResponse
from app.schemas.oferta import (
    ConfirmacionConsorcioRequest,
    ConsorcioRequest,
    OfertaCreateRequest,
    OfertaItemResponse,
    OfertaPropiaResponse,
    OfertaResponse,
    OfertaUpdateRequest,
    OngConsorcioResponse,
    ParticipanteResponse,
)
from app.services import consorcios
from app.services import ofertas as servicio
from app.services.notificaciones import clave_oferta_recibida
from app.services.referencias_nacionales import recursos_para_oferta
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
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
    504: {"model": ErrorResponse},
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
    servicio.OfertaYaExisteError: status.HTTP_409_CONFLICT,
    servicio.OfertaNoEncontradaError: status.HTTP_404_NOT_FOUND,
    servicio.OfertaNoEditableError: status.HTTP_409_CONFLICT,
    servicio.VersionOfertaDesactualizadaError: status.HTTP_409_CONFLICT,
    servicio.LoteNoOfertableError: status.HTTP_404_NOT_FOUND,
    servicio.UnidadIncompatibleError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    servicio.CantidadOfrecidaExcedidaError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    servicio.DatosOfertaInvalidosError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def _respuesta(oferta: Oferta, usuario: Usuario) -> OfertaResponse:
    """Arma la respuesta a partir de la versión vigente de la oferta."""

    version = next(v for v in oferta.versiones if v.numero == oferta.version_actual)
    convocatoria = oferta.convocatoria
    return OfertaResponse(
        id=oferta.id,
        convocatoria_id=oferta.convocatoria_id,
        emergencia_id=convocatoria.emergencia_id,
        ong_creadora_id=oferta.ong_creadora_id,
        creada_por_usuario_id=oferta.creada_por_usuario_id,
        estado=oferta.estado,
        version_actual=oferta.version_actual,
        version_bloqueo=oferta.version_bloqueo,
        editable=(
            oferta.ong_creadora_id == usuario.organizacion_id
            and len(version.participantes) <= 1
            and oferta.estado is EstadoOferta.PRESENTADA
            and convocatoria.estado is EstadoConvocatoria.ABIERTA
            and datetime.now(UTC) < convocatoria.cierra_en
        ),
        observaciones=version.observaciones,
        presentada_en=version.presentada_en,
        creada_en=oferta.creada_en,
        items=[OfertaItemResponse.model_validate(item) for item in version.items]
        if version.presentada_en is not None
        else [],
        participantes=[
            ParticipanteResponse(
                ong_id=p.ong_id,
                nombre=p.nombre_ong,
                rol=p.rol,
                confirmada=p.confirmada_en is not None,
            )
            for p in version.participantes
        ],
        requiere_desglose_nacional=version.requiere_desglose_nacional,
        consorcio_editable=(
            len(version.participantes) > 1
            and oferta.estado in {EstadoOferta.BORRADOR, EstadoOferta.PRESENTADA}
            and convocatoria.estado == EstadoConvocatoria.ABIERTA
            and datetime.now(UTC) < convocatoria.cierra_en
        ),
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
        "cantidades positivas que no excedan la necesidad publicada. Rechaza "
        "una segunda oferta de la misma ONG, lotes inexistentes, no publicados "
        "o de otra convocatoria. La transacción es atómica. Solo "
        "REPRESENTANTE_ONG con token CSRF vigente."
    ),
)
def crear_oferta(
    datos: OfertaCreateRequest,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioPresentaOferta,
    gestor_tiempo_real: GestorTiempoRealDep,
    cliente_nacional: ClienteNacionalDep,
) -> OfertaResponse:
    try:
        referencias = recursos_para_oferta(session, usuario, cliente_nacional, datos)
        oferta = servicio.registrar_oferta(
            session, usuario, datos, referencias=referencias
        )
    except ErrorNacional as error:
        session.rollback()
        raise HTTPException(error.status, str(error)) from error
    except servicio.OfertaError as error:
        session.rollback()
        raise HTTPException(
            status_code=_CODIGOS_ERROR[type(error)], detail=str(error)
        ) from error

    programar_evento_confirmado(
        gestor_tiempo_real,
        session,
        clave_oferta_recibida(oferta.id),
    )
    return _respuesta(oferta, usuario)


@router.put(
    "/{oferta_id}",
    response_model=OfertaResponse,
    status_code=status.HTTP_200_OK,
    responses=RESPUESTAS_ERROR,
    summary="Modificar una oferta propia",
    description=(
        "Crea una nueva versión inmutable de la oferta de la ONG autenticada. "
        "Solo permite editar una oferta presentada mientras su convocatoria "
        "permanezca abierta y rechaza versiones de bloqueo desactualizadas."
    ),
)
def modificar_oferta(
    oferta_id: int,
    datos: OfertaUpdateRequest,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioPresentaOferta,
    cliente_nacional: ClienteNacionalDep,
) -> OfertaResponse:
    """Actualiza el contenido sin perder la versión previamente presentada."""

    try:
        referencias = recursos_para_oferta(session, usuario, cliente_nacional, datos)
        oferta = servicio.actualizar_oferta(
            session, usuario, oferta_id, datos, referencias=referencias
        )
    except ErrorNacional as error:
        session.rollback()
        raise HTTPException(error.status, str(error)) from error
    except servicio.OfertaError as error:
        raise HTTPException(
            status_code=_CODIGOS_ERROR[type(error)], detail=str(error)
        ) from error
    return _respuesta(oferta, usuario)


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
            **_respuesta(oferta, usuario).model_dump(),
            emergencia=EmergenciaResumenResponse.model_validate(
                oferta.convocatoria.emergencia
            ),
        )
        for oferta in ofertas
    ]


@router.get(
    "/ongs-disponibles",
    response_model=list[OngConsorcioResponse],
    summary="Consultar ONGs con oferta individual para un consorcio",
)
def ongs_disponibles(
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioConsultaOfertas,
    convocatoria_id: int,
) -> list[OngConsorcioResponse]:
    filas = session.execute(
        select(Organizacion.id, Organizacion.nombre)
        .join(Oferta, Oferta.ong_creadora_id == Organizacion.id)
        .join(
            OfertaVersion,
            (OfertaVersion.oferta_id == Oferta.id)
            & (OfertaVersion.numero == Oferta.version_actual),
        )
        .where(
            Oferta.convocatoria_id == convocatoria_id,
            Oferta.estado == EstadoOferta.PRESENTADA,
            Oferta.fusionada_en_oferta_id.is_(None),
            OfertaVersion.requiere_desglose_nacional,
            Organizacion.activa,
            Organizacion.id != usuario.organizacion_id,
        )
        .order_by(Organizacion.nombre, Organizacion.id)
    )
    return [
        OngConsorcioResponse(ong_id=ong_id, nombre=nombre) for ong_id, nombre in filas
    ]


@router.post(
    "/{oferta_id}/consorcio",
    response_model=OfertaResponse,
    responses=RESPUESTAS_ERROR,
    summary="Proponer consorcio con ofertas individuales",
)
def proponer_consorcio(
    oferta_id: int,
    datos: ConsorcioRequest,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioPresentaOferta,
) -> OfertaResponse:
    try:
        oferta = consorcios.proponer_consorcio(
            session, usuario, oferta_id, datos.version_bloqueo, datos.ong_ids
        )
    except servicio.OfertaError as error:
        session.rollback()
        raise HTTPException(_CODIGOS_ERROR[type(error)], str(error)) from error
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            409, "La propuesta no pudo confirmarse. Actualizá el listado."
        ) from error
    return _respuesta(oferta, usuario)


@router.post(
    "/{oferta_id}/consorcio/confirmacion",
    response_model=OfertaResponse,
    responses=RESPUESTAS_ERROR,
    summary="Confirmar mis aportes a la versión propuesta",
)
def confirmar_consorcio(
    oferta_id: int,
    datos: ConfirmacionConsorcioRequest,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioPresentaOferta,
) -> OfertaResponse:
    try:
        oferta = consorcios.confirmar_consorcio(
            session, usuario, oferta_id, datos.version_bloqueo
        )
    except servicio.OfertaError as error:
        session.rollback()
        raise HTTPException(_CODIGOS_ERROR[type(error)], str(error)) from error
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            409, "La propuesta no pudo confirmarse. Actualizá el listado."
        ) from error
    return _respuesta(oferta, usuario)


@router.delete(
    "/{oferta_id}/consorcio",
    response_model=OfertaResponse,
    responses=RESPUESTAS_ERROR,
    summary="Rechazar o desarmar el consorcio durante la convocatoria",
)
def desarmar_consorcio(
    oferta_id: int,
    datos: ConfirmacionConsorcioRequest,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioPresentaOferta,
) -> OfertaResponse:
    try:
        oferta = consorcios.desarmar_consorcio(
            session, usuario, oferta_id, datos.version_bloqueo
        )
    except servicio.OfertaError as error:
        session.rollback()
        raise HTTPException(_CODIGOS_ERROR[type(error)], str(error)) from error
    return _respuesta(oferta, usuario)
