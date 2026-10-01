from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import ClienteEmailDep, UsuarioAdministrador, validar_csrf
from app.db.models import Usuario
from app.db.session import get_db
from app.integrations.email.cliente import EmailNoDisponibleError
from app.schemas import ErrorResponse
from app.schemas.usuarios import (
    PasswordTemporalRequest,
    UsuarioCreate,
    UsuarioResponse,
    UsuarioUpdate,
)
from app.services.usuarios import (
    ContextoUsuarioInvalidoError,
    EmailDuplicadoError,
    ProteccionAdministradorError,
    UsuarioNoEncontradoError,
    actualizar_usuario,
    crear_usuario,
    desactivar_usuario,
    listar_usuarios,
    restablecer_password,
)

router = APIRouter()

RESPUESTAS_GESTION = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}


def _traducir_error(error: Exception) -> NoReturn:
    if isinstance(error, UsuarioNoEncontradoError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El usuario solicitado no existe.",
        ) from error
    if isinstance(error, EmailDuplicadoError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario con ese correo.",
        ) from error
    if isinstance(error, ProteccionAdministradorError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    if isinstance(error, ContextoUsuarioInvalidoError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    if isinstance(error, EmailNoDisponibleError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No pudimos enviar las credenciales. El usuario no fue creado; "
                "intentá nuevamente."
            ),
        ) from error
    raise error


@router.get(
    "",
    response_model=list[UsuarioResponse],
    summary="Listar usuarios",
    description="Devuelve cuentas activas e inactivas para su administración.",
)
def obtener_usuarios(
    _: UsuarioAdministrador,
    session: Annotated[Session, Depends(get_db)],
) -> list[Usuario]:
    return listar_usuarios(session)


@router.post(
    "",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    responses=RESPUESTAS_GESTION,
    summary="Crear un usuario",
    description=(
        "Genera una contraseña temporal, crea la cuenta y envía las credenciales "
        "al correo del usuario."
    ),
)
def alta_usuario(
    datos: UsuarioCreate,
    _: UsuarioAdministrador,
    session: Annotated[Session, Depends(get_db)],
    cliente_email: ClienteEmailDep,
    __: Annotated[None, Depends(validar_csrf)],
) -> Usuario:
    try:
        resultado = crear_usuario(session, datos)
        cliente_email.enviar_alta_usuario(
            resultado.usuario.email,
            resultado.password_temporal.get_secret_value(),
        )
        session.commit()
        return resultado.usuario
    except (
        ContextoUsuarioInvalidoError,
        EmailDuplicadoError,
        EmailNoDisponibleError,
    ) as error:
        session.rollback()
        _traducir_error(error)


@router.patch(
    "/{usuario_id}",
    response_model=UsuarioResponse,
    responses=RESPUESTAS_GESTION,
    summary="Editar un usuario",
    description="Modifica correo, rol, organización o estado de una cuenta.",
)
def editar_usuario(
    usuario_id: int,
    datos: UsuarioUpdate,
    administrador: UsuarioAdministrador,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(validar_csrf)],
) -> Usuario:
    try:
        usuario = actualizar_usuario(session, administrador, usuario_id, datos)
        session.commit()
        return usuario
    except (
        ContextoUsuarioInvalidoError,
        EmailDuplicadoError,
        ProteccionAdministradorError,
        UsuarioNoEncontradoError,
    ) as error:
        session.rollback()
        _traducir_error(error)


@router.delete(
    "/{usuario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=RESPUESTAS_GESTION,
    summary="Desactivar un usuario",
    description="Desactiva la cuenta y conserva toda su trazabilidad histórica.",
)
def baja_usuario(
    usuario_id: int,
    administrador: UsuarioAdministrador,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(validar_csrf)],
) -> Response:
    try:
        desactivar_usuario(session, administrador, usuario_id)
        session.commit()
    except (
        ProteccionAdministradorError,
        UsuarioNoEncontradoError,
    ) as error:
        session.rollback()
        _traducir_error(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{usuario_id}/password",
    response_model=UsuarioResponse,
    responses=RESPUESTAS_GESTION,
    summary="Restablecer la contraseña de un usuario",
    description=(
        "Asigna una contraseña temporal, invalida sus sesiones y exige cambiarla "
        "en el siguiente acceso."
    ),
)
def cambiar_password_usuario(
    usuario_id: int,
    datos: PasswordTemporalRequest,
    administrador: UsuarioAdministrador,
    session: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(validar_csrf)],
) -> Usuario:
    try:
        usuario = restablecer_password(
            session,
            administrador,
            usuario_id,
            datos.password.get_secret_value(),
        )
        session.commit()
        return usuario
    except (
        ProteccionAdministradorError,
        UsuarioNoEncontradoError,
    ) as error:
        session.rollback()
        _traducir_error(error)
