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
from app.services.auth import organizacion_vigente_de_tipo


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

    municipio = organizacion_vigente_de_tipo(usuario, TipoOrganizacion.MUNICIPIO)
    if municipio is None:
        raise MunicipioInvalidoError(
            "Solo un municipio activo puede registrar emergencias."
        )

    emergencia = Emergencia(
        municipio_id=municipio.id,
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
