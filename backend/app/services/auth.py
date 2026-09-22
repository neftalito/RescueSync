from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.security import verificar_password
from app.db.models import Organizacion, RolUsuario, TipoOrganizacion, Usuario

_TIPO_REQUERIDO_POR_ROL: dict[RolUsuario, TipoOrganizacion] = {
    RolUsuario.OPERADOR_MUNICIPAL: TipoOrganizacion.MUNICIPIO,
    RolUsuario.COORDINADOR_REGIONAL: TipoOrganizacion.CENTRO_COORDINADOR,
    RolUsuario.REPRESENTANTE_ONG: TipoOrganizacion.ONG,
}


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

    tipo_requerido = _TIPO_REQUERIDO_POR_ROL.get(usuario.rol)
    if tipo_requerido is None:
        organizacion = usuario.organizacion
        return organizacion is None or organizacion.activa

    return organizacion_vigente_de_tipo(usuario, tipo_requerido) is not None


def obtener_usuario_vigente(session: Session, usuario_id: int) -> Usuario | None:
    """Carga desde PostgreSQL la identidad y el contexto vigentes de una sesión."""

    usuario = session.scalar(
        select(Usuario)
        .options(joinedload(Usuario.organizacion))
        .where(Usuario.id == usuario_id)
    )
    if usuario is None or not usuario_tiene_contexto_vigente(usuario):
        return None
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
