"""Endpoints que invocan los conectores REST del proceso RescueSync en Bonita.

No los usa el frontend. Cualquier respuesta 4xx o 5xx deja la tarea de Bonita
en estado fallido, por lo que los rechazos deben ser definitivos y explícitos.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.api.dependencies import GestorTiempoRealDep, validar_callback_bonita
from app.db.models import Convocatoria
from app.db.session import get_db, get_db_consolidado
from app.integrations.bonita.contratos import CABECERA_CASO_RAIZ
from app.schemas import ErrorResponse
from app.schemas.bonita import (
    CierreConvocatoriaRequest,
    ConvocatoriaBonitaResponse,
    NotificacionAperturaRequest,
    OfertasConsolidadasResponse,
)
from app.services import callbacks_bonita as servicio
from app.services.consolidado_nacional import respuesta_consolidada
from app.services.notificaciones import clave_convocatoria_cerrada
from app.services.tiempo_real import programar_evento_confirmado

router = APIRouter(dependencies=[Depends(validar_callback_bonita)])

EmergenciaId = Annotated[int, Path(gt=0)]
CasoBonitaId = Annotated[
    int,
    Header(
        alias=CABECERA_CASO_RAIZ,
        gt=0,
        description="Caso raíz agregado por el conector REST de Bonita.",
    ),
]
RESPUESTAS_ERROR: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}
_CODIGOS_ERROR: dict[type[servicio.CallbackBonitaError], int] = {
    servicio.EmergenciaNoEncontradaError: status.HTTP_404_NOT_FOUND,
    servicio.ConvocatoriaNoEncontradaError: status.HTTP_409_CONFLICT,
    servicio.CasoBonitaNoCorrespondeError: status.HTTP_409_CONFLICT,
    servicio.EstadoConvocatoriaInvalidoError: status.HTTP_409_CONFLICT,
    servicio.FechaCierreInvalidaError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def _ejecutar[T](operacion: Callable[[], T]) -> T:
    try:
        return operacion()
    except servicio.CallbackBonitaError as error:
        raise HTTPException(
            status_code=_CODIGOS_ERROR[type(error)], detail=str(error)
        ) from error


def _verificar_emergencia_del_cuerpo(emergencia_id: int, id_en_cuerpo: int) -> None:
    if emergencia_id != id_en_cuerpo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="idEmergencia no coincide con la ruta.",
        )


def _respuesta_convocatoria(convocatoria: Convocatoria) -> ConvocatoriaBonitaResponse:
    return ConvocatoriaBonitaResponse(
        id_emergencia=convocatoria.emergencia_id,
        convocatoria_id=convocatoria.id,
        numero=convocatoria.numero,
        estado=convocatoria.estado,
        cierra_en=convocatoria.cierra_en,
        cerrada_en=convocatoria.cerrada_en,
    )


@router.post(
    "/{emergencia_id}/notificar-apertura",
    response_model=ConvocatoriaBonitaResponse,
    responses=RESPUESTAS_ERROR,
    summary="Bonita: confirmar apertura de la convocatoria",
    description=(
        "Llamado por la tarea `Enviar notificacion a ONGs de convocatoria`. "
        "Alinea `cierra_en` con la fecha del timer de Bonita. Es idempotente."
    ),
)
def notificar_apertura(
    emergencia_id: EmergenciaId,
    case_id: CasoBonitaId,
    datos: NotificacionAperturaRequest,
    session: Annotated[Session, Depends(get_db)],
    gestor_tiempo_real: GestorTiempoRealDep,
) -> ConvocatoriaBonitaResponse:
    _verificar_emergencia_del_cuerpo(emergencia_id, datos.id_emergencia)
    convocatoria = _ejecutar(
        lambda: servicio.registrar_apertura(
            session,
            emergencia_id=emergencia_id,
            case_id=case_id,
            numero=datos.intento_convocatoria,
            cierra_en=datos.fecha_cierre_ofertas,
        )
    )
    gestor_tiempo_real.programar_metricas()
    return _respuesta_convocatoria(convocatoria)


@router.post(
    "/{emergencia_id}/cerrar-convocatoria",
    response_model=ConvocatoriaBonitaResponse,
    responses=RESPUESTAS_ERROR,
    summary="Bonita: cerrar la convocatoria al vencer el timer",
    description=(
        "Llamado por la tarea `Cerrar convocatoria local`. Impide nuevas ofertas "
        "y tolera reintentos."
    ),
)
def cerrar_convocatoria(
    emergencia_id: EmergenciaId,
    case_id: CasoBonitaId,
    datos: CierreConvocatoriaRequest,
    session: Annotated[Session, Depends(get_db)],
    gestor_tiempo_real: GestorTiempoRealDep,
) -> ConvocatoriaBonitaResponse:
    _verificar_emergencia_del_cuerpo(emergencia_id, datos.id_emergencia)
    convocatoria = _ejecutar(
        lambda: servicio.cerrar_convocatoria(
            session,
            emergencia_id=emergencia_id,
            case_id=case_id,
            numero=datos.intento_convocatoria,
            ahora=datetime.now(UTC),
        )
    )
    programar_evento_confirmado(
        gestor_tiempo_real,
        session,
        clave_convocatoria_cerrada(convocatoria.id),
    )
    return _respuesta_convocatoria(convocatoria)


@router.get(
    "/{emergencia_id}/ofertas-consolidadas",
    response_model=OfertasConsolidadasResponse,
    responses=RESPUESTAS_ERROR,
    summary="Bonita: obtener las ofertas consolidadas",
    description=(
        "Llamado por la tarea `Solicitar ofertas consolidadas`. Devuelve las "
        "ofertas presentadas de la última convocatoria cerrada y `lotesCubiertos`."
    ),
)
def ofertas_consolidadas(
    emergencia_id: EmergenciaId,
    case_id: CasoBonitaId,
    response: Response,
    session: Annotated[Session, Depends(get_db_consolidado)],
    intento_convocatoria: Annotated[
        int | None, Query(alias="intentoConvocatoria", gt=0)
    ] = None,
) -> OfertasConsolidadasResponse:
    consolidado = _ejecutar(
        lambda: servicio.consolidar_ofertas(
            session,
            emergencia_id=emergencia_id,
            case_id=case_id,
            intento_convocatoria=intento_convocatoria,
        )
    )
    response.headers["Cache-Control"] = "no-store"
    return respuesta_consolidada(consolidado, case_id)
