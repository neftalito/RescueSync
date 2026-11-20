"""Alta municipal de emergencias para la Entrega 2."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
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
from app.db.models import EstadoEmergencia, Usuario
from app.db.session import get_db
from app.schemas import ErrorResponse
from app.schemas.emergencia import (
    EmergenciaCreate,
    EmergenciaEnBandejaResponse,
    EmergenciaResponse,
)
from app.services import emergencias as servicio
from app.services.notificaciones import clave_emergencia_registrada
from app.services.tiempo_real import programar_evento_confirmado
from app.services.vinculacion_bonita import vincular_emergencia_con_bonita

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

    if not verificar_token_csrf(token_csrf, usuario.id, usuario.version_sesion):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El token CSRF no es válido.",
        )
    return usuario


UsuarioRegistraEmergencia = Annotated[Usuario, Depends(exigir_municipio_con_csrf)]
EmergenciaId = Annotated[int, Path(gt=0)]


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
        "REGISTRADA para el municipio autenticado y luego inicia su instancia "
        "en Bonita. Si Bonita falla, la emergencia se conserva con el estado "
        "de sincronización y un error seguro para reintentar. Solo "
        "OPERADOR_MUNICIPAL con token CSRF vigente."
    ),
)
def crear_emergencia(
    datos: EmergenciaCreate,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioRegistraEmergencia,
    cliente: ClienteBonitaDep,
    gestor_tiempo_real: GestorTiempoRealDep,
) -> EmergenciaResponse:
    """Confirma el alta local y vincula su instancia de Bonita de forma trazable."""

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
    emergencia = vincular_emergencia_con_bonita(session, emergencia, cliente)
    programar_evento_confirmado(
        gestor_tiempo_real,
        session,
        clave_emergencia_registrada(emergencia.id),
    )
    return EmergenciaResponse.model_validate(emergencia)


@router.post(
    "/{emergencia_id}/reintentar-bonita",
    response_model=EmergenciaResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
    summary="Reintentar la vinculación de una emergencia con Bonita",
    description=(
        "Reanuda de forma idempotente una vinculación fallida. Si un POST "
        "anterior tuvo resultado incierto, busca primero el caso existente "
        "para no duplicarlo. Los reclamos concurrentes se serializan. Solo "
        "el municipio dueño, con token CSRF vigente."
    ),
)
def reintentar_vinculacion_bonita(
    emergencia_id: EmergenciaId,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioRegistraEmergencia,
    cliente: ClienteBonitaDep,
    gestor_tiempo_real: GestorTiempoRealDep,
) -> EmergenciaResponse:
    """Autoriza el reintento y devuelve el estado de sincronización resultante."""

    try:
        emergencia = servicio.obtener_emergencia_para_reintento(
            session, usuario, emergencia_id
        )
    except servicio.EmergenciaNoEncontradaError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except (
        servicio.MunicipioInvalidoError,
        servicio.EmergenciaNoAutorizadaError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error
    emergencia = vincular_emergencia_con_bonita(session, emergencia, cliente)
    gestor_tiempo_real.programar_metricas()
    return EmergenciaResponse.model_validate(emergencia)


UsuarioConsultaEmergencias = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.CONSULTAR_EMERGENCIAS)),
]


@router.get(
    "",
    response_model=list[EmergenciaEnBandejaResponse],
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
    summary="Consultar la bandeja de emergencias del rol autenticado",
    description=(
        "Un municipio ve únicamente sus propias emergencias con su estado "
        "actual. Un centro coordinador ve las emergencias REGISTRADA sin "
        "centro asignado y todas las asignadas al suyo, en cualquier estado. "
        "Cada resultado indica si tiene lotes para separar pendientes de "
        "emergencias con lotes creados. La autorización se aplica en el backend."
    ),
)
def listar_bandeja_emergencias(
    paginacion: PaginacionDep,
    busqueda: BusquedaDep,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioConsultaEmergencias,
    tiene_lotes: bool | None = None,
    estado: EstadoEmergencia | None = None,
) -> list[EmergenciaEnBandejaResponse]:
    """Devuelve la bandeja de emergencias filtrada por rol y organización vigente."""

    try:
        emergencias = servicio.listar_emergencias(
            session,
            usuario,
            paginacion,
            tiene_lotes=tiene_lotes,
            estado=estado,
            busqueda=busqueda,
        )
    except servicio.MunicipioInvalidoError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error
    except servicio.CentroInvalidoError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error
    con_lotes = servicio.ids_emergencias_con_lotes(session, emergencias)
    return [
        EmergenciaEnBandejaResponse(
            **EmergenciaResponse.model_validate(emergencia).model_dump(),
            tiene_lotes=emergencia.id in con_lotes,
        )
        for emergencia in emergencias
    ]
