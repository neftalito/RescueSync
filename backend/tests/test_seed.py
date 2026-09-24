from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Convocatoria,
    Emergencia,
    Lote,
    Oferta,
    Organizacion,
    Usuario,
)
from app.scripts.seed import seed_development_data
from app.services.auth import autenticar_usuario

EMAILS = (
    "municipio@rescuesync.org",
    "coordinador@rescuesync.org",
    "ong@rescuesync.org",
    "auditor@rescuesync.org",
    "admin@rescuesync.org",
)
ORGANIZACIONES = (
    "Municipalidad de Puerto Esperanza",
    "Centro Coordinador Litoral",
    "Ayuda Sin Fronteras",
    "Red Médica Solidaria",
)
ZONAS = (
    "Arroyo Sur — datos demo",
    "Corredor Norte — datos demo",
)


def _contar(session: Session, modelo: type[object], condicion: object) -> int:
    cantidad = session.scalar(select(func.count()).select_from(modelo).where(condicion))
    assert cantidad is not None
    return cantidad


def test_seed_es_idempotente_y_crea_un_usuario_vigente_por_rol(
    db_session: Session,
) -> None:
    primer_resultado = seed_development_data(db_session)
    segundo_resultado = seed_development_data(db_session)

    assert primer_resultado == segundo_resultado
    assert _contar(db_session, Usuario, Usuario.email.in_(EMAILS)) == 5
    assert (
        _contar(db_session, Organizacion, Organizacion.nombre.in_(ORGANIZACIONES)) == 4
    )
    assert _contar(db_session, Emergencia, Emergencia.zona.in_(ZONAS)) == 2

    roles = set()
    for cuenta in primer_resultado.cuentas:
        password = (
            get_settings().admin_initial_password.get_secret_value()
            if cuenta.rol.value == "ADMINISTRADOR"
            else f"{cuenta.email.partition('@')[0]}123"
        )
        usuario = autenticar_usuario(
            db_session,
            cuenta.email,
            password,
        )
        assert usuario is not None
        roles.add(usuario.rol)
    assert roles == {cuenta.rol for cuenta in primer_resultado.cuentas}


def test_seed_migra_los_correos_demo_del_formato_anterior(
    db_session: Session,
) -> None:
    seed_development_data(db_session)
    usuario = db_session.scalar(
        select(Usuario).where(Usuario.email == "municipio@rescuesync.org")
    )
    assert usuario is not None
    usuario_id = usuario.id
    usuario.email = "municipio@demo.rescuesync.org"
    db_session.flush()

    seed_development_data(db_session)

    migrado = db_session.scalar(
        select(Usuario).where(Usuario.email == "municipio@rescuesync.org")
    )
    assert migrado is not None
    assert migrado.id == usuario_id
    assert (
        db_session.scalar(
            select(Usuario).where(Usuario.email == "municipio@demo.rescuesync.org")
        )
        is None
    )


def test_seed_deja_convocatoria_lotes_y_oferta_para_pruebas(
    db_session: Session,
) -> None:
    seed_development_data(db_session)
    emergencia = db_session.scalar(
        select(Emergencia).where(Emergencia.zona == "Corredor Norte — datos demo")
    )

    assert emergencia is not None
    assert _contar(db_session, Lote, Lote.emergencia_id == emergencia.id) == 3
    assert (
        _contar(
            db_session,
            Convocatoria,
            Convocatoria.emergencia_id == emergencia.id,
        )
        == 1
    )
    convocatoria = db_session.scalar(
        select(Convocatoria).where(Convocatoria.emergencia_id == emergencia.id)
    )
    assert convocatoria is not None
    assert _contar(db_session, Oferta, Oferta.convocatoria_id == convocatoria.id) == 1
