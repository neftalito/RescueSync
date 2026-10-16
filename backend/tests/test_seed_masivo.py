"""Verifica volumen, repetición y consistencia usando PostgreSQL real."""

from dataclasses import asdict, replace
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import generar_password_hash
from app.db.models import (
    AccesoNacional,
    Convocatoria,
    Emergencia,
    Lote,
    Notificacion,
    Oferta,
    OfertaItem,
    OfertaItemAporte,
    OfertaVersion,
    Organizacion,
    RolUsuario,
    Usuario,
)
from app.scripts.seed_masivo import ConfiguracionSeed, main, seed_mass_data
from app.services.acceso_nacional import cifrador
from app.services.auth import autenticar_usuario

CONFIG = ConfiguracionSeed(
    seed=17041,
    municipios=2,
    centros=2,
    ongs=4,
    emergencias=15,
    lotes_por_emergencia=4,
    ofertas_por_convocatoria=3,
    batch_size=4,
)


@pytest.fixture(autouse=True)
def cifrado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        get_settings(),
        "nacional_encryption_key",
        SecretStr(Fernet.generate_key().decode()),
    )


def test_repetir_carga_no_duplica_ni_sobrescribe_datos(db_session: Session) -> None:
    primero = seed_mass_data(db_session, CONFIG)
    assert primero.organizaciones == 8
    assert primero.usuarios == 10
    assert primero.emergencias == 15
    assert primero.lotes == 36
    assert primero.convocatorias == 6
    assert primero.ofertas == 18
    assert primero.notificaciones == 15
    usuario = db_session.scalar(
        select(Usuario).where(
            Usuario.email == f"masivo-{CONFIG.seed}-ong-1@example.test"
        )
    )
    assert usuario is not None
    usuario.password_hash = generar_password_hash("password-modificada-123")
    usuario.activo = False
    original = usuario.password_hash
    emergencia = db_session.scalar(
        select(Emergencia).where(
            Emergencia.zona == f"Masivo {CONFIG.seed} emergencia 00000001"
        )
    )
    assert emergencia is not None
    emergencia.descripcion = "Descripción editada manualmente."
    db_session.flush()

    repetido = seed_mass_data(db_session, replace(CONFIG, batch_size=7))

    assert repetido.omitidas == 15
    assert all(
        valor == 0 for campo, valor in asdict(repetido).items() if campo != "omitidas"
    )
    assert usuario.password_hash == original and not usuario.activo
    assert emergencia.descripcion == "Descripción editada manualmente."


def test_ampliar_objetivo_agrega_solo_escenarios_nuevos(db_session: Session) -> None:
    seed_mass_data(db_session, CONFIG)
    resultado = seed_mass_data(db_session, replace(CONFIG, emergencias=20, ongs=5))
    assert resultado.organizaciones == 1
    assert resultado.usuarios == 1
    assert resultado.emergencias == 5 and resultado.omitidas == 15
    assert resultado.lotes == 12
    assert resultado.convocatorias == 2 and resultado.ofertas == 6
    assert resultado.notificaciones == 5


def test_ofertas_tienen_desglose_valido_y_referencias_nacionales(
    db_session: Session,
) -> None:
    seed_mass_data(db_session, CONFIG)
    # Fuerza también los triggers diferidos que normalmente se validan al commit.
    db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    versiones = db_session.scalars(
        select(OfertaVersion)
        .join(Oferta)
        .join(Convocatoria)
        .where(Convocatoria.sistema_origen_ref == f"masivo-{CONFIG.seed}")
    ).all()
    assert len(versiones) == 18
    for version in versiones:
        assert version.requiere_desglose_nacional and version.presentada_en is not None
        assert len(version.participantes) == 1
        assert version.participantes[0].confirmada_en is not None
        assert len(version.items) == 4
        for item in version.items:
            assert (
                sum((aporte.cantidad for aporte in item.aportes), Decimal(0))
                == item.cantidad_ofrecida
            )
            assert item.cantidad_ofrecida > 0
    aporte = db_session.scalar(
        select(OfertaItemAporte)
        .join(OfertaItem, OfertaItem.id == OfertaItemAporte.oferta_item_id)
        .join(Lote, Lote.id == OfertaItem.lote_id)
        .where(
            Lote.codigo_capacidad == "AGUA",
            Lote.emergencia_id.in_(
                select(Emergencia.id).where(
                    Emergencia.zona.like(f"Masivo {CONFIG.seed} emergencia %")
                )
            ),
        )
    )
    assert aporte is not None
    org = db_session.get(Organizacion, aporte.ong_id)
    assert org is not None
    indice = int(org.nombre.rsplit(" ", 1)[1])
    assert aporte.recurso_nacional_id == uuid5(
        NAMESPACE_URL, f"rescuesync-masivo:{CONFIG.seed}:recurso:{indice}:1"
    )
    assert aporte.capacidad_nacional_id == uuid5(
        NAMESPACE_URL, "rescuesync:capacidad:AGUA"
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Notificacion)
            .where(Notificacion.clave_evento.like(f"masivo:{CONFIG.seed}:%"))
        )
        == 15
    )


