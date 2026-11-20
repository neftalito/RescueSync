from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Organizacion, TipoOrganizacion, Usuario
from app.schemas.organizaciones import OrganizacionCreate, OrganizacionUpdate
from app.schemas.paginacion import SIN_PAGINACION, Paginacion
from app.services.busqueda import contiene_texto


class OrganizacionDuplicadaError(ValueError):
    """Indica que ya existe una organización del mismo tipo y nombre."""


class OrganizacionNoEncontradaError(LookupError):
    """Indica que la organización solicitada no existe."""


class TipoOrganizacionEnUsoError(ValueError):
    """Impide cambiar el tipo mientras existan usuarios relacionados."""


def listar_organizaciones(
    session: Session,
    paginacion: Paginacion = SIN_PAGINACION,
    *,
    busqueda: str = "",
    tipo: TipoOrganizacion | None = None,
    activa: bool | None = None,
) -> list[Organizacion]:
    """Lista organizaciones activas e inactivas para su administración."""

    consulta = select(Organizacion)
    if busqueda:
        consulta = consulta.where(contiene_texto(Organizacion.nombre, busqueda))
    if tipo is not None:
        consulta = consulta.where(Organizacion.tipo == tipo)
    if activa is not None:
        consulta = consulta.where(Organizacion.activa == activa)
    consulta = (
        consulta.order_by(
            Organizacion.activa.desc(),
            Organizacion.tipo,
            Organizacion.nombre,
            Organizacion.id,
        )
        .offset(paginacion.offset)
        .limit(paginacion.limit)
    )
    return list(session.scalars(consulta))


def _validar_identidad_disponible(
    session: Session,
    tipo: TipoOrganizacion,
    nombre: str,
    organizacion_id: int | None = None,
) -> None:
    consulta = select(Organizacion.id).where(
        Organizacion.tipo == tipo,
        Organizacion.nombre == nombre,
    )
    if organizacion_id is not None:
        consulta = consulta.where(Organizacion.id != organizacion_id)
    if session.scalar(consulta) is not None:
        raise OrganizacionDuplicadaError


def _flush_identidad_segura(session: Session) -> None:
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as error:
        raise OrganizacionDuplicadaError from error


def _obtener_organizacion_bloqueada(
    session: Session,
    organizacion_id: int,
) -> Organizacion:
    organizacion = session.scalar(
        select(Organizacion).where(Organizacion.id == organizacion_id).with_for_update()
    )
    if organizacion is None:
        raise OrganizacionNoEncontradaError
    return organizacion


def _desactivar_usuarios_relacionados(
    session: Session,
    organizacion_id: int,
) -> None:
    usuarios = session.scalars(
        select(Usuario)
        .where(
            Usuario.organizacion_id == organizacion_id,
            Usuario.activo.is_(True),
        )
        .order_by(Usuario.id)
        .with_for_update()
    )
    for usuario in usuarios:
        usuario.activo = False
        usuario.version_sesion += 1


def crear_organizacion(
    session: Session,
    datos: OrganizacionCreate,
) -> Organizacion:
    """Crea una organización activa y rechaza identidades repetidas."""

    _validar_identidad_disponible(session, datos.tipo, datos.nombre)

    organizacion = Organizacion(tipo=datos.tipo, nombre=datos.nombre)
    session.add(organizacion)
    _flush_identidad_segura(session)
    return organizacion


def actualizar_organizacion(
    session: Session,
    organizacion_id: int,
    datos: OrganizacionUpdate,
) -> Organizacion:
    """Edita identidad o estado y mantiene consistentes las cuentas relacionadas."""

    organizacion = _obtener_organizacion_bloqueada(session, organizacion_id)
    campos = datos.model_fields_set
    nuevo_tipo = datos.tipo if "tipo" in campos else organizacion.tipo
    nuevo_nombre = datos.nombre if "nombre" in campos else organizacion.nombre
    nueva_activa = datos.activa if "activa" in campos else organizacion.activa
    assert nuevo_tipo is not None
    assert nuevo_nombre is not None
    assert nueva_activa is not None

    if nuevo_tipo is not organizacion.tipo:
        if organizacion.ong_nacional_id is not None:
            raise TipoOrganizacionEnUsoError
        usuario_relacionado = session.scalar(
            select(Usuario.id)
            .where(Usuario.organizacion_id == organizacion.id)
            .limit(1)
        )
        if usuario_relacionado is not None:
            raise TipoOrganizacionEnUsoError

    _validar_identidad_disponible(
        session,
        nuevo_tipo,
        nuevo_nombre,
        organizacion.id,
    )
    if organizacion.activa and not nueva_activa:
        _desactivar_usuarios_relacionados(session, organizacion.id)
    organizacion.tipo = nuevo_tipo
    organizacion.nombre = nuevo_nombre
    organizacion.activa = nueva_activa
    _flush_identidad_segura(session)
    return organizacion


def desactivar_organizacion(session: Session, organizacion_id: int) -> None:
    """Da de baja la organización y todas sus cuentas activas sin borrar datos."""

    actualizar_organizacion(
        session,
        organizacion_id,
        OrganizacionUpdate(activa=False),
    )
