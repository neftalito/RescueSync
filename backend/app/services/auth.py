from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.roles import TIPO_ORGANIZACION_POR_ROL
from app.core.security import generar_password_hash, verificar_password
from app.db.models import Organizacion, TipoOrganizacion, Usuario


def organizacion_vigente_de_tipo(
    usuario: Usuario, tipo: TipoOrganizacion
) -> Organizacion | None:
    """Devuelve la organización si está activa y es del tipo requerido."""

    organizacion = usuario.organizacion
    if (
        usuario.organizacion_id is None
        or organizacion is None
        or organizacion.tipo is not tipo
        or not organizacion.activa
    ):
        return None
    return organizacion


def usuario_tiene_contexto_vigente(usuario: Usuario) -> bool:
    """Valida que identidad, organización y rol sigan habilitados y sean coherentes."""

    if not usuario.activo:
        return False

    tipo_requerido = TIPO_ORGANIZACION_POR_ROL.get(usuario.rol)
    if tipo_requerido is None:
        organizacion = usuario.organizacion
        return organizacion is None or organizacion.activa

    return organizacion_vigente_de_tipo(usuario, tipo_requerido) is not None


def obtener_usuario_vigente(
    session: Session,
    usuario_id: int,
    version_sesion: int,
) -> Usuario | None:
    """Carga desde PostgreSQL la identidad y el contexto vigentes de una sesión."""

    usuario = session.scalar(
        select(Usuario)
        .options(joinedload(Usuario.organizacion))
        .where(Usuario.id == usuario_id)
    )
    if (
        usuario is None
        or usuario.version_sesion != version_sesion
        or not usuario_tiene_contexto_vigente(usuario)
    ):
        return None
    return usuario


class PasswordActualIncorrectaError(ValueError):
    """Indica que la contraseña actual no permite autorizar el cambio."""


class PasswordSinCambiosError(ValueError):
    """Indica que la contraseña nueva coincide con la vigente."""


def cambiar_password_propia(
    session: Session,
    usuario: Usuario,
    password_actual: str,
    password_nueva: str,
) -> Usuario:
    """Cambia la contraseña propia e invalida cualquier otra sesión abierta."""

    if not verificar_password(password_actual, usuario.password_hash):
        raise PasswordActualIncorrectaError
    if verificar_password(password_nueva, usuario.password_hash):
        raise PasswordSinCambiosError

    usuario.password_hash = generar_password_hash(password_nueva)
    usuario.requiere_cambio_password = False
    usuario.version_sesion += 1
    session.flush()
    return usuario


def autenticar_usuario(session: Session, email: str, password: str) -> Usuario | None:
    """Autentica credenciales locales sin revelar si una cuenta existe o está inactiva."""

    email_normalizado = email.strip().lower()
    usuario = session.scalar(
        select(Usuario)
        .options(joinedload(Usuario.organizacion))
        .where(func.lower(Usuario.email) == email_normalizado)
    )

    password_valido = verificar_password(
        password,
        usuario.password_hash if usuario is not None else None,
    )
    if (
        not password_valido
        or usuario is None
        or not usuario_tiene_contexto_vigente(usuario)
    ):
        return None
    return usuario
