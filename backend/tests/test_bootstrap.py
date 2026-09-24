import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import generar_password_hash, verificar_password
from app.db.models import RolUsuario, Usuario
from app.services.bootstrap import (
    AdminInicialEnConflictoError,
    asegurar_admin_inicial,
)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        admin_email="inicial@rescuesync.org",
        admin_initial_password="Clave-inicial-2026",
    )


def _quitar_administradores_existentes(db_session: Session) -> None:
    db_session.execute(delete(Usuario).where(Usuario.rol == RolUsuario.ADMINISTRADOR))
    db_session.flush()


def test_bootstrap_crea_admin_temporal_y_es_idempotente(
    db_session: Session,
) -> None:
    _quitar_administradores_existentes(db_session)
    primer_admin = asegurar_admin_inicial(db_session, _settings())
    segundo_admin = asegurar_admin_inicial(db_session, _settings())

    assert segundo_admin.id == primer_admin.id
    assert primer_admin.email == "inicial@rescuesync.org"
    assert primer_admin.rol is RolUsuario.ADMINISTRADOR
    assert primer_admin.requiere_cambio_password is True
    assert verificar_password("Clave-inicial-2026", primer_admin.password_hash)


def test_bootstrap_no_reemplaza_un_administrador_activo(
    db_session: Session,
) -> None:
    _quitar_administradores_existentes(db_session)
    existente = Usuario(
        email="existente@rescuesync.org",
        password_hash=generar_password_hash("Clave-existente-2026"),
        rol=RolUsuario.ADMINISTRADOR,
    )
    db_session.add(existente)
    db_session.flush()

    resultado = asegurar_admin_inicial(db_session, _settings())

    assert resultado.id == existente.id
    assert verificar_password("Clave-existente-2026", resultado.password_hash)


def test_bootstrap_falla_si_el_correo_inicial_esta_ocupado(
    db_session: Session,
) -> None:
    _quitar_administradores_existentes(db_session)
    db_session.add(
        Usuario(
            email="inicial@rescuesync.org",
            password_hash=generar_password_hash("Clave-auditor-2026"),
            rol=RolUsuario.AUDITOR_DIRECTIVO,
        )
    )
    db_session.flush()

    with pytest.raises(AdminInicialEnConflictoError):
        asegurar_admin_inicial(db_session, _settings())
