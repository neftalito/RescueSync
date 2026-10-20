"""Valida y conserva evidencia BPM sin ejecutar transiciones del negocio."""

from datetime import UTC, datetime

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    EstadoConvocatoria,
    EstadoOferta,
    HechoMonitoreo,
    Oferta,
    OfertaVersion,
    OfertaVersionParticipante,
)
from app.schemas.monitoreo import (
    AdjudicacionConfirmada,
    DatosHecho,
    DecisionConvocatoria,
    FinalizacionOng,
    RegistroHecho,
    ResolucionEmergencia,
    ValidacionNacional,
)

ADAPTADOR_HECHO = TypeAdapter(DatosHecho)


class HechoInvalidoError(Exception):
    """La evidencia no corresponde al caso, ronda o antecedentes registrados."""


def referencia_hecho(datos: DatosHecho) -> str:
    """Impide contar dos veces un mismo hecho usando claves de transporte distintas."""
    if isinstance(datos, DecisionConvocatoria):
        return f"decision:{datos.convocatoria_numero}"
    if isinstance(datos, ValidacionNacional):
        return f"validacion:{datos.validacion_ref}"
    if isinstance(datos, AdjudicacionConfirmada):
        return f"adjudicacion:{datos.adjudicacion_ref}"
    if isinstance(datos, FinalizacionOng):
        return f"finalizacion:{datos.adjudicacion_ref}:{datos.ong_id}"
    return "resolucion"


