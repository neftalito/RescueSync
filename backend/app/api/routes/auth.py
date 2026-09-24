from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    UsuarioCambioPassword,
    UsuarioConsultaSesion,
    validar_csrf,
)
from app.core.config import get_settings
from app.core.security import crear_token_csrf, crear_valor_sesion
from app.db.models import Usuario
from app.db.session import get_db
from app.schemas import (
    CambioPasswordRequest,
    ErrorResponse,
    LoginRequest,
    SesionResponse,
    UsuarioSesion,
)
from app.services.auth import (
    PasswordActualIncorrectaError,
    PasswordSinCambiosError,
    autenticar_usuario,
    cambiar_password_propia,
)

router = APIRouter()
settings = get_settings()

RESPUESTA_NO_AUTORIZADA = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
}


def _crear_respuesta_sesion(usuario: Usuario) -> SesionResponse:
    return SesionResponse(
        usuario=UsuarioSesion.model_validate(usuario),
        csrf_token=crear_token_csrf(usuario.id, usuario.version_sesion),
    )


def _establecer_cookie_sesion(response: Response, usuario: Usuario) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=crear_valor_sesion(usuario.id, usuario.version_sesion),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.cookies_seguras,
        samesite=settings.session_cookie_samesite,
        path=settings.api_v1_prefix,
    )


def _evitar_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.post(
    "/login",
    response_model=SesionResponse,
    responses=RESPUESTA_NO_AUTORIZADA,
    summary="Iniciar sesión local",
    description=(
        "Valida las credenciales locales y crea una sesión firmada en una cookie "
        "HttpOnly. No utiliza el JWT del futuro Sistema Nacional."
    ),
)
def iniciar_sesion(
    datos: LoginRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
) -> SesionResponse:
    usuario = autenticar_usuario(
        session,
        str(datos.email),
        datos.password.get_secret_value(),
    )
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El correo o la contraseña son incorrectos.",
        )

    _establecer_cookie_sesion(response, usuario)
    _evitar_cache(response)
    return _crear_respuesta_sesion(usuario)


@router.get(
    "/me",
    response_model=SesionResponse,
    responses=RESPUESTA_NO_AUTORIZADA,
    summary="Consultar la sesión local",
    description=(
        "Carga nuevamente el usuario, su rol y su organización desde PostgreSQL "
        "para no confiar en permisos almacenados en el navegador."
    ),
)
def consultar_sesion(
    usuario: UsuarioConsultaSesion,
    response: Response,
) -> SesionResponse:
    _evitar_cache(response)
    return _crear_respuesta_sesion(usuario)


@router.post(
    "/password",
    response_model=SesionResponse,
    responses={
        **RESPUESTA_NO_AUTORIZADA,
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
    summary="Cambiar la contraseña propia",
    description=(
        "Valida la contraseña vigente, reemplaza el hash Argon2 e invalida "
        "cualquier otra sesión del usuario."
    ),
)
def cambiar_password(
    datos: CambioPasswordRequest,
    response: Response,
    usuario: UsuarioCambioPassword,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(validar_csrf)],
) -> SesionResponse:
    try:
        usuario = cambiar_password_propia(
            session,
            usuario,
            datos.password_actual.get_secret_value(),
            datos.password_nueva.get_secret_value(),
        )
        session.commit()
    except PasswordActualIncorrectaError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual es incorrecta.",
        ) from error
    except PasswordSinCambiosError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña nueva debe ser diferente de la actual.",
        ) from error

    _establecer_cookie_sesion(response, usuario)
    _evitar_cache(response)
    return _crear_respuesta_sesion(usuario)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **RESPUESTA_NO_AUTORIZADA,
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
    summary="Cerrar la sesión local",
    description="Valida el token CSRF y elimina la cookie de sesión del navegador.",
)
def cerrar_sesion(
    response: Response,
    _: Annotated[None, Depends(validar_csrf)],
) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.cookies_seguras,
        samesite=settings.session_cookie_samesite,
        path=settings.api_v1_prefix,
    )
    _evitar_cache(response)