def test_cuentas_permiten_entrar_y_tienen_acceso_tecnico_cifrado(
    db_session: Session,
) -> None:
    seed_mass_data(db_session, CONFIG)
    usuario = autenticar_usuario(
        db_session, f"masivo-{CONFIG.seed}-ong-1@example.test", "CargaMasiva2026!"
    )
    assert usuario is not None
    acceso = db_session.get(AccesoNacional, usuario.organizacion_id)
    assert acceso is not None
    assert acceso.ong_id == uuid5(
        NAMESPACE_URL, f"rescuesync-masivo:{CONFIG.seed}:ong:1"
    )
    assert acceso.cuenta_id == uuid5(
        NAMESPACE_URL, f"rescuesync-masivo:{CONFIG.seed}:cuenta-tecnica:1"
    )
    assert (
        cifrador().decrypt(acceso.secreto_cifrado.encode()).decode()
        == "CargaMasivaTecnica2026!"
    )


def test_error_revierte_toda_la_carga(db_session: Session) -> None:
    with (
        pytest.raises(RuntimeError, match="fallo de prueba"),
        db_session.begin_nested(),
    ):
        seed_mass_data(db_session, CONFIG)
        raise RuntimeError("fallo de prueba")
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Organizacion)
            .where(Organizacion.nombre.like(f"Masivo {CONFIG.seed} %"))
        )
        == 0
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Emergencia)
            .where(Emergencia.zona.like(f"Masivo {CONFIG.seed} %"))
        )
        == 0
    )


def test_rechaza_produccion_antes_de_escribir(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "app_env", "production")
    with pytest.raises(ValueError, match="desarrollo y pruebas"):
        seed_mass_data(db_session, CONFIG)
    assert main(["--dry-run"]) == 1


def test_exige_cifrado_antes_de_escribir(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "nacional_encryption_key", None)
    with pytest.raises(ValueError, match="NACIONAL_ENCRYPTION_KEY"):
        seed_mass_data(db_session, CONFIG)


@pytest.mark.parametrize(
    "opciones", [{"emergencias": 0}, {"batch_size": 1001}, {"seed": -1}, {"ongs": 2}]
)
def test_rechaza_configuracion_invalida(opciones: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        replace(CONFIG, **opciones)


def test_simulacion_no_necesita_base_de_datos(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--dry-run", "--emergencias", "10000"]) == 0
    assert "10000" in capsys.readouterr().out


def test_masivo_solo_crea_el_administrador_default_del_demo(
    db_session: Session,
) -> None:
    db_session.execute(delete(Usuario).where(Usuario.rol == RolUsuario.ADMINISTRADOR))
    seed_mass_data(db_session, CONFIG)
    settings = get_settings()
    admin = autenticar_usuario(
        db_session,
        str(settings.admin_email),
        settings.admin_initial_password.get_secret_value(),
    )
    assert admin is not None and admin.rol == RolUsuario.ADMINISTRADOR
    assert admin.requiere_cambio_password
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Usuario)
            .where(Usuario.rol == RolUsuario.ADMINISTRADOR)
        )
        == 1
    )
    assert (
        db_session.scalar(
            select(Usuario.id).where(
                Usuario.email == f"masivo-{CONFIG.seed}-admin@example.test"
            )
        )
        is None
    )


def test_masivo_respeta_configuracion_del_administrador_inicial(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_session.execute(delete(Usuario).where(Usuario.rol == RolUsuario.ADMINISTRADOR))
    monkeypatch.setattr(get_settings(), "admin_email", "admin-carga@rescuesync.org")
    monkeypatch.setattr(
        get_settings(), "admin_initial_password", SecretStr("Clave-configurada-2026")
    )
    seed_mass_data(db_session, CONFIG)
    assert (
        autenticar_usuario(
            db_session, "admin-carga@rescuesync.org", "Clave-configurada-2026"
        )
        is not None
    )


def test_repetir_o_cambiar_seed_conserva_password_del_admin(
    db_session: Session,
) -> None:
    db_session.execute(delete(Usuario).where(Usuario.rol == RolUsuario.ADMINISTRADOR))
    seed_mass_data(db_session, CONFIG)
    admin = db_session.scalar(
        select(Usuario).where(Usuario.rol == RolUsuario.ADMINISTRADOR)
    )
    assert admin is not None
    admin.password_hash = generar_password_hash("Clave-rotada-2026")
    admin.requiere_cambio_password = False
    admin.version_sesion += 1
    original = (admin.id, admin.password_hash, admin.version_sesion)
    db_session.flush()

    seed_mass_data(db_session, CONFIG)
    seed_mass_data(db_session, replace(CONFIG, seed=CONFIG.seed + 1))

    assert (admin.id, admin.password_hash, admin.version_sesion) == original
    assert not admin.requiere_cambio_password
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Usuario)
            .where(Usuario.rol == RolUsuario.ADMINISTRADOR)
        )
        == 1
    )
