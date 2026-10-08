"""Vinculación y conexión nacional sin duplicar inventario en la base local."""

from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ConexionNacional, Organizacion, TipoOrganizacion, Usuario
from app.integrations.nacional.cliente import ClienteNacional, ErrorNacional
from app.schemas.inventario import ConexionRequest, EstadoConexion


def _cifrador() -> Fernet:
    """Deriva una clave con propósito separado del secreto de sesión local."""

    material = b"rescuesync-nacional-v1:" + get_settings().clave_firma_sesion.encode()
    return Fernet(urlsafe_b64encode(sha256(material).digest()))


def _ong(usuario: Usuario) -> Organizacion:
    ong = usuario.organizacion
    if ong is None or ong.tipo != TipoOrganizacion.ONG or not ong.activa:
        raise ErrorNacional(
            403, "Necesitás una ONG local activa para gestionar recursos."
        )
    return ong


def desconectar(session: Session, usuario_id: int) -> None:
    """Elimina la credencial temporal sin cambiar la vinculación institucional."""

    session.execute(
        delete(ConexionNacional).where(ConexionNacional.usuario_id == usuario_id)
    )
    session.commit()


def estado_conexion(session: Session, usuario: Usuario) -> EstadoConexion:
    ong = _ong(usuario)
    conexion = session.get(ConexionNacional, usuario.id)
    vigente = (
        conexion is not None
        and conexion.ong_id == ong.ong_nacional_id
        and conexion.version_sesion == usuario.version_sesion
        and conexion.expira_en > datetime.now(UTC)
    )
    if vigente and conexion is not None:
        try:
            _cifrador().decrypt(conexion.token_cifrado.encode())
        except InvalidToken:
            vigente = False
    if conexion is not None and not vigente:
        desconectar(session, usuario.id)
    return EstadoConexion(
        vinculada=ong.ong_nacional_id is not None,
        conectada=vigente,
        ong_id=ong.ong_nacional_id,
        expira_en=conexion.expira_en if vigente and conexion else None,
    )


def conectar(
    session: Session, usuario: Usuario, cliente: ClienteNacional, datos: ConexionRequest
) -> EstadoConexion:
    """Verifica la ONG del JWT antes de cifrarlo y conservarlo temporalmente."""

    ong = _ong(usuario)
    if ong.ong_nacional_id is None:
        raise ErrorNacional(
            409, "Un administrador debe vincular tu ONG al Sistema Nacional."
        )
    # Se toma el instante previo al login para no sobreestimar la duración del JWT.
    ahora = datetime.now(UTC)
    credencial = cliente.login(datos)
    token = credencial.access_token.get_secret_value()
    cuenta = cliente.cuenta(token)
    if cuenta.rol != "ONG" or cuenta.ong_id != ong.ong_nacional_id:
        raise ErrorNacional(
            403, "La cuenta nacional debe pertenecer a la ONG local vinculada."
        )
    # Las llamadas HTTP ya terminaron: recién aquí adquirimos el bloqueo local.
    session.refresh(ong, with_for_update=True)
    if cuenta.ong_id != ong.ong_nacional_id or not ong.activa:
        raise ErrorNacional(
            409, "La vinculación cambió durante la conexión. Intentá nuevamente."
        )
    conexion = session.get(ConexionNacional, usuario.id)
    if conexion is None:
        conexion = ConexionNacional(usuario_id=usuario.id)
        session.add(conexion)
    conexion.version_sesion = usuario.version_sesion
    assert cuenta.ong_id is not None
    conexion.ong_id = cuenta.ong_id
    conexion.token_cifrado = _cifrador().encrypt(token.encode()).decode()
    conexion.expira_en = ahora + timedelta(seconds=credencial.expires_in)
    session.commit()
    return estado_conexion(session, usuario)


def credencial(session: Session, usuario: Usuario) -> tuple[UUID, str]:
    """Revalida vinculación, versión y expiración antes de cada operación remota."""

    estado = estado_conexion(session, usuario)
    if not estado.conectada or estado.ong_id is None:
        raise ErrorNacional(401, "Conectá tu cuenta nacional para gestionar recursos.")
    conexion = session.get(ConexionNacional, usuario.id)
    assert conexion is not None
    return estado.ong_id, _cifrador().decrypt(conexion.token_cifrado.encode()).decode()


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
        ong.ong_nacional_id = ong_id
        session.execute(
            delete(ConexionNacional).where(
                ConexionNacional.usuario_id.in_(
                    select(Usuario.id).where(Usuario.organizacion_id == organizacion_id)
                )
            )
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise ErrorNacional(
            409, "Esa ONG nacional ya está vinculada a otra organización local."
        ) from error
    return ong
