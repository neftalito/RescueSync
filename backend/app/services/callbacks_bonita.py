"""Casos de uso que ejecuta Bonita sobre la base local mediante callbacks HTTP.

Bonita administra la ventana de ofertas; PostgreSQL sigue siendo la fuente de
verdad. `intentoConvocatoria` del proceso corresponde a `Convocatoria.numero`.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    EstadoConvocatoria,
    EstadoEmergencia,
    EstadoOferta,
    Lote,
    Oferta,
    OfertaVersion,
)
from app.services.notificaciones import notificar_convocatoria_cerrada

ESTADOS_OFERTA_NO_CONSOLIDABLES = frozenset(
    {EstadoOferta.BORRADOR, EstadoOferta.RETIRADA}
)


class CallbackBonitaError(Exception):
    """Rechazo de un callback con un mensaje apto para devolver a Bonita."""


class EmergenciaNoEncontradaError(CallbackBonitaError):
    """La emergencia indicada no existe."""


class CasoBonitaNoCorrespondeError(CallbackBonitaError):
    """El caso que llama no es el vinculado a la emergencia."""


class ConvocatoriaNoEncontradaError(CallbackBonitaError):
    """No existe la convocatoria esperada por el proceso."""


class EstadoConvocatoriaInvalidoError(CallbackBonitaError):
    """La convocatoria no admite la transición pedida."""


class FechaCierreInvalidaError(CallbackBonitaError):
    """La fecha de cierre calculada por Bonita no es posterior a la publicación."""


@dataclass(frozen=True)
class CoberturaLote:
    """Cantidad publicada de un lote frente a lo ofrecido en la misma unidad."""

    publicacion: ConvocatoriaLote
    lote: Lote
    cantidad_ofrecida: Decimal

    @property
    def cubierto(self) -> bool:
        return self.cantidad_ofrecida >= self.publicacion.cantidad_publicada


@dataclass(frozen=True)
class OfertasConsolidadas:
    """Resultado de consolidar una convocatoria cerrada."""

    emergencia_id: int
    convocatoria: Convocatoria
    lotes: tuple[CoberturaLote, ...]
    ofertas: tuple[tuple[Oferta, OfertaVersion], ...]

    @property
    def lotes_cubiertos(self) -> bool:
        return bool(self.lotes) and all(lote.cubierto for lote in self.lotes)


def _verificar_caso(session: Session, emergencia_id: int, case_id: int) -> Emergencia:
    """Impide que un caso actúe sobre una emergencia que no le pertenece."""

    emergencia = session.get(Emergencia, emergencia_id)
    if emergencia is None:
        raise EmergenciaNoEncontradaError("La emergencia no existe.")
    if emergencia.bonita_process_instance_id != case_id:
        raise CasoBonitaNoCorrespondeError(
            "El caso de Bonita no está vinculado a esta emergencia."
        )
    return emergencia


def _convocatoria_bloqueada(
    session: Session, emergencia_id: int, numero: int
) -> Convocatoria:
    convocatoria = session.scalar(
        select(Convocatoria)
        .where(
            Convocatoria.emergencia_id == emergencia_id,
            Convocatoria.numero == numero,
        )
        .with_for_update()
    )
    if convocatoria is None:
        raise ConvocatoriaNoEncontradaError(
            f"No existe la convocatoria {numero} de la emergencia."
        )
    return convocatoria


def registrar_apertura(
    session: Session,
    *,
    emergencia_id: int,
    case_id: int,
    numero: int,
    cierra_en: datetime,
) -> Convocatoria:
    """Alinea el cierre local con la fecha del timer de Bonita.

    Es idempotente: repetir el callback con los mismos datos no cambia nada.
    """

    _verificar_caso(session, emergencia_id, case_id)
    convocatoria = _convocatoria_bloqueada(session, emergencia_id, numero)
    if convocatoria.estado is not EstadoConvocatoria.ABIERTA:
        raise EstadoConvocatoriaInvalidoError(
            f"La convocatoria {numero} está {convocatoria.estado}."
        )
    cierre_utc = cierra_en.astimezone(UTC)
    if cierre_utc <= convocatoria.publicada_en:
        raise FechaCierreInvalidaError(
            "La fecha de cierre debe ser posterior a la publicación."
        )

    convocatoria.cierra_en = cierre_utc
    session.commit()
    return convocatoria


def cerrar_convocatoria(
    session: Session,
    *,
    emergencia_id: int,
    case_id: int,
    numero: int,
    ahora: datetime,
) -> Convocatoria:
    """Cierra la convocatoria para que no ingresen más ofertas.

    Es idempotente para tolerar reintentos del conector.
    """

    emergencia = _verificar_caso(session, emergencia_id, case_id)
    convocatoria = _convocatoria_bloqueada(session, emergencia_id, numero)
    if convocatoria.estado is EstadoConvocatoria.CERRADA:
        return convocatoria
    if convocatoria.estado is not EstadoConvocatoria.ABIERTA:
        raise EstadoConvocatoriaInvalidoError(
            f"La convocatoria {numero} está {convocatoria.estado}."
        )

    convocatoria.estado = EstadoConvocatoria.CERRADA
    convocatoria.cerrada_en = ahora
    emergencia.estado = EstadoEmergencia.EN_EVALUACION
    notificar_convocatoria_cerrada(
        session,
        convocatoria_id=convocatoria.id,
        municipio_id=emergencia.municipio_id,
        zona=emergencia.zona,
    )
    session.commit()
    return convocatoria


def consolidar_ofertas(
    session: Session,
    *,
    emergencia_id: int,
    case_id: int,
) -> OfertasConsolidadas:
    """Consolida las ofertas presentadas en la última convocatoria cerrada.

    Solo usa la versión vigente de cada oferta y excluye borradores y retiradas.
    Una cantidad cuenta para la cobertura únicamente si usa la unidad publicada.
    """

    _verificar_caso(session, emergencia_id, case_id)
    convocatoria = session.scalar(
        select(Convocatoria)
        .where(Convocatoria.emergencia_id == emergencia_id)
        .order_by(Convocatoria.numero.desc())
        .limit(1)
    )
    if convocatoria is None:
        raise ConvocatoriaNoEncontradaError("La emergencia no tiene convocatorias.")
    if convocatoria.estado is not EstadoConvocatoria.CERRADA:
        raise EstadoConvocatoriaInvalidoError(
            f"La convocatoria {convocatoria.numero} debe cerrarse antes de "
            "consolidar sus ofertas."
        )

    publicaciones = session.execute(
        select(ConvocatoriaLote, Lote)
        .join(Lote, Lote.id == ConvocatoriaLote.lote_id)
        .where(ConvocatoriaLote.convocatoria_id == convocatoria.id)
        .order_by(Lote.id)
    ).all()
    ofertas = tuple(
        (oferta, version)
        for oferta, version in session.execute(
            select(Oferta, OfertaVersion)
            .join(
                OfertaVersion,
                and_(
                    OfertaVersion.oferta_id == Oferta.id,
                    OfertaVersion.numero == Oferta.version_actual,
                ),
            )
            .where(
                Oferta.convocatoria_id == convocatoria.id,
                Oferta.estado.not_in(ESTADOS_OFERTA_NO_CONSOLIDABLES),
                OfertaVersion.presentada_en.is_not(None),
            )
            .options(selectinload(OfertaVersion.items))
            .order_by(Oferta.id)
        ).all()
    )

    ofrecido: dict[tuple[int, str], Decimal] = {}
    for _, version in ofertas:
        for item in version.items:
            clave = (item.lote_id, _normalizar_unidad(item.unidad))
            ofrecido[clave] = ofrecido.get(clave, Decimal(0)) + item.cantidad_ofrecida

    lotes = tuple(
        CoberturaLote(
            publicacion=publicacion,
            lote=lote,
            cantidad_ofrecida=ofrecido.get(
                (lote.id, _normalizar_unidad(publicacion.unidad_publicada)),
                Decimal(0),
            ),
        )
        for publicacion, lote in publicaciones
    )
    return OfertasConsolidadas(
        emergencia_id=emergencia_id,
        convocatoria=convocatoria,
        lotes=lotes,
        ofertas=ofertas,
    )


def _normalizar_unidad(unidad: str) -> str:
    return unidad.strip().casefold()
