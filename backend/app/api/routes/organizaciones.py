from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import UsuarioAdministrador, validar_csrf
from app.db.models import Organizacion
from app.db.session import get_db
from app.schemas import ErrorResponse
from app.schemas.organizaciones import (
    OrganizacionCreate,
    OrganizacionResponse,
    OrganizacionUpdate,
)
from app.services.organizaciones import (
    OrganizacionDuplicadaError,
    OrganizacionNoEncontradaError,
    TipoOrganizacionEnUsoError,
    actualizar_organizacion,
    crear_organizacion,
    desactivar_organizacion,
    listar_organizaciones,
)

router = APIRouter()


@router.get(
    "",
    response_model=list[OrganizacionResponse],
    summary="Listar organizaciones",
    description=(
        "Devuelve municipios, centros coordinadores y ONG activas e inactivas "
        "para su administración."
    ),
)
def obtener_organizaciones(
    _: UsuarioAdministrador,
    session: Annotated[Session, Depends(get_db)],
) -> list[Organizacion]:
    return listar_organizaciones(session)


@router.post(
    "",
    response_model=OrganizacionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
    summary="Crear una organización",
    description=(
        "Registra una organización activa para luego asignarla a usuarios "
        "municipales, coordinadores o representantes de ONG."
    ),
)
def alta_organizacion(
    datos: OrganizacionCreate,
    _: UsuarioAdministrador,
    session: Annotated[Session, Depends(get_db)],
    __: Annotated[None, Depends(validar_csrf)],
) -> Organizacion:
    try:
        organizacion = crear_organizacion(session, datos)
        session.commit()
        return organizacion
    except OrganizacionDuplicadaError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una organización de ese tipo con el mismo nombre.",
        ) from error


@router.patch(
    "/{organizacion_id}",
    response_model=OrganizacionResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
    summary="Editar una organización",
    description=(
        "Modifica nombre, tipo o estado. Una baja también desactiva las cuentas "
        "relacionadas; una recuperación no las reactiva automáticamente."
    ),
)
def editar_organizacion(
    organizacion_id: int,
    datos: OrganizacionUpdate,
    _: UsuarioAdministrador,
    session: Annotated[Session, Depends(get_db)],
    __: Annotated[None, Depends(validar_csrf)],
) -> Organizacion:
    try:
        organizacion = actualizar_organizacion(session, organizacion_id, datos)
        session.commit()
        return organizacion
    except OrganizacionNoEncontradaError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La organización solicitada no existe.",
        ) from error
    except OrganizacionDuplicadaError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una organización de ese tipo con el mismo nombre.",
        ) from error
    except TipoOrganizacionEnUsoError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No se puede cambiar el tipo de una organización que tiene "
                "usuarios relacionados o una vinculación nacional."
            ),
        ) from error


@router.delete(
    "/{organizacion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
    summary="Eliminar lógicamente una organización",
    description=(
        "Realiza una baja lógica y desactiva todas las cuentas activas "
        "relacionadas, conservando su trazabilidad."
    ),
)
def baja_organizacion(
    organizacion_id: int,
    _: UsuarioAdministrador,
    session: Annotated[Session, Depends(get_db)],
    __: Annotated[None, Depends(validar_csrf)],
) -> Response:
    try:
        desactivar_organizacion(session, organizacion_id)
        session.commit()
    except OrganizacionNoEncontradaError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La organización solicitada no existe.",
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
