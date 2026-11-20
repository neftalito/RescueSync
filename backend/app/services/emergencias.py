"""Caso de uso para registrar una emergencia municipal."""

from collections.abc import Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Emergencia,
    EstadoEmergencia,
    EstadoSincronizacionBonita,
    Lote,
    RolUsuario,
    TipoOrganizacion,
    Usuario,
)
from app.schemas.emergencia import EmergenciaCreate
from app.schemas.paginacion import SIN_PAGINACION, Paginacion
from app.services.auth import organizacion_vigente_de_tipo
from app.services.busqueda import coincide_numero, contiene_texto
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
    *,
    prioridad: int | None = None,
) -> Emergencia:
    """Persiste una emergencia en estado REGISTRADA para el municipio autenticado.

    Args:
        session: Sesión SQLAlchemy con la que se confirma la transacción.
        usuario: Operador municipal vigente cargado desde PostgreSQL.
        datos: Gravedad, zona y descripción ya validadas por Pydantic.
        prioridad: Puntuación verificada por el flujo de alta.

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
        prioridad=prioridad,
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


def listar_emergencias(
    session: Session,
    usuario: Usuario,
    paginacion: Paginacion = SIN_PAGINACION,
    *,
    tiene_lotes: bool | None = None,
    estado: EstadoEmergencia | None = None,
    busqueda: str = "",
) -> list[Emergencia]:
    """Filtra la bandeja de emergencias visible según el rol autenticado.

    Un municipio ve únicamente sus propias emergencias, con su estado actual.
    Un centro coordinador ve las emergencias en REGISTRADA aún sin asignar
    y todas las asignadas a su centro, cualquiera sea su estado.

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
            .order_by(Emergencia.creada_en.desc(), Emergencia.id.desc())
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
                or_(
                    and_(
                        Emergencia.estado == EstadoEmergencia.REGISTRADA,
                        Emergencia.centro_coordinador_id.is_(None),
                    ),
                    Emergencia.centro_coordinador_id == centro.id,
                ),
            )
            .order_by(Emergencia.creada_en.asc(), Emergencia.id.asc())
        )
    else:
        raise EmergenciaError("El rol autenticado no tiene una bandeja de emergencias.")

    if busqueda:
        enunciado = enunciado.where(
            or_(
                coincide_numero(Emergencia.id, busqueda),
                contiene_texto(Emergencia.descripcion, busqueda),
            )
        )
    if estado is not None:
        enunciado = enunciado.where(Emergencia.estado == estado)
    if tiene_lotes is not None:
        existen_lotes = (
            select(Lote.id).where(Lote.emergencia_id == Emergencia.id).exists()
        )
        enunciado = enunciado.where(existen_lotes if tiene_lotes else ~existen_lotes)
    return list(
        session.scalars(
            enunciado.offset(paginacion.offset).limit(paginacion.limit)
        ).all()
    )


def ids_emergencias_con_lotes(
    session: Session, emergencias: Sequence[Emergencia]
) -> set[int]:
    """Consulta en bloque qué emergencias visibles tienen al menos un lote."""

    if not emergencias:
        return set()
    return set(
        session.scalars(
            select(Lote.emergencia_id)
            .where(
                Lote.emergencia_id.in_([emergencia.id for emergencia in emergencias])
            )
            .distinct()
        ).all()
    )


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
