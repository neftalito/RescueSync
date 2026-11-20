"""Publicación explícita de la convocatoria de una emergencia."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.api.busqueda import BusquedaDep
from app.api.dependencies import (
    ClienteBonitaDep,
    GestorTiempoRealDep,
    requerir_operacion,
)
from app.api.paginacion import PaginacionDep
from app.core.permissions import OperacionProtegida
from app.core.security import verificar_token_csrf
from app.db.models import Convocatoria, ConvocatoriaLote, Usuario
from app.db.session import get_db
from app.schemas import ErrorResponse
from app.schemas.convocatoria import (
    ConvocatoriaAbiertaResponse,
    ConvocatoriaResponse,
    EmergenciaResumenResponse,
    LotePublicadoResponse,
)
from app.services import convocatorias as servicio
from app.services.notificaciones import clave_convocatoria_publicada
from app.services.publicacion_bonita import completar_generacion_lotes
from app.services.tiempo_real import programar_evento_confirmado

router = APIRouter()
router_publico = APIRouter()

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
            _respuesta_lote(publicacion)
            for publicacion in sorted(convocatoria.lotes, key=lambda p: p.lote_id)
        ],
        bonita_generar_lotes_estado=convocatoria.bonita_generar_lotes_estado,
        bonita_generar_lotes_ultimo_error=convocatoria.bonita_generar_lotes_ultimo_error,
        bonita_generar_lotes_ultimo_intento_en=(
            convocatoria.bonita_generar_lotes_ultimo_intento_en
        ),
    )


def _respuesta_lote(publicacion: ConvocatoriaLote) -> LotePublicadoResponse:
    """Expone el snapshot cuantitativo junto con el detalle legible del lote."""

    return LotePublicadoResponse(
        lote_id=publicacion.lote_id,
        tipo_necesidad=publicacion.lote.tipo_necesidad,
        descripcion=publicacion.lote.descripcion,
        cantidad_publicada=publicacion.cantidad_publicada,
        unidad_publicada=publicacion.unidad_publicada,
        capacidad_nacional_id=publicacion.capacidad_nacional_id,
        codigo_capacidad_publicada=publicacion.codigo_capacidad_publicada,
        riesgo_requerido_publicado=publicacion.riesgo_requerido_publicado,
    )


@router.post(
    "/{emergencia_id}/publicar",
    response_model=ConvocatoriaResponse,
    status_code=status.HTTP_201_CREATED,
    responses=RESPUESTAS_ERROR,
    summary="Publicar la convocatoria de una emergencia",
    description=(
        "Exige al menos un lote en borrador, crea la convocatoria y "
        "transiciona la emergencia a PUBLICADA de forma atómica; `cierra_en` "
        "se guarda con un valor provisorio hasta que Bonita confirme la "
        "fecha real. Completa además la tarea `Generar lotes de "
        "necesidades` en Bonita; si esa sincronización falla, la "
        "publicación local igual queda confirmada y se puede reintentar "
        "llamando de nuevo a este mismo endpoint. Solo el centro "
        "coordinador asignado, con token CSRF vigente."
    ),
)
def publicar_convocatoria(
    emergencia_id: EmergenciaId,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioPublicaConvocatoria,
    cliente: ClienteBonitaDep,
    gestor_tiempo_real: GestorTiempoRealDep,
) -> ConvocatoriaResponse:
    """Valida el estado en base de datos, publica y sincroniza con Bonita."""

    try:
        convocatoria = servicio.publicar_convocatoria(session, usuario, emergencia_id)
    except servicio.ConvocatoriaError as error:
        raise HTTPException(
            status_code=_CODIGOS_ERROR[type(error)], detail=str(error)
        ) from error
    convocatoria = completar_generacion_lotes(
        session, convocatoria.emergencia, convocatoria, cliente
    )
    programar_evento_confirmado(
        gestor_tiempo_real,
        session,
        clave_convocatoria_publicada(convocatoria.id),
    )
    return _respuesta(convocatoria)


@router_publico.get(
    "",
    response_model=list[ConvocatoriaAbiertaResponse],
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}},
    summary="Listar convocatorias abiertas",
    description=(
        "Devuelve las convocatorias actualmente abiertas con sus lotes "
        "publicados y el contexto mínimo de la emergencia (zona, gravedad y "
        "descripción), para que cualquier ONG activa identifique dónde "
        "ofertar. Solo REPRESENTANTE_ONG."
    ),
)
def listar_convocatorias_abiertas(
    paginacion: PaginacionDep,
    busqueda: BusquedaDep,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioConsultaConvocatorias,
    zona: Annotated[
        str, Query(max_length=120, description="Texto de la zona afectada.")
    ] = "",
) -> list[ConvocatoriaAbiertaResponse]:
    """Consulta las convocatorias abiertas sin reclamar ni modificar nada."""

    convocatorias = servicio.listar_convocatorias_abiertas(
        session, paginacion, busqueda=busqueda, zona=zona.strip()
    )
    return [
        ConvocatoriaAbiertaResponse(
            requiere_desglose_nacional=bool(convocatoria.sistema_origen_ref),
            id=convocatoria.id,
            emergencia_id=convocatoria.emergencia_id,
            numero=convocatoria.numero,
            estado=convocatoria.estado,
            publicada_en=convocatoria.publicada_en,
            cierra_en=convocatoria.cierra_en,
            lotes=[
                _respuesta_lote(publicacion)
                for publicacion in sorted(
                    convocatoria.lotes, key=lambda publicacion: publicacion.lote_id
                )
            ],
            emergencia=EmergenciaResumenResponse.model_validate(
                convocatoria.emergencia
            ),
        )
        for convocatoria in convocatorias
    ]
