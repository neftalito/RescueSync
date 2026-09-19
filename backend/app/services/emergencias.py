"""Caso de uso para registrar una emergencia municipal."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Emergencia,
    EstadoEmergencia,
    EstadoSincronizacionBonita,
    TipoOrganizacion,
    Usuario,
)
from app.schemas.emergencia import EmergenciaCreate


class EmergenciaError(Exception):
    """Fallo de dominio al registrar una emergencia con mensaje apto para la API."""


class MunicipioInvalidoError(EmergenciaError):
    """El usuario no conserva un municipio vigente para registrar la emergencia."""


class DatosEmergenciaInvalidosError(EmergenciaError):
    """La base rechazó los datos aunque Pydantic los haya aceptado."""


def registrar_emergencia(
    session: Session,
    usuario: Usuario,
    datos: EmergenciaCreate,
) -> Emergencia:
    """Persiste una emergencia en estado REGISTRADA para el municipio autenticado.

    Args:
        session: Sesión SQLAlchemy con la que se confirma la transacción.
        usuario: Operador municipal vigente cargado desde PostgreSQL.
        datos: Gravedad, zona y descripción ya validadas por Pydantic.

    Returns:
        La emergencia persistida con sincronización Bonita en PENDIENTE.

    Raises:
        MunicipioInvalidoError: Si el usuario no conserva un municipio activo.
        DatosEmergenciaInvalidosError: Si la base rechaza la inserción.
    """

    organizacion = usuario.organizacion
    if (
        usuario.organizacion_id is None
        or organizacion is None
        or organizacion.tipo is not TipoOrganizacion.MUNICIPIO
        or not organizacion.activa
    ):
        raise MunicipioInvalidoError(
            "Solo un municipio activo puede registrar emergencias."
        )

    emergencia = Emergencia(
        municipio_id=usuario.organizacion_id,
        creada_por_usuario_id=usuario.id,
        gravedad=datos.gravedad,
        zona=datos.zona,
        descripcion=datos.descripcion,
        estado=EstadoEmergencia.REGISTRADA,
        bonita_sync=EstadoSincronizacionBonita.PENDIENTE,
    )
    session.add(emergencia)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DatosEmergenciaInvalidosError(
            "Los datos de la emergencia no son válidos."
        ) from error
    session.refresh(emergencia)
    return emergencia
