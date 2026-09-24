from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from app.db.models.enums import RolUsuario


class OperacionProtegida(StrEnum):
    """Identifica las operaciones locales alcanzadas por la matriz RBAC."""

    CONSULTAR_SESION = "CONSULTAR_SESION"
    CERRAR_SESION = "CERRAR_SESION"
    CAMBIAR_PASSWORD = "CAMBIAR_PASSWORD"
    GESTIONAR_USUARIOS = "GESTIONAR_USUARIOS"
    REGISTRAR_EMERGENCIA = "REGISTRAR_EMERGENCIA"
    CONSULTAR_EMERGENCIAS = "CONSULTAR_EMERGENCIAS"
    GESTIONAR_LOTES = "GESTIONAR_LOTES"
    PRESENTAR_OFERTA = "PRESENTAR_OFERTA"


ROLES_AUTENTICADOS: frozenset[RolUsuario] = frozenset(RolUsuario)

ROLES_POR_OPERACION: Mapping[OperacionProtegida, frozenset[RolUsuario]] = (
    MappingProxyType(
        {
            OperacionProtegida.CONSULTAR_SESION: ROLES_AUTENTICADOS,
            OperacionProtegida.CERRAR_SESION: ROLES_AUTENTICADOS,
            OperacionProtegida.CAMBIAR_PASSWORD: ROLES_AUTENTICADOS,
            OperacionProtegida.GESTIONAR_USUARIOS: frozenset(
                {RolUsuario.ADMINISTRADOR}
            ),
            OperacionProtegida.REGISTRAR_EMERGENCIA: frozenset(
                {RolUsuario.OPERADOR_MUNICIPAL}
            ),
            OperacionProtegida.CONSULTAR_EMERGENCIAS: frozenset(
                {RolUsuario.OPERADOR_MUNICIPAL, RolUsuario.COORDINADOR_REGIONAL}
            ),
            OperacionProtegida.GESTIONAR_LOTES: frozenset(
                {RolUsuario.COORDINADOR_REGIONAL}
            ),
            OperacionProtegida.PRESENTAR_OFERTA: frozenset(
                {RolUsuario.REPRESENTANTE_ONG}
            ),
        }
    )
)


def roles_habilitados_para(
    operacion: OperacionProtegida,
) -> frozenset[RolUsuario]:
    """Devuelve los roles autorizados para una operación local concreta."""

    return ROLES_POR_OPERACION[operacion]
