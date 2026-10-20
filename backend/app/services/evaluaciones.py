"""Prepara evaluaciones y correlaciona cada perfil contra el snapshot congelado."""

import hashlib
import json
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, JsonValue, TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    OfertaVersion,
    OfertaVersionParticipante,
)
from app.db.models.ejecucion import AdjudicacionLocal, EvaluacionLocal
from app.db.models.enums import EstadoConvocatoria, EstadoEmergencia
from app.schemas.bonita import OfertasConsolidadasResponse
from app.schemas.ejecucion import (
    AporteElegible,
    CoberturaLote,
    PerfilesRequest,
    PerfilesResponse,
    PreparacionResponse,
    PreparacionValidacion,
    ValidacionNacional,
    ValidacionNacionalLegacy,
)
from app.services.callbacks_bonita import consolidar_ofertas
from app.services.cobertura_validada import Requerimiento, calcular_cobertura
from app.services.consolidado_nacional import respuesta_consolidada


class IntegracionLocalError(Exception):
    """Rechazo de negocio seguro para usuarios y conectores."""

    def __init__(self, mensaje: str, status: int = 409) -> None:
        super().__init__(mensaje)
        self.status = status


def objeto(modelo: BaseModel) -> dict[str, JsonValue]:
    return json.loads(modelo.model_dump_json(by_alias=True))


