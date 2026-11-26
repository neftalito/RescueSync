from collections.abc import Callable
from secrets import compare_digest
from typing import Annotated

from fastapi import (
    Cookie,
    Depends,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketException,
    status,
)
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import OperacionProtegida, roles_habilitados_para
from app.core.security import leer_credencial_sesion, verificar_token_csrf
from app.db.models import RolUsuario, Usuario
from app.db.session import get_db
from app.integrations.bonita.cliente import ClienteBonita
from app.integrations.email.cliente import ClienteSMTP
from app.integrations.nacional.cliente import ClienteNacional
from app.integrations.prioridad import ClientePrioridad
from app.services.auth import obtener_usuario_vigente
from app.services.tiempo_real import GestorTiempoReal

settings = get_settings()


def obtener_usuario_actual(
    session: Annotated[Session, Depends(get_db)],
    valor_sesion: Annotated[
        str | None,
        Cookie(alias=settings.session_cookie_name),
    ] = None,
) -> Usuario:
    """Reautentica la sesión y carga permisos y organización desde PostgreSQL."""

    credencial = leer_credencial_sesion(valor_sesion)
    usuario = (
        obtener_usuario_vigente(
            session,
            credencial.usuario_id,
            credencial.version_sesion,
        )
        if credencial is not None
        else None
    )
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión no es válida o expiró.",
        )
    return usuario


UsuarioActual = Annotated[Usuario, Depends(obtener_usuario_actual)]


def autenticar_websocket(
    websocket: WebSocket,
    session: Annotated[Session, Depends(get_db)],
    valor_sesion: Annotated[
        str | None,
        Cookie(alias=settings.session_cookie_name),
    ] = None,
) -> Usuario:
    """Reautentica el socket con cookie y rechaza orígenes no permitidos."""

    if websocket.headers.get("origin") not in settings.cors_origins:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    try:
        usuario = obtener_usuario_actual(session, valor_sesion)
    except HTTPException as error:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION) from error
    if usuario.requiere_cambio_password:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return usuario


UsuarioWebSocket = Annotated[Usuario, Depends(autenticar_websocket)]


def requerir_roles(
    *roles_permitidos: RolUsuario,
    permitir_cambio_password_pendiente: bool = False,
) -> Callable[[UsuarioActual], Usuario]:
    """Construye una dependencia que autoriza únicamente los roles indicados."""

    permitidos = frozenset(roles_permitidos)

    def autorizar(usuario: UsuarioActual) -> Usuario:
        if usuario.requiere_cambio_password and not permitir_cambio_password_pendiente:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Debés cambiar tu contraseña antes de continuar.",
            )
        if usuario.rol not in permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tenés permisos para realizar esta operación.",
            )
        return usuario

    return autorizar


def requerir_operacion(
    operacion: OperacionProtegida,
) -> Callable[[UsuarioActual], Usuario]:
    """Autoriza una operación de acuerdo con la matriz RBAC local."""

    return requerir_roles(
        *roles_habilitados_para(operacion),
        permitir_cambio_password_pendiente=operacion
        in {
            OperacionProtegida.CONSULTAR_SESION,
            OperacionProtegida.CERRAR_SESION,
            OperacionProtegida.CAMBIAR_PASSWORD,
        },
    )


UsuarioConsultaSesion = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.CONSULTAR_SESION)),
]
UsuarioCierreSesion = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.CERRAR_SESION)),
]
UsuarioCambioPassword = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.CAMBIAR_PASSWORD)),
]
UsuarioAdministrador = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.GESTIONAR_USUARIOS)),
]

UsuarioInventario = Annotated[
    Usuario, Depends(requerir_operacion(OperacionProtegida.GESTIONAR_INVENTARIO))
]


def obtener_cliente_nacional(request: Request) -> ClienteNacional:
    """Entrega el cliente nacional compartido durante el lifespan."""

    return request.app.state.cliente_nacional


ClienteNacionalDep = Annotated[ClienteNacional, Depends(obtener_cliente_nacional)]


def obtener_cliente_prioridad(request: Request) -> ClientePrioridad:
    """Entrega el cliente de priorización compartido durante el lifespan."""

    return request.app.state.cliente_prioridad


ClientePrioridadDep = Annotated[ClientePrioridad, Depends(obtener_cliente_prioridad)]


def validar_csrf(
    usuario: UsuarioActual,
    token_csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    """Exige un token CSRF vigente en operaciones autenticadas que cambian estado."""

    if not verificar_token_csrf(
        token_csrf,
        usuario.id,
        usuario.version_sesion,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El token CSRF no es válido.",
        )


def obtener_cliente_bonita(request: Request) -> ClienteBonita:
    """Entrega el cliente de Bonita creado durante el arranque de la aplicación."""

    cliente = getattr(request.app.state, "cliente_bonita", None)
    if isinstance(cliente, ClienteBonita):
        return cliente
    raise RuntimeError("El cliente de Bonita no fue inicializado en el lifespan.")


ClienteBonitaDep = Annotated[ClienteBonita, Depends(obtener_cliente_bonita)]


def obtener_cliente_email(request: Request) -> ClienteSMTP:
    """Entrega el adaptador SMTP configurado durante el arranque de la API."""

    cliente = getattr(request.app.state, "cliente_email", None)
    if isinstance(cliente, ClienteSMTP):
        return cliente
    raise RuntimeError("El cliente de correo no fue inicializado en el lifespan.")


ClienteEmailDep = Annotated[ClienteSMTP, Depends(obtener_cliente_email)]


def obtener_gestor_tiempo_real(request: Request) -> GestorTiempoReal:
    """Entrega el distribuidor WebSocket creado durante el arranque."""

    gestor = getattr(request.app.state, "gestor_tiempo_real", None)
    if isinstance(gestor, GestorTiempoReal):
        return gestor
    raise RuntimeError("El gestor de tiempo real no fue inicializado.")


GestorTiempoRealDep = Annotated[
    GestorTiempoReal,
    Depends(obtener_gestor_tiempo_real),
]


def validar_callback_bonita(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Autentica las llamadas que el proceso de Bonita hace a FastAPI.

    Compara en tiempo constante el token `Bearer` con `BONITA_CALLBACK_TOKEN`.
    """

    esperado = settings.bonita_callback_token
    if esperado is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Los callbacks de Bonita no están configurados.",
        )
    esquema, _, token = (authorization or "").partition(" ")
    if esquema.casefold() != "bearer" or not compare_digest(
        token.encode(), esperado.get_secret_value().encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token de Bonita no es válido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
