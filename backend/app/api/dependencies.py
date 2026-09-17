from collections.abc import Callable
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import OperacionProtegida, roles_habilitados_para
from app.core.security import leer_usuario_id_sesion, verificar_token_csrf
from app.db.models import RolUsuario, Usuario
from app.db.session import get_db
from app.integrations.bonita.cliente import ClienteBonita
from app.services.auth import obtener_usuario_vigente

settings = get_settings()


def obtener_usuario_actual(
    session: Annotated[Session, Depends(get_db)],
    valor_sesion: Annotated[
        str | None,
        Cookie(alias=settings.session_cookie_name),
    ] = None,
) -> Usuario:
    """Reautentica la sesión y carga permisos y organización desde PostgreSQL."""

    usuario_id = leer_usuario_id_sesion(valor_sesion)
    usuario = (
        obtener_usuario_vigente(session, usuario_id) if usuario_id is not None else None
    )
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión no es válida o expiró.",
        )
    return usuario


UsuarioActual = Annotated[Usuario, Depends(obtener_usuario_actual)]


def requerir_roles(*roles_permitidos: RolUsuario) -> Callable[[UsuarioActual], Usuario]:
    """Construye una dependencia que autoriza únicamente los roles indicados."""

    permitidos = frozenset(roles_permitidos)

    def autorizar(usuario: UsuarioActual) -> Usuario:
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

    return requerir_roles(*roles_habilitados_para(operacion))


UsuarioConsultaSesion = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.CONSULTAR_SESION)),
]
UsuarioCierreSesion = Annotated[
    Usuario,
    Depends(requerir_operacion(OperacionProtegida.CERRAR_SESION)),
]


def validar_csrf(
    usuario: UsuarioCierreSesion,
    token_csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    """Exige un token CSRF vigente en operaciones autenticadas que cambian estado."""

    if not verificar_token_csrf(token_csrf, usuario.id):
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
