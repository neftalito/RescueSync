"""Adaptador autenticado del inventario nacional para el navegador local."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.dependencies import (
    ClienteNacionalDep,
    UsuarioAdministrador,
    UsuarioInventario,
    validar_csrf,
)
from app.db.models import Organizacion
from app.db.session import get_db
from app.integrations.nacional.cliente import ErrorNacional
from app.schemas.certificaciones import (
    CertificacionesOngResponse,
    CertificacionResponse,
)
from app.schemas.errors import ErrorResponse
from app.schemas.inventario import (
    CapacidadResponse,
    EstadoConexion,
    OngNacionalResponse,
    RecursoCreate,
    RecursoResponse,
    RecursoUpdate,
    RegistroNacionalRequest,
    VinculoRequest,
)
from app.schemas.organizaciones import OrganizacionResponse
from app.services.acceso_nacional import ejecutar_nacional
from app.services.inventario import (
    estado_conexion,
    registrar_ong_nacional,
    vincular_ong,
)

router = APIRouter()
router_admin = APIRouter()
Db = Annotated[Session, Depends(get_db)]
errores = {
    codigo: {"model": ErrorResponse}
    for codigo in (401, 403, 404, 409, 422, 502, 503, 504)
}


def _ejecutar[T](session: Session, operacion: Callable[[], T]) -> T:
    try:
        return operacion()
    except ErrorNacional as error:
        raise HTTPException(error.status, str(error)) from error


def _remoto[T](
    session: Session,
    usuario: UsuarioInventario,
    cliente: ClienteNacionalDep,
    operacion: Callable[[UUID, str], T],
    *,
    escritura: bool = False,
    accion: str,
) -> T:
    return _ejecutar(
        session,
        lambda: ejecutar_nacional(
            session, usuario, cliente, operacion, escritura=escritura, accion=accion
        ),
    )


@router.get(
    "/conexion",
    response_model=EstadoConexion,
    responses=errores,
    summary="Consultar conexión de la ONG al Sistema Nacional",
)
def estado(
    usuario: UsuarioInventario, session: Db, response: Response
) -> EstadoConexion:
    response.headers["Cache-Control"] = "no-store"
    return _ejecutar(session, lambda: estado_conexion(session, usuario))


@router.post(
    "/registro-nacional",
    response_model=OngNacionalResponse,
    status_code=201,
    responses=errores,
    summary="Registrar mi ONG y su cuenta nacional",
    description=(
        "Crea una ONG PENDIENTE usando el nombre local. "
        "Un administrador debe verificar y guardar luego el vínculo por UUID."
    ),
    dependencies=[Depends(validar_csrf)],
)
def registro_nacional(
    datos: RegistroNacionalRequest,
    usuario: UsuarioInventario,
    session: Db,
    cliente: ClienteNacionalDep,
    response: Response,
) -> OngNacionalResponse:
    response.headers["Cache-Control"] = "no-store"
    return _ejecutar(session, lambda: registrar_ong_nacional(usuario, cliente, datos))


@router.get(
    "/capacidades",
    response_model=list[CapacidadResponse],
    responses=errores,
    summary="Consultar capacidades nacionales",
)
def capacidades(
    usuario: UsuarioInventario, session: Db, cliente: ClienteNacionalDep
) -> list[CapacidadResponse]:
    return _remoto(
        session,
        usuario,
        cliente,
        lambda _ong, token: cliente.capacidades(token),
        accion="consultar capacidades",
    )


@router.get(
    "/catalogo-certificaciones",
    response_model=list[CertificacionResponse],
    responses=errores,
    summary="Consultar catálogo nacional de certificaciones",
    description="Catálogo de referencia; no significa que tu ONG esté acreditada.",
)
def catalogo_certificaciones(
    usuario: UsuarioInventario,
    session: Db,
    cliente: ClienteNacionalDep,
    response: Response,
) -> list[CertificacionResponse]:
    response.headers["Cache-Control"] = "no-store"
    return _remoto(
        session,
        usuario,
        cliente,
        lambda _ong, token: cliente.certificaciones(token),
        accion="consultar catálogo de certificaciones",
    )


@router.get(
    "/certificaciones",
    response_model=CertificacionesOngResponse,
    responses=errores,
    summary="Consultar las acreditaciones de mi ONG",
    description="La ONG se obtiene del usuario y del vínculo verificado, sin recibir IDs del navegador.",
)
def certificaciones(
    usuario: UsuarioInventario,
    session: Db,
    cliente: ClienteNacionalDep,
    response: Response,
) -> CertificacionesOngResponse:
    response.headers["Cache-Control"] = "no-store"
    return _remoto(
        session,
        usuario,
        cliente,
        lambda ong, token: cliente.certificaciones_ong(token, ong),
        accion="consultar certificaciones",
    )


@router.get(
    "/recursos",
    response_model=list[RecursoResponse],
    responses=errores,
    summary="Consultar los recursos de mi ONG",
)
def recursos(
    usuario: UsuarioInventario, session: Db, cliente: ClienteNacionalDep
) -> list[RecursoResponse]:
    return _remoto(
        session,
        usuario,
        cliente,
        lambda ong, token: cliente.recursos(token, ong),
        accion="consultar recursos",
    )


@router.post(
    "/recursos",
    response_model=RecursoResponse,
    status_code=201,
    responses=errores,
    summary="Registrar un recurso nacional propio",
    dependencies=[Depends(validar_csrf)],
)
def crear(
    datos: RecursoCreate,
    usuario: UsuarioInventario,
    session: Db,
    cliente: ClienteNacionalDep,
) -> RecursoResponse:
    return _remoto(
        session,
        usuario,
        cliente,
        lambda ong, token: cliente.crear(token, ong, datos),
        escritura=True,
        accion="crear recurso",
    )


@router.patch(
    "/recursos/{recurso_id}",
    response_model=RecursoResponse,
    responses=errores,
    summary="Actualizar el total de un recurso propio",
    dependencies=[Depends(validar_csrf)],
)
def actualizar(
    recurso_id: UUID,
    datos: RecursoUpdate,
    usuario: UsuarioInventario,
    session: Db,
    cliente: ClienteNacionalDep,
) -> RecursoResponse:
    return _remoto(
        session,
        usuario,
        cliente,
        lambda ong, token: cliente.actualizar(token, ong, recurso_id, datos),
        escritura=True,
        accion="editar recurso",
    )


@router_admin.patch(
    "/{organizacion_id}/vinculo-nacional",
    response_model=OrganizacionResponse,
    responses=errores,
    summary="Vincular una ONG local por UUID nacional",
    dependencies=[Depends(validar_csrf)],
)
def vinculo(
    organizacion_id: int, datos: VinculoRequest, _: UsuarioAdministrador, session: Db
) -> Organizacion:
    return _ejecutar(
        session, lambda: vincular_ong(session, organizacion_id, datos.ong_nacional_id)
    )
