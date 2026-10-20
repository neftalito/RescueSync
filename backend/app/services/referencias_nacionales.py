"""Consulta referencias antes de adquirir locks; nunca replica stock nacional."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Usuario
from app.integrations.nacional.cliente import ClienteNacional, ErrorNacional
from app.schemas.inventario import CapacidadResponse, ConexionRequest, RecursoResponse
from app.schemas.lote import LoteItem
from app.schemas.oferta import OfertaContenidoRequest
from app.services.acceso_nacional import ejecutar_nacional


def token_catalogo(cliente: ClienteNacional, *, administrar: bool = False) -> str:
    """Autentica la cuenta del catálogo y exige su rol nacional vigente."""
    settings = get_settings()
    if (
        not settings.nacional_catalogo_login
        or settings.nacional_catalogo_password is None
    ):
        raise ErrorNacional(
            503, "El catálogo nacional para coordinación no está configurado."
        )
    token = cliente.login(
        ConexionRequest(
            identificador_login=settings.nacional_catalogo_login,
            password=settings.nacional_catalogo_password,
        )
    ).access_token.get_secret_value()
    rol = cliente.cuenta(token).rol
    if rol not in {"INTEGRACION", "ADMIN_NACIONAL"}:
        raise ErrorNacional(403, "El catálogo requiere una cuenta técnica autorizada.")
    if administrar and rol != "ADMIN_NACIONAL":
        raise ErrorNacional(
            403,
            "Para crear capacidades, la cuenta del catálogo debe tener rol ADMIN_NACIONAL.",
        )
    return token


def catalogo_tecnico(cliente: ClienteNacional) -> list[CapacidadResponse]:
    """Usa una cuenta técnica configurada en el servidor, nunca un token de ONG."""
    return cliente.capacidades(token_catalogo(cliente))


def capacidades_para_lotes(
    cliente: ClienteNacional, items: list[LoteItem]
) -> dict[UUID, CapacidadResponse]:
    ids = {
        i.capacidad_nacional_id for i in items if i.capacidad_nacional_id is not None
    }
    if not ids:
        return {}
    capacidades = {c.id: c for c in catalogo_tecnico(cliente)}
    if not ids <= capacidades.keys():
        raise ErrorNacional(422, "Una capacidad nacional no existe o está inactiva.")
    for item in items:
        if item.capacidad_nacional_id is None:
            continue
        capacidad = capacidades[item.capacidad_nacional_id]
        if item.unidad != capacidad.unidad or (
            not capacidad.admite_fracciones
            and item.cantidad_requerida != item.cantidad_requerida.to_integral_value()
        ):
            raise ErrorNacional(
                422, "La cantidad y unidad deben coincidir con la capacidad elegida."
            )
    return capacidades


def recursos_para_oferta(
    session: Session,
    usuario: Usuario,
    cliente: ClienteNacional,
    datos: OfertaContenidoRequest,
) -> tuple[UUID | None, dict[UUID, RecursoResponse]]:
    ids = {a.recurso_nacional_id for item in datos.items for a in item.aportes}
    if not ids:
        return None, {}

    def consultar(
        ong_id: UUID, token: str
    ) -> tuple[UUID, list[RecursoResponse], list[CapacidadResponse]]:
        return ong_id, cliente.recursos(token, ong_id), cliente.capacidades(token)

    ong_id, recursos, catalogo = ejecutar_nacional(session, usuario, cliente, consultar)
    capacidades = {c.id: c for c in catalogo}
    if any(r.ong_id != ong_id for r in recursos):
        raise ErrorNacional(502, "El inventario nacional contiene otra ONG.")
    seleccionados = {
        r.id: r for r in recursos if r.activo and r.capacidad_id in capacidades
    }
    if any(
        r.unidad != capacidades[r.capacidad_id].unidad
        or r.admite_fracciones != capacidades[r.capacidad_id].admite_fracciones
        for r in seleccionados.values()
    ):
        raise ErrorNacional(502, "El inventario no coincide con el catálogo nacional.")
    if not ids <= seleccionados.keys():
        raise ErrorNacional(
            422, "Un recurso no existe o no pertenece a tu inventario activo."
        )
    return ong_id, seleccionados
