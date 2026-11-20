"""Evidencia BPM, autorización del callback y métricas exactas sobre PostgreSQL."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    EstadoConvocatoria,
    HechoMonitoreo,
    Oferta,
    OfertaVersionParticipante,
    Organizacion,
    TipoOrganizacion,
    TipoParticipacion,
)
from app.db.session import get_db
from app.main import app
from app.schemas.metricas import FiltrosMetricas
from app.schemas.monitoreo import (
    AdjudicacionConfirmada,
    AporteAdjudicado,
    CantidadCumplida,
    DecisionConvocatoria,
    FinalizacionOng,
    RegistroHecho,
    ResolucionEmergencia,
    ResultadoValidacion,
    ValidacionNacional,
)
from app.services.hechos_monitoreo import HechoInvalidoError, registrar_hecho
from app.services.indicadores_proceso import obtener_indicadores

ALERTA = datetime(2026, 10, 14, 8, tzinfo=UTC)
FILTROS = FiltrosMetricas(fecha_desde=date(2026, 10, 1), fecha_hasta=date(2026, 10, 31))
TOKEN = "callback-monitoreo-token-de-prueba-123456789"


@pytest.fixture
def escenario(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Session:
    from app.scripts.seed import seed_development_data

    monkeypatch.setattr(
        get_settings(),
        "nacional_encryption_key",
        SecretStr(Fernet.generate_key().decode()),
    )
    monkeypatch.setattr(get_settings(), "bonita_callback_token", SecretStr(TOKEN))
    seed_development_data(db_session, incluir_dashboard=False)
    for e in db_session.scalars(select(Emergencia)):
        e.creada_en = ALERTA
    c = db_session.scalars(select(Convocatoria)).one()
    c.publicada_en = ALERTA + timedelta(hours=1)
    c.cierra_en = c.cerrada_en = ALERTA + timedelta(hours=2)
    c.estado = EstadoConvocatoria.CERRADA
    e = db_session.get(Emergencia, c.emergencia_id)
    assert e is not None
    e.bonita_process_instance_id = 4242
    db_session.flush()
    db_session.commit()
    return db_session


def adjudicacion(session: Session) -> AdjudicacionConfirmada:
    oferta = session.scalars(select(Oferta)).one()
    c = session.get(Convocatoria, oferta.convocatoria_id)
    assert c is not None
    return AdjudicacionConfirmada(
        tipo="ADJUDICACION_CONFIRMADA",
        ocurrido_en=ALERTA + timedelta(hours=3),
        convocatoria_numero=c.numero,
        adjudicacion_ref="reserva-confirmada-1",
        alerta_en=ALERTA,
        aportes=[
            AporteAdjudicado(
                ong_id=oferta.ong_creadora_id,
                lote_id=p.lote_id,
                cantidad=p.cantidad_publicada,
                plazo_en=ALERTA + timedelta(hours=5),
            )
            for p in session.scalars(
                select(ConvocatoriaLote).where(ConvocatoriaLote.convocatoria_id == c.id)
            )
        ],
    )


def guardar(
    session: Session,
    clave: str,
    datos: AdjudicacionConfirmada
    | FinalizacionOng
    | ResolucionEmergencia
    | DecisionConvocatoria
    | ValidacionNacional,
) -> HechoMonitoreo:
    c = session.scalars(select(Convocatoria)).one()
    return registrar_hecho(
        session, c.emergencia_id, 4242, RegistroHecho(clave=clave, datos=datos)
    )


def cerrar(session: Session, a: AdjudicacionConfirmada, parcial: bool = False) -> None:
    for ong_id in {p.ong_id for p in a.aportes}:
        guardar(
            session,
            f"final-{ong_id}",
            FinalizacionOng(
                tipo="FINALIZACION_ONG",
                ocurrido_en=ALERTA + timedelta(hours=4),
                convocatoria_numero=a.convocatoria_numero,
                adjudicacion_ref=a.adjudicacion_ref,
                ong_id=ong_id,
            ),
        )
    guardar(
        session,
        "cierre",
        ResolucionEmergencia(
            tipo="RESOLUCION_EMERGENCIA",
            ocurrido_en=ALERTA + timedelta(hours=6),
            convocatoria_numero=a.convocatoria_numero,
            alerta_en=ALERTA,
            plazo_en=ALERTA + timedelta(hours=7),
            cobertura=[
                CantidadCumplida(
                    lote_id=p.lote_id, cantidad=p.cantidad / (2 if parcial else 1)
                )
                for p in a.aportes
            ],
        ),
    )


def test_seis_indicadores_cruzan_hechos_y_negocio_sin_confundir_ofrecido(
    escenario: Session,
) -> None:
    a = adjudicacion(escenario)
    guardar(
        escenario,
        "decision",
        DecisionConvocatoria(
            tipo="DECISION_CONVOCATORIA",
            ocurrido_en=ALERTA + timedelta(hours=2),
            convocatoria_numero=a.convocatoria_numero,
            decision="REFORMULAR",
            motivo="Necesidades actualizadas",
        ),
    )
    guardar(
        escenario,
        "validacion",
        ValidacionNacional(
            tipo="VALIDACION_NACIONAL",
            ocurrido_en=ALERTA + timedelta(hours=2),
            convocatoria_numero=a.convocatoria_numero,
            validacion_ref="validacion-1",
            resultados=[
                ResultadoValidacion(
                    ong_id=p.ong_id,
                    lote_id=p.lote_id,
                    habilitada=i == 0,
                    motivos=[] if i == 0 else ["ACREDITACION_VENCIDA"],
                )
                for i, p in enumerate(a.aportes)
            ],
        ),
    )
    guardar(escenario, "adjudicacion", a)
    cerrar(escenario, a)
    reporte = obtener_indicadores(escenario, FILTROS)
    fila = next(r for r in reporte.resolucion_por_gravedad if r.cierres_confirmados)
    assert fila.promedio_segundos == 6 * 3600
    assert fila.tasa_en_termino == 100
    assert reporte.alerta_adjudicacion_promedio_segundos == 3 * 3600
    assert reporte.alerta_adjudicacion_muestras == 1
    assert reporte.reiteradas[0].reformulaciones == 1
    assert reporte.cobertura_cierres.proporcion_total == 100
    assert {r.unidad: r.cantidad for r in reporte.ranking_ongs} == {
        p.unidad_publicada.lower(): p.cantidad_publicada
        for p in escenario.scalars(select(ConvocatoriaLote))
    }
    assert all(r.tasa_cumplimiento == 100 for r in reporte.ranking_ongs)
    assert {r.unidad: r.cantidad for r in reporte.demanda_rubros} == {
        p.unidad_publicada.lower(): p.cantidad_publicada
        for p in escenario.scalars(select(ConvocatoriaLote))
    }
    assert all(
        r.model_dump().keys() == {"capacidad", "unidad", "cantidad"}
        for r in reporte.demanda_rubros
    )
    assert reporte.emergencias_con_hechos == reporte.emergencias_sin_hechos == 1


def test_reintento_no_duplica_y_conflictos_no_reescriben_historia(
    escenario: Session,
) -> None:
    a = adjudicacion(escenario)
    primero = guardar(escenario, "adjudicacion", a)
    assert guardar(escenario, "adjudicacion", a).id == primero.id
    for clave, datos in [
        ("otra-clave", a),
        ("adjudicacion", a.model_copy(update={"adjudicacion_ref": "otra-reserva"})),
    ]:
        with pytest.raises(HechoInvalidoError):
            guardar(escenario, clave, datos)
    assert escenario.scalar(select(func.count()).select_from(HechoMonitoreo)) == 1


def test_rechaza_cierre_prematuro_y_cobertura_imposible(escenario: Session) -> None:
    a = adjudicacion(escenario)
    guardar(escenario, "adjudicacion", a)
    cierre = ResolucionEmergencia(
        tipo="RESOLUCION_EMERGENCIA",
        ocurrido_en=ALERTA + timedelta(hours=6),
        convocatoria_numero=a.convocatoria_numero,
        alerta_en=ALERTA,
        cobertura=[
            CantidadCumplida(lote_id=p.lote_id, cantidad=p.cantidad) for p in a.aportes
        ],
    )
    with pytest.raises(HechoInvalidoError, match="finalización"):
        guardar(escenario, "cierre", cierre)
    guardar(
        escenario,
        "final",
        FinalizacionOng(
            tipo="FINALIZACION_ONG",
            ocurrido_en=ALERTA + timedelta(hours=4),
            convocatoria_numero=a.convocatoria_numero,
            adjudicacion_ref=a.adjudicacion_ref,
            ong_id=a.aportes[0].ong_id,
        ),
    )
    cierre.cobertura[0].cantidad += Decimal(1)
    with pytest.raises(HechoInvalidoError, match="exceder"):
        guardar(escenario, "cierre", cierre)


def test_cobertura_parcial_y_falta_de_sla_no_se_convierten_en_ceros(
    escenario: Session,
) -> None:
    a = adjudicacion(escenario)
    for aporte in a.aportes:
        aporte.plazo_en = None
    guardar(escenario, "adjudicacion", a)
    cerrar(escenario, a, parcial=True)
    reporte = obtener_indicadores(escenario, FILTROS)
    assert reporte.cobertura_cierres.proporcion_parcial == 100
    assert all(r.tasa_cumplimiento is None for r in reporte.ranking_ongs)
    vacio = obtener_indicadores(
        escenario, FILTROS.model_copy(update={"municipio_id": 999999})
    )
    assert vacio.alerta_adjudicacion_promedio_segundos is None
    assert vacio.cobertura_cierres.proporcion_total is None
    assert all(r.tasa_en_termino is None for r in vacio.resolucion_por_gravedad)


def test_ranking_distribuye_consorcio_y_mide_cada_ong_independientemente(
    escenario: Session,
) -> None:
    a = adjudicacion(escenario)
    oferta = escenario.scalars(select(Oferta)).one()
    otra = escenario.scalars(
        select(Organizacion).where(
            Organizacion.tipo == TipoOrganizacion.ONG,
            Organizacion.id != oferta.ong_creadora_id,
        )
    ).first()
    assert otra is not None
    version = oferta.versiones[0]
    escenario.add(
        OfertaVersionParticipante(
            oferta_version_id=version.id,
            ong_id=otra.id,
            nombre_ong=otra.nombre,
            rol=TipoParticipacion.MIEMBRO,
            confirmada_en=ALERTA,
        )
    )
    for aporte in a.aportes:
        aporte.cantidad /= 2
    a.aportes.extend(
        [p.model_copy(update={"ong_id": otra.id}) for p in list(a.aportes)]
    )
    guardar(escenario, "adjudicacion", a)
    guardar(
        escenario,
        "final",
        FinalizacionOng(
            tipo="FINALIZACION_ONG",
            ocurrido_en=ALERTA + timedelta(hours=6),
            convocatoria_numero=a.convocatoria_numero,
            adjudicacion_ref=a.adjudicacion_ref,
            ong_id=otra.id,
        ),
    )
    reporte = obtener_indicadores(escenario, FILTROS)
    assert all(
        r.finalizados == r.aportes and r.tasa_cumplimiento == 0
        for r in reporte.ranking_ongs
        if r.ong_id == otra.id
    )
    assert all(
        r.finalizados == 0 and r.tasa_cumplimiento is None
        for r in reporte.ranking_ongs
        if r.ong_id != otra.id
    )


def test_rechaza_ong_ajena_lote_ajeno_fechas_y_cantidad_excesiva(
    escenario: Session,
) -> None:
    a = adjudicacion(escenario)
    for cambio in [
        {"ong_id": 999999},
        {"lote_id": 999999},
        {"cantidad": a.aportes[0].cantidad + 1},
    ]:
        alterada = a.model_copy(deep=True)
        alterada.aportes[0] = alterada.aportes[0].model_copy(update=cambio)
        with pytest.raises(HechoInvalidoError):
            guardar(escenario, "adjudicacion", alterada)
    with pytest.raises(ValidationError):
        AdjudicacionConfirmada.model_validate(
            {**a.model_dump(), "alerta_en": a.ocurrido_en + timedelta(hours=1)}
        )


def test_falta_de_stock_no_se_registra_como_inhabilitacion() -> None:
    with pytest.raises(ValidationError):
        ResultadoValidacion(
            ong_id=1,
            lote_id=2,
            habilitada=False,
            motivos=["DISPONIBILIDAD_INSUFICIENTE"],
        )
    with pytest.raises(ValidationError):
        ResultadoValidacion(ong_id=1, lote_id=2, habilitada=False, motivos=[])


@pytest.fixture
def client(escenario: Session) -> Iterator[TestClient]:
    def db_prueba() -> Iterator[Session]:
        yield escenario

    app.dependency_overrides[get_db] = db_prueba
    try:
        with TestClient(app) as cliente:
            yield cliente
    finally:
        app.dependency_overrides.clear()


def test_callback_exige_token_caso_y_payload_tipado(
    client: TestClient, escenario: Session
) -> None:
    a = adjudicacion(escenario)
    c = escenario.scalars(select(Convocatoria)).one()
    url = f"/api/v1/emergencias/{c.emergencia_id}/hechos-monitoreo"
    registro = RegistroHecho(clave="adjudicacion", datos=a).model_dump(mode="json")
    assert client.post(url, json=registro).status_code == 401
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "X-Bonita-Root-Process-Instance-Id": "4243",
    }
    assert client.post(url, json=registro, headers=headers).status_code == 409
    headers["X-Bonita-Root-Process-Instance-Id"] = "4242"
    assert (
        client.post(url, json={**registro, "extra": True}, headers=headers).status_code
        == 422
    )
    respuesta = client.post(url, json=registro, headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    assert client.post(url, json=registro, headers=headers).json() == respuesta.json()
    assert escenario.scalar(select(func.count()).select_from(HechoMonitoreo)) == 1
