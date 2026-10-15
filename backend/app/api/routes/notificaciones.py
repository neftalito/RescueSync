"""Buzón durable y canal WebSocket de novedades operativas."""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.orm import Session

from app.api.dependencies import (
    UsuarioWebSocket,
    requerir_operacion,
)
from app.api.paginacion import PaginacionDep
from app.core.permissions import OperacionProtegida
from app.core.security import verificar_token_csrf
from app.db.models import RolUsuario, Usuario
from app.db.session import get_db
from app.schemas import ErrorResponse
from app.schemas.notificacion import NotificacionesLeidasResponse, NotificacionResponse
from app.services import notificaciones as servicio
from app.services.tiempo_real import GestorTiempoReal

router = APIRouter()

UsuarioConsultaNotificaciones = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.CONSULTAR_NOTIFICACIONES)),
]
UsuarioMarcaNotificacion = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.MARCAR_NOTIFICACION_LEIDA)),
]
NotificacionId = Annotated[int, Path(gt=0)]


def exigir_usuario_con_csrf(
    usuario: UsuarioMarcaNotificacion,
    token_csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Usuario:
    """Exige CSRF antes de modificar el buzón del usuario."""

    if not verificar_token_csrf(token_csrf, usuario.id, usuario.version_sesion):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El token CSRF no es válido.",
        )
    return usuario


UsuarioActualizaNotificacion = Annotated[Usuario, Depends(exigir_usuario_con_csrf)]


@router.get(
    "",
    response_model=list[NotificacionResponse],
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}},
    summary="Listar las notificaciones propias",
    description=(
        "Devuelve novedades del usuario autenticado. Admite limit (1–100) y offset; sin limit devuelve las últimas 50. "
        "El filtro de destinatario se aplica siempre en PostgreSQL."
    ),
)
def listar_notificaciones(
    paginacion: PaginacionDep,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioConsultaNotificaciones,
) -> list[NotificacionResponse]:
    """Entrega el buzón ordenado desde la novedad más reciente."""

    return [
        NotificacionResponse.model_validate(notificacion)
        for notificacion in servicio.listar_notificaciones(session, usuario, paginacion)
    ]


@router.patch(
    "/leidas",
    response_model=NotificacionesLeidasResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
    summary="Marcar todas las notificaciones propias como leídas",
    description=(
        "Actualiza de forma atómica todas las notificaciones pendientes cuyo "
        "destinatario sea el usuario autenticado. Requiere token CSRF."
    ),
)
def marcar_todas_las_notificaciones_leidas(
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioActualizaNotificacion,
) -> NotificacionesLeidasResponse:
    """Marca todo el buzón propio sin afectar notificaciones de otros usuarios."""

    cantidad, leida_en = servicio.marcar_todas_como_leidas(session, usuario)
    return NotificacionesLeidasResponse(
        cantidad_actualizada=cantidad,
        leida_en=leida_en,
    )


@router.patch(
    "/{notificacion_id}/leida",
    response_model=NotificacionResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
    summary="Marcar una notificación propia como leída",
    description=(
        "Actualiza de forma idempotente únicamente una notificación cuyo "
        "destinatario sea el usuario autenticado. Requiere token CSRF."
    ),
)
def marcar_notificacion_leida(
    notificacion_id: NotificacionId,
    session: Annotated[Session, Depends(get_db)],
    usuario: UsuarioActualizaNotificacion,
) -> NotificacionResponse:
    """Marca la novedad o devuelve 404 sin revelar buzones ajenos."""

    try:
        notificacion = servicio.marcar_como_leida(
            session,
            usuario,
            notificacion_id,
        )
    except servicio.NotificacionNoEncontradaError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    return NotificacionResponse.model_validate(notificacion)


@router.websocket("/ws")
async def novedades_en_tiempo_real(
    websocket: WebSocket,
    usuario: UsuarioWebSocket,
) -> None:
    """Mantiene un canal autenticado para las novedades del usuario."""

    gestor = getattr(websocket.app.state, "gestor_tiempo_real", None)
    if not isinstance(gestor, GestorTiempoReal):
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return
    await gestor.conectar(
        usuario.id, websocket, auditor=usuario.rol == RolUsuario.AUDITOR_DIRECTIVO
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await gestor.desconectar(usuario.id, websocket)
