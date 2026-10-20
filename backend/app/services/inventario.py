"""Vinculación y conexión nacional sin duplicar inventario en la base local."""

from datetime import UTC, datetime
from uuid import UUID

from cryptography.fernet import InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AccesoNacional, Organizacion, TipoOrganizacion, Usuario
from app.db.models.aprovisionamiento import AprovisionamientoNacional
from app.integrations.nacional.cliente import ClienteNacional, ErrorNacional
from app.schemas.inventario import (
    EstadoConexion,
    OngNacionalResponse,
    RegistroNacionalRequest,
)
from app.services.acceso_nacional import cifrador
from app.services.aprovisionamiento_nacional import completar_alta, preparar_alta


def _ong(usuario: Usuario) -> Organizacion:
    ong = usuario.organizacion
    if ong is None or ong.tipo != TipoOrganizacion.ONG or not ong.activa:
        raise ErrorNacional(
            403, "Necesitás una ONG local activa para gestionar recursos."
        )
    return ong


def registrar_ong_nacional(
    session: Session,
    usuario: Usuario,
    cliente: ClienteNacional,
    datos: RegistroNacionalRequest,
) -> OngNacionalResponse:
    """Registra y vincula la ONG propia con su acceso técnico automático."""
    ong = _ong(usuario)
    if ong.ong_nacional_id is not None:
        raise ErrorNacional(409, "Tu ONG ya tiene un registro nacional vinculado.")
    preparar_alta(session, ong, datos)
    organizacion_id = ong.id
    session.commit()
    resultado = completar_alta(session, organizacion_id, cliente)
    assert resultado.ong_nacional_id is not None
    return OngNacionalResponse(
        id=resultado.ong_nacional_id, nombre=resultado.nombre, estado="PENDIENTE"
    )


def estado_conexion(session: Session, usuario: Usuario) -> EstadoConexion:
    """Consulta configuración sin exigir un token vigente ni llamar al nacional."""
    ong = _ong(usuario)
    acceso = session.get(AccesoNacional, ong.id, populate_existing=True)
    configurada = acceso is not None and acceso.ong_id == ong.ong_nacional_id
    estado = "SIN_CONFIGURAR"
    if configurada and acceso is not None:
        estado = "REQUIERE_REVISION" if acceso.requiere_revision else "LISTA"
        try:
            cifrador().decrypt(acceso.secreto_cifrado.encode())
        except (InvalidToken, ErrorNacional):
            estado = "REQUIERE_REVISION"
    return EstadoConexion(
        vinculada=ong.ong_nacional_id is not None,
        conectada=bool(
            configurada
            and acceso is not None
            and acceso.token_cifrado
            and acceso.expira_en
            and acceso.expira_en > datetime.now(UTC)
            and estado == "LISTA"
        ),
        ong_id=ong.ong_nacional_id,
        expira_en=acceso.expira_en if configurada and acceso is not None else None,
        estado=estado,
    )


def vincular_ong(
    session: Session, organizacion_id: int, ong_id: UUID | None
) -> Organizacion:
    """Sólo el endpoint administrativo usa esta vinculación explícita por UUID."""

    ong = session.scalar(
        select(Organizacion).where(Organizacion.id == organizacion_id).with_for_update()
    )
    if ong is None:
        raise ErrorNacional(404, "La organización local no existe.")
    if ong.tipo != TipoOrganizacion.ONG:
        raise ErrorNacional(422, "Sólo se pueden vincular organizaciones de tipo ONG.")
    try:
        if ong.ong_nacional_id != ong_id:
            session.execute(
                delete(AccesoNacional).where(
                    AccesoNacional.organizacion_id == organizacion_id
                )
            )
            session.execute(
                delete(AprovisionamientoNacional).where(
                    AprovisionamientoNacional.organizacion_id == organizacion_id
                )
            )
        ong.ong_nacional_id = ong_id
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise ErrorNacional(
            409, "Esa ONG nacional ya está vinculada a otra organización local."
        ) from error
    return ong
