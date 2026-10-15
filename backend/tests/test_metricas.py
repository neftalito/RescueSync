"""Indicadores globales sobre PostgreSQL y autorización de ambos endpoints."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import crear_valor_sesion
from app.db.models import (
    Emergencia,
    EstadoEmergencia,
    EstadoOferta,
    Oferta,
    OfertaItem,
    OfertaVersion,
    OfertaVersionParticipante,
    Organizacion,
    RolUsuario,
    TipoOrganizacion,
    TipoParticipacion,
    Usuario,
)
from app.db.session import get_db
from app.integrations.bonita.cliente import BonitaNoDisponibleError, ClienteBonita
from app.integrations.bonita.contratos import TransicionTareaArchivada
from app.main import app
from app.schemas.metricas import DisponibilidadBonita, FiltrosMetricas
from app.scripts.seed import seed_development_data
from app.services.metricas import obtener_metricas
from app.services.metricas_bonita import obtener_tiempos

FECHA = datetime(2026, 10, 15, 12, tzinfo=UTC)
FILTROS = FiltrosMetricas(fecha_desde=date(2026, 10, 1), fecha_hasta=date(2026, 10, 31))


@pytest.fixture(autouse=True)
def cifrado_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        get_settings(),
        "nacional_encryption_key",
        SecretStr(Fernet.generate_key().decode()),
    )


@pytest.fixture
def escenario(db_session: Session) -> Session:
    """Reutiliza el escenario público demo dentro de la transacción de prueba."""
    seed_development_data(db_session, incluir_dashboard=False)
    for emergencia in db_session.scalars(select(Emergencia)):
        emergencia.creada_en = FECHA
    db_session.flush()
    return db_session


@pytest.fixture
def client(escenario: Session) -> Iterator[TestClient]:
    def base_prueba() -> Iterator[Session]:
        yield escenario

    app.dependency_overrides[get_db] = base_prueba
    try:
        with TestClient(app) as cliente:
            yield cliente
    finally:
        app.dependency_overrides.clear()


def autenticar(client: TestClient, session: Session, rol: RolUsuario) -> None:
    """Usa una sesión real firmada; la autorización vuelve a leer el usuario."""
    usuario = session.scalars(select(Usuario).where(Usuario.rol == rol)).first()
    assert usuario is not None
    client.cookies.set(
        get_settings().session_cookie_name,
        crear_valor_sesion(usuario.id, usuario.version_sesion),
    )


@pytest.mark.parametrize("ruta", ["/metricas", "/metricas/tiempos"])
def test_metricas_exige_sesion(client: TestClient, ruta: str) -> None:
    assert client.get(f"/api/v1{ruta}").status_code == 401


@pytest.mark.parametrize("ruta", ["/metricas", "/metricas/tiempos"])
@pytest.mark.parametrize(
    "rol", [r for r in RolUsuario if r != RolUsuario.AUDITOR_DIRECTIVO]
)
def test_metricas_rechaza_todos_los_otros_roles(
    client: TestClient, escenario: Session, ruta: str, rol: RolUsuario
) -> None:
    autenticar(client, escenario, rol)
    assert client.get(f"/api/v1{ruta}").status_code == 403


@pytest.mark.parametrize("ruta", ["/metricas", "/metricas/tiempos"])
def test_auditor_consulta_indicadores_y_rechaza_fechas_invertidas(
    client: TestClient, escenario: Session, ruta: str
) -> None:
    autenticar(client, escenario, RolUsuario.AUDITOR_DIRECTIVO)
    respuesta = client.get(
        f"/api/v1{ruta}",
        params={"fecha_desde": "2026-10-01", "fecha_hasta": "2026-10-31"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["filtros"]["fecha_desde"] == "2026-10-01"
    invalida = client.get(
        f"/api/v1{ruta}?fecha_desde=2026-11-01&fecha_hasta=2026-10-01"
    )
    assert invalida.status_code == 422


def test_resumen_no_multiplica_emergencias_por_lotes_items_o_versiones(
    escenario: Session,
) -> None:
    reporte = obtener_metricas(escenario, FILTROS)
    assert reporte.resumen.model_dump() == {
        "emergencias": 2,
        "activas": 2,
        "resueltas": 0,
        "convocatorias_abiertas": 1,
        "ofertas_presentadas": 1,
        "ong_participantes": 1,
    }
    assert sum(c.cantidad for c in reporte.por_estado) == 2
    assert reporte.evolucion_mensual[0].cantidad == 2
    assert {c.unidad: c.cantidad for c in reporte.cantidades_ofrecidas} == {
        "litros": Decimal(3000),
        "kits": Decimal(10),
    }


def test_periodo_vacio_devuelve_ceros_y_meses_sin_altas(escenario: Session) -> None:
    reporte = obtener_metricas(
        escenario,
        FiltrosMetricas(fecha_desde=date(2025, 12, 1), fecha_hasta=date(2026, 2, 1)),
    )
    assert reporte.resumen.emergencias == reporte.resumen.ong_participantes == 0
    assert [c.categoria for c in reporte.evolucion_mensual] == [
        "2025-12",
        "2026-01",
        "2026-02",
    ]
    assert all(c.cantidad == 0 for c in reporte.evolucion_mensual)
    assert reporte.cantidades_ofrecidas == []


def test_fechas_inclusivas_usan_horario_argentino_y_filtros_combinados(
    escenario: Session,
) -> None:
    emergencias = escenario.scalars(select(Emergencia).order_by(Emergencia.id)).all()
    emergencias[0].creada_en = datetime(2026, 10, 1, 2, 59, 59, tzinfo=UTC)
    emergencias[1].creada_en = datetime(2026, 11, 1, 2, 59, 59, tzinfo=UTC)
    escenario.flush()
    reporte = obtener_metricas(escenario, FILTROS)
    assert reporte.resumen.emergencias == 1
    filtrado = FILTROS.model_copy(
        update={
            "municipio_id": emergencias[1].municipio_id,
            "estado": emergencias[1].estado,
            "gravedad": emergencias[1].gravedad,
        }
    )
    assert obtener_metricas(escenario, filtrado).resumen.emergencias == 1
    assert (
        obtener_metricas(
            escenario, FILTROS.model_copy(update={"municipio_id": 999999})
        ).resumen.emergencias
        == 0
    )
    emergencias[1].creada_en = datetime(2026, 11, 1, 3, tzinfo=UTC)
    escenario.flush()
    assert obtener_metricas(escenario, FILTROS).resumen.emergencias == 0


def test_resueltas_y_canceladas_no_se_cuentan_como_activas(escenario: Session) -> None:
    emergencias = escenario.scalars(select(Emergencia).order_by(Emergencia.id)).all()
    emergencias[0].estado = EstadoEmergencia.RESUELTA
    emergencias[1].estado = EstadoEmergencia.CANCELADA
    escenario.flush()
    resumen = obtener_metricas(escenario, FILTROS).resumen
    assert resumen.resueltas == 1
    assert resumen.activas == 0


@pytest.mark.parametrize("estado", [EstadoOferta.BORRADOR, EstadoOferta.RETIRADA])
def test_borradores_y_retiradas_no_aportan_cantidades(
    escenario: Session, estado: EstadoOferta
) -> None:
    oferta = escenario.scalars(select(Oferta)).one()
    oferta.estado = estado
    escenario.flush()
    reporte = obtener_metricas(escenario, FILTROS)
    assert reporte.resumen.ofertas_presentadas == reporte.resumen.ong_participantes == 0
    assert reporte.cantidades_ofrecidas == []


def test_solo_version_vigente_presentada_y_unidades_separadas(
    escenario: Session,
) -> None:
    oferta = escenario.scalars(select(Oferta)).one()
    vieja = escenario.scalars(select(OfertaVersion)).one()
    item = vieja.items[0]
    nueva = OfertaVersion(
        oferta_id=oferta.id,
        creada_por_usuario_id=oferta.creada_por_usuario_id,
        numero=2,
        presentada_en=FECHA,
    )
    escenario.add(nueva)
    escenario.flush()
    escenario.add(
        OfertaItem(
            oferta_version_id=nueva.id,
            convocatoria_id=oferta.convocatoria_id,
            lote_id=item.lote_id,
            tipo=item.tipo,
            descripcion="Nueva cantidad",
            cantidad_ofrecida=Decimal(12),
            unidad="cajas",
        )
    )
    oferta.version_actual = 2
    escenario.flush()
    reporte = obtener_metricas(escenario, FILTROS)
    assert reporte.resumen.ofertas_presentadas == 1
    assert [(c.cantidad, c.unidad) for c in reporte.cantidades_ofrecidas] == [
        (Decimal(12), "cajas")
    ]
    nueva.presentada_en = None
    escenario.flush()
    assert obtener_metricas(escenario, FILTROS).resumen.ofertas_presentadas == 0


def test_consorcio_confirmado_cuenta_una_oferta_y_dos_ongs(escenario: Session) -> None:
    oferta = escenario.scalars(select(Oferta)).one()
    version = escenario.scalars(select(OfertaVersion)).one()
    ongs = escenario.scalars(
        select(Organizacion)
        .where(Organizacion.tipo == TipoOrganizacion.ONG)
        .order_by(Organizacion.id)
    ).all()
    for i, ong in enumerate(ongs):
        escenario.add(
            OfertaVersionParticipante(
                oferta_version_id=version.id,
                ong_id=ong.id,
                nombre_ong=ong.nombre,
                rol=TipoParticipacion.LIDER if i == 0 else TipoParticipacion.MIEMBRO,
                confirmada_en=FECHA if i == 0 else None,
            )
        )
    escenario.flush()
    assert obtener_metricas(escenario, FILTROS).resumen.ofertas_presentadas == 0
    participante = escenario.get(OfertaVersionParticipante, (version.id, ongs[1].id))
    assert participante is not None
    participante.confirmada_en = FECHA
    # Una oferta fuente fusionada sigue en la base, pero no duplica cantidades.
    fuente = Oferta(
        convocatoria_id=oferta.convocatoria_id,
        ong_creadora_id=ongs[1].id,
        creada_por_usuario_id=oferta.creada_por_usuario_id,
        fusionada_en_oferta_id=oferta.id,
        estado=EstadoOferta.PRESENTADA,
    )
    escenario.add(fuente)
    escenario.flush()
    escenario.add(
        OfertaVersion(
            oferta_id=fuente.id,
            creada_por_usuario_id=oferta.creada_por_usuario_id,
            numero=1,
            presentada_en=FECHA,
        )
    )
    escenario.flush()
    reporte = obtener_metricas(escenario, FILTROS)
    assert reporte.resumen.ofertas_presentadas == 1
    assert reporte.resumen.ong_participantes == 2
    assert {c.categoria: c.cantidad for c in reporte.tipos_oferta} == {
        "INDIVIDUAL": 0,
        "CONJUNTA": 1,
    }


def test_bonita_parcial_conserva_muestras_validas(
    escenario: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i, emergencia in enumerate(
        escenario.scalars(select(Emergencia).order_by(Emergencia.id))
    ):
        emergencia.bonita_process_instance_id = 900 + i
        emergencia.bonita_process_version = "1.2"
    escenario.flush()

    def historial(_self: ClienteBonita, case_id: int) -> list[TransicionTareaArchivada]:
        if case_id == 901:
            raise BonitaNoDisponibleError("Sin conexión")
        return [
            TransicionTareaArchivada(
                type="USER_TASK",
                sourceObjectId=1,
                rootCaseId=case_id,
                name="Generar lotes",
                state=estado,
                reached_state_date=fecha,
            )
            for estado, fecha in [
                ("ready", "2026-10-15 09:00:00"),
                ("completed", "2026-10-15 10:00:00"),
            ]
        ]

    monkeypatch.setattr(ClienteBonita, "obtener_historial_tareas", historial)
    monkeypatch.setattr(
        ClienteBonita, "obtener_tareas_activas", lambda _self, _case_id: []
    )
    from app.integrations.bonita.cliente import ConfiguracionBonita

    with ClienteBonita(ConfiguracionBonita.desde_settings(get_settings())) as cliente:
        reporte = obtener_tiempos(escenario, FILTROS, cliente)
    assert reporte.disponibilidad == DisponibilidadBonita.PARCIAL
    assert reporte.casos_consultados == reporte.casos_con_error == 1
    assert reporte.etapas[0].promedio_segundos == 3600
    assert reporte.etapas[0].muestras == 1
