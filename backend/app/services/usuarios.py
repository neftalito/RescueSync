from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.roles import TIPO_ORGANIZACION_POR_ROL
from app.core.security import generar_password_hash
from app.db.models import Organizacion, RolUsuario, Usuario
from app.schemas.usuarios import UsuarioCreate, UsuarioUpdate
from app.services.admin_lock import bloquear_gestion_administradores


class UsuarioNoEncontradoError(LookupError):
    """Indica que la cuenta solicitada no existe."""


class EmailDuplicadoError(ValueError):
    """Indica que el correo normalizado ya pertenece a otra cuenta."""


class ContextoUsuarioInvalidoError(ValueError):
    """Indica que rol y organización no forman un contexto válido."""


class ProteccionAdministradorError(ValueError):
    """Impide que una operación deje al sistema sin administración."""


def listar_usuarios(session: Session) -> list[Usuario]:
    """Lista todas las cuentas, incluidas las inactivas, ordenadas por correo."""

    return list(
        session.scalars(
            select(Usuario)
            .options(joinedload(Usuario.organizacion))
            .order_by(func.lower(Usuario.email), Usuario.id)
        )
    )


def listar_organizaciones_activas(session: Session) -> list[Organizacion]:
    """Lista organizaciones habilitadas para asignarlas a usuarios operativos."""

    return list(
        session.scalars(
            select(Organizacion)
            .where(Organizacion.activa.is_(True))
            .order_by(Organizacion.tipo, Organizacion.nombre)
        )
    )


def _normalizar_email(email: str) -> str:
    return email.strip().lower()


def _validar_email_disponible(
    session: Session,
    email: str,
    usuario_id: int | None = None,
) -> None:
    consulta = select(Usuario.id).where(func.lower(Usuario.email) == email)
    if usuario_id is not None:
        consulta = consulta.where(Usuario.id != usuario_id)
    if session.scalar(consulta) is not None:
        raise EmailDuplicadoError


def _resolver_organizacion(
    session: Session,
    rol: RolUsuario,
    organizacion_id: int | None,
) -> Organizacion | None:
    tipo_requerido = TIPO_ORGANIZACION_POR_ROL.get(rol)
    if tipo_requerido is None:
        if organizacion_id is not None:
            raise ContextoUsuarioInvalidoError(
                "El rol seleccionado no admite una organización."
            )
        return None
    if organizacion_id is None:
        raise ContextoUsuarioInvalidoError(
            "El rol seleccionado requiere una organización."
        )

    organizacion = session.get(Organizacion, organizacion_id)
    if (
        organizacion is None
        or not organizacion.activa
        or organizacion.tipo is not tipo_requerido
    ):
        raise ContextoUsuarioInvalidoError(
            "La organización no está activa o no corresponde al rol seleccionado."
        )
    return organizacion


def _flush_email_seguro(session: Session) -> None:
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as error:
        raise EmailDuplicadoError from error


def crear_usuario(session: Session, datos: UsuarioCreate) -> Usuario:
    """Crea una cuenta activa con contraseña temporal y contexto validado."""

    if datos.rol is RolUsuario.ADMINISTRADOR:
        bloquear_gestion_administradores(session)
    email = _normalizar_email(str(datos.email))
    _validar_email_disponible(session, email)
    organizacion = _resolver_organizacion(session, datos.rol, datos.organizacion_id)
    usuario = Usuario(
        email=email,
        password_hash=generar_password_hash(datos.password.get_secret_value()),
        rol=datos.rol,
        organizacion_id=organizacion.id if organizacion is not None else None,
        requiere_cambio_password=True,
    )
    session.add(usuario)
    _flush_email_seguro(session)
    return usuario


def _obtener_usuario_bloqueado(session: Session, usuario_id: int) -> Usuario:
    usuario = session.scalar(
        select(Usuario)
        .options(selectinload(Usuario.organizacion))
        .where(Usuario.id == usuario_id)
        .with_for_update()
    )
    if usuario is None:
        raise UsuarioNoEncontradoError
    return usuario


def _proteger_administradores(
    session: Session,
    administrador_actual: Usuario,
    objetivo: Usuario,
    nuevo_rol: RolUsuario,
    nuevo_activo: bool,
) -> None:
    pierde_acceso_admin = objetivo.rol is RolUsuario.ADMINISTRADOR and (
        nuevo_rol is not RolUsuario.ADMINISTRADOR or not nuevo_activo
    )
    if not pierde_acceso_admin:
        return
    if objetivo.id == administrador_actual.id:
        raise ProteccionAdministradorError(
            "No podés quitar tu propio acceso de administrador."
        )

    administradores = list(
        session.scalars(
            select(Usuario)
            .where(
                Usuario.rol == RolUsuario.ADMINISTRADOR,
                Usuario.activo.is_(True),
            )
            .order_by(Usuario.id)
            .with_for_update()
        )
    )
    if len(administradores) <= 1:
        raise ProteccionAdministradorError(
            "Debe permanecer al menos un administrador activo."
        )


def actualizar_usuario(
    session: Session,
    administrador_actual: Usuario,
    usuario_id: int,
    datos: UsuarioUpdate,
) -> Usuario:
    """Modifica una cuenta preservando contexto, sesiones y último administrador."""

    bloquear_gestion_administradores(session)
    usuario = _obtener_usuario_bloqueado(session, usuario_id)
    campos = datos.model_fields_set
    nuevo_email = (
        _normalizar_email(str(datos.email)) if "email" in campos else usuario.email
    )
    nuevo_rol = datos.rol if "rol" in campos else usuario.rol
    nuevo_activo = datos.activo if "activo" in campos else usuario.activo
    nueva_organizacion_id = (
        datos.organizacion_id
        if "organizacion_id" in campos
        else usuario.organizacion_id
    )
    assert nuevo_rol is not None
    assert nuevo_activo is not None

    _validar_email_disponible(session, nuevo_email, usuario.id)
    organizacion = _resolver_organizacion(
        session,
        nuevo_rol,
        nueva_organizacion_id,
    )
    _proteger_administradores(
        session,
        administrador_actual,
        usuario,
        nuevo_rol,
        nuevo_activo,
    )

    se_desactiva = usuario.activo and not nuevo_activo
    usuario.email = nuevo_email
    usuario.rol = nuevo_rol
    usuario.activo = nuevo_activo
    usuario.organizacion = organizacion
    if se_desactiva:
        usuario.version_sesion += 1
    _flush_email_seguro(session)
    return usuario


def desactivar_usuario(
    session: Session,
    administrador_actual: Usuario,
    usuario_id: int,
) -> None:
    """Desactiva una cuenta sin eliminar su trazabilidad histórica."""

    actualizar_usuario(
        session,
        administrador_actual,
        usuario_id,
        UsuarioUpdate(activo=False),
    )


def restablecer_password(
    session: Session,
    administrador_actual: Usuario,
    usuario_id: int,
    password: str,
) -> Usuario:
    """Asigna una contraseña temporal e invalida las sesiones del destinatario."""

    usuario = _obtener_usuario_bloqueado(session, usuario_id)
    if usuario.id == administrador_actual.id:
        raise ProteccionAdministradorError(
            "Usá el cambio de contraseña personal para modificar tu propia clave."
        )
    usuario.password_hash = generar_password_hash(password)
    usuario.requiere_cambio_password = True
    usuario.version_sesion += 1
    session.flush()
    return usuario
