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
    CONSULTAR_LOTES_PUBLICADOS = "CONSULTAR_LOTES_PUBLICADOS"
    PUBLICAR_CONVOCATORIA = "PUBLICAR_CONVOCATORIA"
    CONSULTAR_CONVOCATORIAS = "CONSULTAR_CONVOCATORIAS"
    PRESENTAR_OFERTA = "PRESENTAR_OFERTA"
    CONSULTAR_OFERTAS_PROPIAS = "CONSULTAR_OFERTAS_PROPIAS"
    GESTIONAR_INVENTARIO = "GESTIONAR_INVENTARIO"
    CONSULTAR_NOTIFICACIONES = "CONSULTAR_NOTIFICACIONES"
    MARCAR_NOTIFICACION_LEIDA = "MARCAR_NOTIFICACION_LEIDA"


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
            OperacionProtegida.CONSULTAR_LOTES_PUBLICADOS: frozenset(
                {RolUsuario.COORDINADOR_REGIONAL, RolUsuario.REPRESENTANTE_ONG}
            ),
            OperacionProtegida.PUBLICAR_CONVOCATORIA: frozenset(
                {RolUsuario.COORDINADOR_REGIONAL}
            ),
            OperacionProtegida.CONSULTAR_CONVOCATORIAS: frozenset(
                {RolUsuario.REPRESENTANTE_ONG}
            ),
            OperacionProtegida.PRESENTAR_OFERTA: frozenset(
                {RolUsuario.REPRESENTANTE_ONG}
            ),
            OperacionProtegida.CONSULTAR_OFERTAS_PROPIAS: frozenset(
                {RolUsuario.REPRESENTANTE_ONG}
            ),
            OperacionProtegida.GESTIONAR_INVENTARIO: frozenset(
                {RolUsuario.REPRESENTANTE_ONG}
            ),
            OperacionProtegida.CONSULTAR_NOTIFICACIONES: ROLES_AUTENTICADOS,
            OperacionProtegida.MARCAR_NOTIFICACION_LEIDA: ROLES_AUTENTICADOS,
        }
    )
)


def roles_habilitados_para(
    operacion: OperacionProtegida,
) -> frozenset[RolUsuario]:
    """Devuelve los roles autorizados para una operación local concreta."""

    return ROLES_POR_OPERACION[operacion]
