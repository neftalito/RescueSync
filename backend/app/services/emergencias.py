"""Caso de uso para registrar una emergencia municipal."""

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Emergencia,
    EstadoEmergencia,
    EstadoSincronizacionBonita,
    RolUsuario,
    TipoOrganizacion,
    Usuario,
)
from app.schemas.emergencia import EmergenciaCreate
from app.services.auth import organizacion_vigente_de_tipo
from app.services.notificaciones import notificar_emergencia_registrada


class EmergenciaError(Exception):
    """Fallo de dominio al registrar una emergencia con mensaje apto para la API."""


class MunicipioInvalidoError(EmergenciaError):
    """El usuario no conserva un municipio vigente para registrar la emergencia."""


class CentroInvalidoError(EmergenciaError):
    """El usuario no conserva un centro coordinador vigente para consultar emergencias."""


class EmergenciaNoEncontradaError(EmergenciaError):
    """La emergencia indicada no existe."""


class EmergenciaNoAutorizadaError(EmergenciaError):
    """La emergencia no pertenece al municipio del operador."""


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
        session.flush()
        notificar_emergencia_registrada(
            session,
            emergencia_id=emergencia.id,
            zona=emergencia.zona,
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DatosEmergenciaInvalidosError(
            "Los datos de la emergencia no son válidos."
        ) from error
    session.refresh(emergencia)
    return emergencia


def listar_emergencias(session: Session, usuario: Usuario) -> list[Emergencia]:
    """Filtra la bandeja de emergencias visible según el rol autenticado.

    Un municipio ve únicamente sus propias emergencias, con su estado actual.
    Un centro coordinador ve las emergencias en REGISTRADA que aún no tienen
    centro asignado o que ya están asignadas al suyo.

    Args:
        session: Sesión SQLAlchemy con la que se ejecuta la consulta.
        usuario: Operador municipal o coordinador regional vigente.

    Returns:
        Las emergencias visibles para ese usuario, ya ordenadas.

    Raises:
        MunicipioInvalidoError: Si un operador municipal no conserva un
            municipio activo.
        CentroInvalidoError: Si un coordinador no conserva un centro
            coordinador activo.
        EmergenciaError: Si el rol autenticado no tiene una bandeja definida.
    """

    if usuario.rol is RolUsuario.OPERADOR_MUNICIPAL:
        municipio = organizacion_vigente_de_tipo(usuario, TipoOrganizacion.MUNICIPIO)
        if municipio is None:
            raise MunicipioInvalidoError(
                "Solo un municipio activo puede consultar sus emergencias."
            )
        enunciado = (
            select(Emergencia)
            .where(Emergencia.municipio_id == municipio.id)
            .order_by(Emergencia.creada_en.desc())
        )
    elif usuario.rol is RolUsuario.COORDINADOR_REGIONAL:
        centro = organizacion_vigente_de_tipo(
            usuario, TipoOrganizacion.CENTRO_COORDINADOR
        )
        if centro is None:
            raise CentroInvalidoError(
                "Solo un centro coordinador activo puede consultar la bandeja."
            )
        enunciado = (
            select(Emergencia)
            .where(
                Emergencia.estado == EstadoEmergencia.REGISTRADA,
                or_(
                    Emergencia.centro_coordinador_id.is_(None),
                    Emergencia.centro_coordinador_id == centro.id,
                ),
            )
            .order_by(Emergencia.creada_en.asc())
        )
    else:
        raise EmergenciaError("El rol autenticado no tiene una bandeja de emergencias.")

    return list(session.scalars(enunciado).all())


def obtener_emergencia_para_reintento(
    session: Session,
    usuario: Usuario,
    emergencia_id: int,
) -> Emergencia:
    """Autoriza el reintento solo para el municipio dueño de la emergencia.

    Raises:
        MunicipioInvalidoError: Si el operador ya no pertenece a un municipio activo.
        EmergenciaNoEncontradaError: Si no existe la emergencia indicada.
        EmergenciaNoAutorizadaError: Si pertenece a otro municipio.
    """

    municipio = organizacion_vigente_de_tipo(usuario, TipoOrganizacion.MUNICIPIO)
    if municipio is None:
        raise MunicipioInvalidoError(
            "Solo un municipio activo puede reintentar la vinculación."
        )
    emergencia = session.get(Emergencia, emergencia_id)
    if emergencia is None:
        raise EmergenciaNoEncontradaError("La emergencia no existe.")
    if emergencia.municipio_id != municipio.id:
        raise EmergenciaNoAutorizadaError(
            "Solo el municipio que registró la emergencia puede reintentarla."
        )
    return emergencia