def registrar_hecho(
    session: Session,
    emergencia_id: int,
    case_id: int,
    registro: RegistroHecho,
) -> HechoMonitoreo:
    """Serializa por emergencia y rechaza reintentos con contenido modificado.

    El emisor debe enviar exclusivamente confirmaciones, nunca intenciones ni
    resultados HTTP inciertos. Este registro no reserva recursos ni resuelve casos.
    """
    emergencia = session.scalar(
        select(Emergencia).where(Emergencia.id == emergencia_id).with_for_update()
    )
    if emergencia is None or emergencia.bonita_process_instance_id != case_id:
        raise HechoInvalidoError("La emergencia no corresponde al caso de Bonita.")
    datos = registro.datos
    payload = datos.model_dump(mode="json")
    anteriores = session.scalars(
        select(HechoMonitoreo).where(HechoMonitoreo.emergencia_id == emergencia_id)
    ).all()
    referencia = referencia_hecho(datos)
    for anterior in anteriores:
        if anterior.clave == registro.clave or anterior.referencia == referencia:
            if anterior.clave != registro.clave or anterior.datos != payload:
                raise HechoInvalidoError(
                    "El hecho ya fue registrado con otra clave o contenido."
                )
            return anterior
    if datos.ocurrido_en > datetime.now(UTC):
        raise HechoInvalidoError("El hecho confirmado no puede tener una fecha futura.")
    convocatoria = session.scalar(
        select(Convocatoria).where(
            Convocatoria.emergencia_id == emergencia_id,
            Convocatoria.numero == datos.convocatoria_numero,
        )
    )
    if convocatoria is None or datos.ocurrido_en < convocatoria.publicada_en:
        raise HechoInvalidoError(
            "La ronda no existe o el hecho precede a su publicación."
        )
    if (
        convocatoria.estado != EstadoConvocatoria.CERRADA
        or convocatoria.cerrada_en is None
        or datos.ocurrido_en < convocatoria.cerrada_en
    ):
        raise HechoInvalidoError(
            "El hecho requiere una convocatoria cerrada previamente."
        )
    publicaciones = {
        p.lote_id: p
        for p in session.scalars(
            select(ConvocatoriaLote).where(
                ConvocatoriaLote.convocatoria_id == convocatoria.id
            )
        )
    }
    ongs = set(
        session.scalars(
            select(Oferta.ong_creadora_id)
            .join(OfertaVersion, OfertaVersion.oferta_id == Oferta.id)
            .where(
                Oferta.convocatoria_id == convocatoria.id,
                OfertaVersion.numero == Oferta.version_actual,
                OfertaVersion.presentada_en.is_not(None),
                Oferta.estado.not_in([EstadoOferta.BORRADOR, EstadoOferta.RETIRADA]),
                Oferta.fusionada_en_oferta_id.is_(None),
            )
        )
    )
    ongs.update(
        session.scalars(
            select(OfertaVersionParticipante.ong_id)
            .join(
                OfertaVersion,
                OfertaVersion.id == OfertaVersionParticipante.oferta_version_id,
            )
            .join(Oferta, Oferta.id == OfertaVersion.oferta_id)
            .where(
                Oferta.convocatoria_id == convocatoria.id,
                OfertaVersion.numero == Oferta.version_actual,
                OfertaVersion.presentada_en.is_not(None),
                OfertaVersionParticipante.confirmada_en.is_not(None),
                Oferta.estado.not_in([EstadoOferta.BORRADOR, EstadoOferta.RETIRADA]),
                Oferta.fusionada_en_oferta_id.is_(None),
            )
        )
    )
    historial = [ADAPTADOR_HECHO.validate_python(h.datos) for h in anteriores]
    if any(isinstance(h, ResolucionEmergencia) for h in historial):
        raise HechoInvalidoError(
            "No se agregan hechos después de una resolución confirmada."
        )
    adjudicaciones = [h for h in historial if isinstance(h, AdjudicacionConfirmada)]
    if isinstance(datos, (AdjudicacionConfirmada, ValidacionNacional)):
        filas = (
            datos.aportes
            if isinstance(datos, AdjudicacionConfirmada)
            else datos.resultados
        )
        if any(f.lote_id not in publicaciones or f.ong_id not in ongs for f in filas):
            raise HechoInvalidoError(
                "Los lotes y ONGs deben pertenecer a la convocatoria."
            )
    if isinstance(datos, AdjudicacionConfirmada):
        if any(h.alerta_en != datos.alerta_en for h in adjudicaciones):
            raise HechoInvalidoError(
                "La alerta inicial debe coincidir con las adjudicaciones anteriores."
            )
        for aporte in datos.aportes:
            total = sum(
                a.cantidad
                for h in adjudicaciones
                for a in h.aportes
                if a.lote_id == aporte.lote_id
            )
            total += sum(
                a.cantidad for a in datos.aportes if a.lote_id == aporte.lote_id
            )
            if total > publicaciones[aporte.lote_id].cantidad_publicada:
                raise HechoInvalidoError(
                    "La cantidad adjudicada excede la necesidad publicada."
                )
    if isinstance(datos, FinalizacionOng):
        adjudicacion = next(
            (h for h in adjudicaciones if h.adjudicacion_ref == datos.adjudicacion_ref),
            None,
        )
        if (
            adjudicacion is None
            or adjudicacion.convocatoria_numero != datos.convocatoria_numero
            or not any(a.ong_id == datos.ong_id for a in adjudicacion.aportes)
            or datos.ocurrido_en < adjudicacion.ocurrido_en
        ):
            raise HechoInvalidoError(
                "La finalización debe corresponder a una participación adjudicada previa."
            )
    if isinstance(datos, ResolucionEmergencia):
        if any(h.alerta_en != datos.alerta_en for h in adjudicaciones):
            raise HechoInvalidoError(
                "La alerta inicial del cierre no coincide con la adjudicación."
            )
        ultima = session.scalar(
            select(Convocatoria.numero)
            .where(Convocatoria.emergencia_id == emergencia_id)
            .order_by(Convocatoria.numero.desc())
            .limit(1)
        )
        if ultima != datos.convocatoria_numero:
            raise HechoInvalidoError(
                "El cierre debe corresponder a la última convocatoria."
            )
        if set(publicaciones) != {c.lote_id for c in datos.cobertura}:
            raise HechoInvalidoError(
                "El cierre debe incluir todos los lotes de la ronda."
            )
        if not adjudicaciones or any(
            h.ocurrido_en > datos.ocurrido_en for h in historial
        ):
            raise HechoInvalidoError(
                "El cierre requiere adjudicaciones previas y debe ser el último hecho."
            )
        finalizaciones = {
            (h.adjudicacion_ref, h.ong_id)
            for h in historial
            if isinstance(h, FinalizacionOng)
        }
        if any(
            (h.adjudicacion_ref, a.ong_id) not in finalizaciones
            for h in adjudicaciones
            for a in h.aportes
        ):
            raise HechoInvalidoError(
                "Falta confirmar la finalización de una ONG adjudicada."
            )
        for cobertura in datos.cobertura:
            asignado = sum(
                a.cantidad
                for h in adjudicaciones
                for a in h.aportes
                if a.lote_id == cobertura.lote_id
            )
            if cobertura.cantidad > asignado:
                raise HechoInvalidoError(
                    "La cobertura cumplida no puede exceder lo adjudicado."
                )
    hecho = HechoMonitoreo(
        emergencia_id=emergencia_id,
        clave=registro.clave,
        referencia=referencia,
        datos=payload,
    )
    session.add(hecho)
    session.flush()
    return hecho
