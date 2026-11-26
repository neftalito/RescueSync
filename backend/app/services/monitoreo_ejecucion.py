"""Lee las confirmaciones del flujo operativo para los indicadores."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Convocatoria, Oferta, OfertaVersion, OfertaVersionParticipante
from app.db.models.ejecucion import (
    AdjudicacionLocal,
    CierreLocal,
    ComandoBonita,
    DecisionLocal,
    EvaluacionLocal,
    FinalizacionLocal,
    OperacionNacional,
    ParticipacionLocal,
)
from app.db.models.enums import EstadoOperacion, EstadoTareaBonita
from app.schemas import ejecucion as dto


@dataclass(frozen=True)
class FinalizacionOperativa:
    informada_en: datetime
    cantidades: list[dto.CantidadFinalizada] | None


@dataclass(frozen=True)
class AdjudicacionOperativa:
    emergencia_id: int
    ronda: int
    confirmada_en: datetime
    plazos: dto.PlazosEjecucion
    cantidades: dict[tuple[int, int], Decimal]
    finalizaciones: dict[int, FinalizacionOperativa]
    por_consorcio: bool


@dataclass(frozen=True)
class CierreOperativo:
    cerrado_en: datetime
    adjudicacion: AdjudicacionOperativa


@dataclass(frozen=True)
class EjecucionMonitoreo:
    adjudicaciones: list[AdjudicacionOperativa]
    cierres: dict[int, CierreOperativo]
    decisiones: dict[tuple[int, int], str]


def obtener_ejecucion(session: Session, ids: list[int]) -> EjecucionMonitoreo:
    """Correlaciona adjudicaciones, liberaciones y cierres confirmados."""
    if not ids:
        return EjecucionMonitoreo([], {}, {})
    decisiones = {
        (eid, ronda): dto.DecisionResponse.model_validate(contenido).accion.value
        for eid, ronda, contenido in session.execute(
            select(
                Convocatoria.emergencia_id, Convocatoria.numero, DecisionLocal.contenido
            )
            .select_from(DecisionLocal)
            .join(ComandoBonita, ComandoBonita.id == DecisionLocal.id)
            .join(EvaluacionLocal, EvaluacionLocal.id == DecisionLocal.evaluacion_id)
            .join(Convocatoria, Convocatoria.id == EvaluacionLocal.convocatoria_id)
            .where(
                Convocatoria.emergencia_id.in_(ids),
                ComandoBonita.estado == EstadoTareaBonita.COMPLETADA,
            )
            .order_by(EvaluacionLocal.revision)
        )
    }
    confirmadas = session.execute(
        select(AdjudicacionLocal, Convocatoria, OperacionNacional.confirmacion)
        .join(Convocatoria, Convocatoria.id == AdjudicacionLocal.convocatoria_id)
        .join(OperacionNacional, OperacionNacional.id == AdjudicacionLocal.operacion_id)
        .where(
            Convocatoria.emergencia_id.in_(ids),
            AdjudicacionLocal.estado == "CONFIRMADA",
            OperacionNacional.estado == EstadoOperacion.CONFIRMADA,
        )
    ).all()
    if not confirmadas:
        return EjecucionMonitoreo([], {}, decisiones)

    participantes: dict[UUID, dict[UUID, int]] = defaultdict(dict)
    finalizaciones: dict[UUID, dict[int, FinalizacionOperativa]] = defaultdict(dict)
    for p, f in session.execute(
        select(ParticipacionLocal, FinalizacionLocal)
        .outerjoin(
            FinalizacionLocal,
            FinalizacionLocal.participacion_id == ParticipacionLocal.id,
        )
        .where(
            ParticipacionLocal.adjudicacion_id.in_([a.id for a, _, _ in confirmadas])
        )
    ):
        participantes[p.adjudicacion_id][p.ong_nacional_id] = p.ong_id
        if p.estado == "LIBERADA" and f is not None:
            finalizaciones[p.adjudicacion_id][p.ong_id] = FinalizacionOperativa(
                informada_en=f.solicitada_en,
                cantidades=dto.FinalizacionRequest.model_validate(
                    f.ejecucion
                ).cantidades
                if f.ejecucion is not None
                else None,
            )

    integrantes: dict[tuple[int, int], set[int]] = defaultdict(set)
    for oferta_id, version, ong_id in session.execute(
        select(
            OfertaVersion.oferta_id,
            OfertaVersion.numero,
            OfertaVersionParticipante.ong_id,
        )
        .join(
            OfertaVersionParticipante,
            OfertaVersionParticipante.oferta_version_id == OfertaVersion.id,
        )
        .join(Oferta, Oferta.id == OfertaVersion.oferta_id)
        .where(
            Oferta.convocatoria_id.in_({c.id for _, c, _ in confirmadas}),
            OfertaVersionParticipante.confirmada_en.is_not(None),
        )
    ):
        integrantes[(oferta_id, version)].add(ong_id)

    adjudicaciones: dict[UUID, AdjudicacionOperativa] = {}
    for a, c, contenido in confirmadas:
        confirmacion = dto.ConfirmarCompromisosRequest.model_validate(contenido)
        cantidades: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
        seleccionadas: dict[tuple[int, int], set[int]] = defaultdict(set)
        for compromiso in confirmacion.compromisos:
            ong_id = participantes[a.id][compromiso.ong_nacional_id]
            for item in compromiso.items:
                cantidades[ong_id, int(item.lote_id)] += item.cantidad
                seleccionadas[int(item.oferta_id), item.version].add(ong_id)
        plazos = dto.AdjudicacionRequest.model_validate(a.seleccion)
        adjudicaciones[a.id] = AdjudicacionOperativa(
            emergencia_id=c.emergencia_id,
            ronda=c.numero,
            confirmada_en=confirmacion.confirmacion.registrado_en,
            plazos=plazos,
            cantidades=cantidades,
            finalizaciones=finalizaciones[a.id],
            por_consorcio=any(
                len(ongs & integrantes[oferta]) >= 2
                for oferta, ongs in seleccionadas.items()
            ),
        )
    cierres = {
        adjudicaciones[adjudicacion_id].emergencia_id: CierreOperativo(
            cerrado_en=dto.ConfirmacionCierre.model_validate(contenido).cerrado_en,
            adjudicacion=adjudicaciones[adjudicacion_id],
        )
        for adjudicacion_id, contenido in session.execute(
            select(CierreLocal.adjudicacion_id, OperacionNacional.confirmacion)
            .join(OperacionNacional, OperacionNacional.id == CierreLocal.operacion_id)
            .where(
                CierreLocal.adjudicacion_id.in_(adjudicaciones),
                OperacionNacional.estado == EstadoOperacion.CONFIRMADA,
            )
        )
    }
    return EjecucionMonitoreo(list(adjudicaciones.values()), cierres, decisiones)
