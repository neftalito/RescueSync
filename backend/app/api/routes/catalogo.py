"""Adapta el catálogo nacional para administradores locales autorizados."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.dependencies import ClienteNacionalDep, requerir_operacion, validar_csrf
from app.core.permissions import OperacionProtegida
from app.db.models import Usuario
from app.integrations.nacional.cliente import ClienteNacional, ErrorNacional
from app.schemas import ErrorResponse
from app.schemas.catalogo import CapacidadCreate, UnidadResponse
from app.schemas.inventario import CapacidadResponse
from app.services.referencias_nacionales import token_catalogo

router = APIRouter()
UsuarioCatalogo = Annotated[
    Usuario, Depends(requerir_operacion(OperacionProtegida.GESTIONAR_CATALOGO_NACIONAL))
]
ERRORES = {
    codigo: {"model": ErrorResponse} for codigo in (401, 403, 409, 422, 502, 503, 504)
}


def _consultar[T](
    cliente: ClienteNacional,
    response: Response,
    operacion: Callable[[str], T],
    *,
    administrar: bool = False,
) -> T:
    """Usa sólo credenciales del servidor y traduce errores nacionales seguros."""
    response.headers["Cache-Control"] = "no-store"
    try:
        return operacion(token_catalogo(cliente, administrar=administrar))
    except ErrorNacional as error:
        raise HTTPException(error.status, str(error)) from error


@router.get(
    "/capacidades",
    response_model=list[CapacidadResponse],
    responses=ERRORES,
    summary="Consultar el catálogo nacional para administración",
)
def capacidades(
    _: UsuarioCatalogo,
    cliente: ClienteNacionalDep,
    response: Response,
) -> list[CapacidadResponse]:
    return _consultar(cliente, response, cliente.capacidades)


@router.get(
    "/unidades",
    response_model=list[UnidadResponse],
    responses=ERRORES,
    summary="Consultar las unidades nacionales predefinidas",
)
def unidades(
    _: UsuarioCatalogo,
    cliente: ClienteNacionalDep,
    response: Response,
) -> list[UnidadResponse]:
    return _consultar(cliente, response, cliente.unidades)


@router.post(
    "/capacidades",
    response_model=CapacidadResponse,
    status_code=201,
    responses=ERRORES,
    summary="Crear una capacidad en el catálogo nacional",
    description="Exige administrador local, CSRF vigente y cuenta nacional ADMIN_NACIONAL.",
)
def alta_capacidad(
    datos: CapacidadCreate,
    _: UsuarioCatalogo,
    cliente: ClienteNacionalDep,
    response: Response,
    __: Annotated[None, Depends(validar_csrf)],
) -> CapacidadResponse:
    return _consultar(
        cliente,
        response,
        lambda token: cliente.crear_capacidad(token, datos),
        administrar=True,
    )
