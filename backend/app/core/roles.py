from collections.abc import Mapping
from types import MappingProxyType

from app.db.models.enums import RolUsuario, TipoOrganizacion

TIPO_ORGANIZACION_POR_ROL: Mapping[RolUsuario, TipoOrganizacion] = MappingProxyType(
    {
        RolUsuario.OPERADOR_MUNICIPAL: TipoOrganizacion.MUNICIPIO,
        RolUsuario.COORDINADOR_REGIONAL: TipoOrganizacion.CENTRO_COORDINADOR,
        RolUsuario.REPRESENTANTE_ONG: TipoOrganizacion.ONG,
    }
)
"""Relaciona cada rol operativo con el tipo de organización que exige."""