def huella(contenido: dict[str, JsonValue]) -> str:
    return hashlib.sha256(
        json.dumps(
            contenido, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def bloquear_emergencia(
    session: Session, emergencia_id: int, case_id: int | None = None
) -> Emergencia:
    """Orden común de locks: emergencia, ronda, entidades de la operación."""
    e = session.scalar(
        select(Emergencia)
        .where(Emergencia.id == emergencia_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if e is None:
        raise IntegracionLocalError("La emergencia no existe.", 404)
    if case_id is not None and e.bonita_process_instance_id != case_id:
        raise IntegracionLocalError("El caso de Bonita no corresponde a la emergencia.")
    return e


def ultima_ronda(session: Session, emergencia_id: int) -> Convocatoria:
    c = session.scalar(
        select(Convocatoria)
        .where(Convocatoria.emergencia_id == emergencia_id)
        .order_by(Convocatoria.numero.desc())
        .limit(1)
        .with_for_update()
    )
    if c is None:
        raise IntegracionLocalError("No hay una convocatoria para evaluar.")
    return c


def ultima_evaluacion(session: Session, convocatoria_id: int) -> EvaluacionLocal | None:
    return session.scalar(
        select(EvaluacionLocal)
        .where(EvaluacionLocal.convocatoria_id == convocatoria_id)
        .order_by(EvaluacionLocal.revision.desc())
        .limit(1)
    )


def leer_resultado(contenido: object) -> ValidacionNacional | ValidacionNacionalLegacy:
    """Conserva lectura histórica sin convertir acreditaciones en permisos actuales."""
    return TypeAdapter(ValidacionNacional | ValidacionNacionalLegacy).validate_python(
        contenido
    )


def vigente(session: Session, evaluacion: EvaluacionLocal) -> bool:
    c = ultima_ronda(session, evaluacion.emergencia_id)
    v = ultima_evaluacion(session, c.id)
    e = session.get(Emergencia, evaluacion.emergencia_id)
    return (
        e.estado not in (EstadoEmergencia.EN_COORDINACION, EstadoEmergencia.PUBLICADA)
        and c.id == evaluacion.convocatoria_id
        and c.estado == EstadoConvocatoria.CERRADA
        and v is not None
        and v.id == evaluacion.id
        and (
            evaluacion.resultado is None
            or evaluacion.resultado.get("contratoVersion") == 3
        )
    )


def preparar(
    session: Session, emergencia_id: int, case_id: int, datos: PreparacionValidacion
) -> PreparacionResponse:
    e = bloquear_emergencia(session, emergencia_id, case_id)
    existente = session.get(EvaluacionLocal, datos.validacion_id)
    if existente is not None:
        s = OfertasConsolidadasResponse.model_validate(existente.snapshot)
        if (
            existente.emergencia_id != emergencia_id
            or s.convocatoria_id != datos.convocatoria_id
            or s.numero != datos.intento_convocatoria
        ):
            raise IntegracionLocalError(
                "La identidad de evaluación ya tiene otro contenido."
            )
        return preparacion(existente)
    c = ultima_ronda(session, emergencia_id)
    if (
        e.estado != EstadoEmergencia.EN_EVALUACION
        or c.estado != EstadoConvocatoria.CERRADA
        or c.id != datos.convocatoria_id
        or c.numero != datos.intento_convocatoria
    ):
        raise IntegracionLocalError("La evaluación requiere la ronda cerrada vigente.")
    if session.scalar(
        select(AdjudicacionLocal.id).where(
            AdjudicacionLocal.convocatoria_id == c.id,
            AdjudicacionLocal.estado != "REQUIERE_REVISION",
        )
    ):
        raise IntegracionLocalError("Ya existe una selección pendiente o confirmada.")
    snapshot = respuesta_consolidada(
        consolidar_ofertas(
            session,
            emergencia_id=emergencia_id,
            case_id=case_id,
            intento_convocatoria=c.numero,
        ),
        case_id,
    )
    if not snapshot.sistema_origen:
        raise IntegracionLocalError(
            "La ronda no conserva el sistema de origen nacional."
        )
    if (
        len(snapshot.ofertas) > 1000
        or sum(len(i.aportes) for o in snapshot.ofertas for i in o.items) > 5000
    ):
        raise IntegracionLocalError(
            "La ronda supera el tamaño de evaluación permitido.", 422
        )
    contenido = objeto(snapshot)
    # EstadoOferta es una proyección mutable; no forma parte de la identidad.
    for oferta in contenido["ofertas"]:
        oferta.pop("estado", None)
    previa = ultima_evaluacion(session, c.id)
    v = EvaluacionLocal(
        id=datos.validacion_id,
        emergencia_id=emergencia_id,
        convocatoria_id=c.id,
        revision=1 if previa is None else previa.revision + 1,
        huella_snapshot=huella(contenido),
        snapshot=objeto(snapshot),
    )
    session.add(v)
    session.commit()
    return preparacion(v)


def preparacion(v: EvaluacionLocal) -> PreparacionResponse:
    s = OfertasConsolidadasResponse.model_validate(v.snapshot)
    return PreparacionResponse(
        validacion_id=v.id,
        convocatoria_id=v.convocatoria_id,
        intento_convocatoria=s.numero,
        revision=v.revision,
        huella_snapshot=v.huella_snapshot,
    )


def elegibles(
    session: Session,
    v: EvaluacionLocal,
    resultado: ValidacionNacional | ValidacionNacionalLegacy,
) -> list[AporteElegible]:
    """Exige el conjunto exacto de perfiles; legacy se conserva sin habilitarlo."""
    if isinstance(resultado, ValidacionNacionalLegacy):
        return []
    s = OfertasConsolidadasResponse.model_validate(v.snapshot)
    if (
        resultado.sistema_origen,
        resultado.id_emergencia,
        resultado.case_id,
        resultado.convocatoria_id,
        resultado.numero,
    ) != (s.sistema_origen, s.id_emergencia, s.case_id, s.convocatoria_id, s.numero):
        raise IntegracionLocalError(
            "El resultado nacional corresponde a otra ronda o caso."
        )
    perfiles = {
        (a.oferta_id, a.version, a.item_id, a.aporte_id): a for a in resultado.aportes
    }
    if len(perfiles) != len(resultado.aportes):
        raise IntegracionLocalError("El resultado repite perfiles.")
    esperados = {
        (o.oferta_id, o.version, i.item_id, a.aporte_id)
        for o in s.ofertas
        for i in o.items
        for a in i.aportes
    }
    esperados.update(
        (o.oferta_id, o.version, i.item_id, None)
        for o in s.ofertas
        for i in o.items
        if not i.aportes
    )
    if perfiles.keys() != esperados:
        raise IntegracionLocalError(
            "El resultado no contiene exactamente los perfiles del snapshot."
        )
    recursos = {r.recurso_nacional_id: r for r in resultado.recursos_consultados}
    if len(recursos) != len(resultado.recursos_consultados):
        raise IntegracionLocalError("El resultado repite recursos consultados.")
    demanda: dict[UUID, Decimal] = {}
    for o in s.ofertas:
        for i in o.items:
            for a in i.aportes:
                demanda[a.recurso_nacional_id] = (
                    demanda.get(a.recurso_nacional_id, Decimal(0)) + a.cantidad
                )
    if not recursos.keys() <= demanda.keys():
        raise IntegracionLocalError(
            "El resultado contiene recursos ajenos al snapshot."
        )
    for rid, r in recursos.items():
        if r.cantidad_solicitada_snapshot != demanda[rid]:
            raise IntegracionLocalError(
                "La demanda nacional no coincide con el snapshot."
            )
    publicaciones = {
        p.lote_id: p
        for p in session.scalars(
            select(ConvocatoriaLote).where(
                ConvocatoriaLote.convocatoria_id == s.convocatoria_id
            )
        )
    }
    nombres = {
        (oferta_id, version, ong_id): nombre
        for oferta_id, version, ong_id, nombre in session.execute(
            select(
                OfertaVersion.oferta_id,
                OfertaVersion.numero,
                OfertaVersionParticipante.ong_id,
                OfertaVersionParticipante.nombre_ong,
            )
            .join(
                OfertaVersionParticipante,
                OfertaVersionParticipante.oferta_version_id == OfertaVersion.id,
            )
            .where(OfertaVersion.oferta_id.in_([o.oferta_id for o in s.ofertas]))
        )
    }
    necesidades = {l.lote_id: l.tipo_necesidad for l in s.lotes}
    salida: list[AporteElegible] = []
    for o in s.ofertas:
        for i in o.items:
            if not i.aportes:
                p = perfiles[o.oferta_id, o.version, i.item_id, None]
                if (
                    p.lote_id,
                    p.ong_id,
                    p.ong_nacional_id,
                    p.recurso_nacional_id,
                    p.cantidad_ofrecida,
                    p.unidad,
                ) != (
                    i.lote_id,
                    o.ong_id,
                    o.ong_nacional_id,
                    None,
                    i.cantidad_ofrecida_exacta,
                    i.unidad,
                ):
                    raise IntegracionLocalError(
                        "El diagnóstico legacy no corresponde al ítem."
                    )
            for a in i.aportes:
                p = perfiles[o.oferta_id, o.version, i.item_id, a.aporte_id]
                if (
                    p.lote_id,
                    p.ong_id,
                    p.ong_nacional_id,
                    p.recurso_nacional_id,
                    p.cantidad_ofrecida,
                    p.unidad,
                ) != (
                    i.lote_id,
                    a.ong_id,
                    a.ong_nacional_id,
                    a.recurso_nacional_id,
                    a.cantidad,
                    a.unidad,
                ):
                    raise IntegracionLocalError(
                        "Un perfil alteró las referencias o cantidades congeladas."
                    )
                if (
                    p.perfil_competencia is not None
                    and p.perfil_competencia.ong_id != a.ong_nacional_id
                ):
                    raise IntegracionLocalError(
                        "El perfil informativo pertenece a otra ONG."
                    )
                r = recursos.get(a.recurso_nacional_id)
                pub = publicaciones[i.lote_id]
                if (
                    r is not None
                    and p.cantidad_disponible_consultada is not None
                    and p.cantidad_disponible_consultada != r.cantidad_disponible
                ):
                    raise IntegracionLocalError(
                        "La disponibilidad repetida es contradictoria."
                    )
                if (
                    any(m.codigo != "DISPONIBILIDAD_INSUFICIENTE" for m in p.motivos)
                    or r is None
                    or a.ong_nacional_id is None
                    or p.cantidad_disponible_consultada is None
                    or (r.ong_nacional_id, r.capacidad_nacional_id, r.unidad)
                    != (a.ong_nacional_id, a.capacidad_nacional_id, a.unidad)
                    or (a.capacidad_nacional_id, a.unidad)
                    != (pub.capacidad_nacional_id, pub.unidad_publicada)
                    or pub.admite_fracciones_publicada is None
                    or (
                        not pub.admite_fracciones_publicada
                        and (a.cantidad % 1 != 0 or pub.cantidad_publicada % 1 != 0)
                    )
                ):
                    continue
                salida.append(
                    AporteElegible(
                        descripcion=i.descripcion,
                        nombre_ong=nombres.get(
                            (o.oferta_id, o.version, a.ong_id), f"ONG {a.ong_id}"
                        ),
                        tipo_necesidad=necesidades[i.lote_id],
                        aporte_id=a.aporte_id,
                        oferta_id=o.oferta_id,
                        version=o.version,
                        lote_id=i.lote_id,
                        ong_id=a.ong_id,
                        ong_nacional_id=a.ong_nacional_id,
                        recurso_nacional_id=a.recurso_nacional_id,
                        capacidad_nacional_id=a.capacidad_nacional_id,
                        riesgo_requerido=pub.riesgo_requerido_publicado,
                        cantidad_ofrecida=a.cantidad,
                        cantidad_disponible=r.cantidad_disponible,
                        unidad=a.unidad,
                        admite_fracciones=pub.admite_fracciones_publicada,
                        perfil_competencia=p.perfil_competencia,
                    )
                )
    return salida


def guardar_perfiles(
    session: Session, emergencia_id: int, case_id: int, datos: PerfilesRequest
) -> PerfilesResponse:
    bloquear_emergencia(session, emergencia_id, case_id)
    v = session.get(EvaluacionLocal, datos.validacion_id)
    if (
        v is None
        or v.emergencia_id != emergencia_id
        or preparacion(v)
        != PreparacionResponse.model_validate(datos.model_dump(exclude={"validacion"}))
    ):
        raise IntegracionLocalError(
            "No corresponde a la solicitud de evaluación preparada."
        )
    contenido = objeto(datos.validacion)
    if v.resultado is not None:
        if huella(v.resultado) != huella(contenido):
            raise IntegracionLocalError("La evaluación ya recibió otro resultado.")
        return confirmacion(session, v)
    if not vigente(session, v):
        raise IntegracionLocalError(
            "La evaluación fue reemplazada; preparar una nueva evaluación."
        )
    aportes = elegibles(session, v, datos.validacion)
    s = OfertasConsolidadasResponse.model_validate(v.snapshot)
    cobertura = calcular_cobertura(
        [
            Requerimiento(l.lote_id, l.cantidad_publicada_exacta, l.unidad)
            for l in s.lotes
        ],
        aportes,
    )
    v.resultado = contenido
    v.cobertura = {"lotes": [objeto(c) for c in cobertura]}
    session.commit()
    return confirmacion(session, v)


def confirmacion(session: Session, v: EvaluacionLocal) -> PerfilesResponse:
    if v.resultado is None or v.cobertura is None:
        raise IntegracionLocalError("La evaluación aún no tiene resultado confirmado.")
    r = leer_resultado(v.resultado)
    cobertura = [CoberturaLote.model_validate(c) for c in v.cobertura["lotes"]]
    return PerfilesResponse(
        **preparacion(v).model_dump(),
        evaluado_en=r.evaluado_en,
        vigente=vigente(session, v),
        lotes_compatibles_cubiertos=bool(cobertura)
        and all(c.faltante == 0 for c in cobertura),
        cobertura=cobertura,
    )
