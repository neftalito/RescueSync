from sqlalchemy import text
from sqlalchemy.orm import Session

_CLAVE_BLOQUEO_ADMIN = 1_937_642_011


def bloquear_gestion_administradores(session: Session) -> None:
    """Serializa cambios que pueden modificar el conjunto de administradores."""

    session.execute(
        text("SELECT pg_advisory_xact_lock(:clave)"),
        {"clave": _CLAVE_BLOQUEO_ADMIN},
    )
