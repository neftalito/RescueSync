from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import generar_password_hash
from app.db.models import RolUsuario, Usuario
from app.services.admin_lock import bloquear_gestion_administradores


class AdminInicialEnConflictoError(RuntimeError):
    """Indica que el correo inicial pertenece a una cuenta incompatible."""


def asegurar_admin_inicial(session: Session, settings: Settings) -> Usuario:
    """Garantiza un administrador activo sin resetear cuentas existentes.

    Usa un bloqueo transaccional de PostgreSQL para que varios procesos de arranque
    no intenten crear simultáneamente la misma identidad inicial.
    """

    bloquear_gestion_administradores(session)
    administrador = session.scalar(
        select(Usuario)
        .where(
            Usuario.rol == RolUsuario.ADMINISTRADOR,
            Usuario.activo.is_(True),
        )
        .order_by(Usuario.id)
        .limit(1)
    )
    if administrador is not None:
        return administrador

    email = str(settings.admin_email).strip().lower()
    cuenta_existente = session.scalar(
        select(Usuario).where(func.lower(Usuario.email) == email).with_for_update()
    )
    if cuenta_existente is not None:
        raise AdminInicialEnConflictoError(
            "ADMIN_EMAIL ya pertenece a una cuenta que no es un administrador activo"
        )

    administrador = Usuario(
        email=email,
        password_hash=generar_password_hash(
            settings.admin_initial_password.get_secret_value()
        ),
        rol=RolUsuario.ADMINISTRADOR,
        organizacion_id=None,
        requiere_cambio_password=True,
    )
    session.add(administrador)
    session.flush()
    return administrador
