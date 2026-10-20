"""Escenarios locales de demostración, sin inventar casos ni tiempos de Bonita."""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    EstadoConvocatoria,
    EstadoEmergencia,
    EstadoLote,
    EstadoOferta,
    GravedadEmergencia,
    Lote,
    Oferta,
    OfertaItem,
    OfertaVersion,
    OfertaVersionParticipante,
    Organizacion,
    TipoAporte,
    TipoParticipacion,
    Usuario,
)

CAPACIDADES_DEMO: tuple[tuple[str, str], ...] = (
    ("Agua potable", "litros"),
    ("Alimentos", "raciones"),
    ("Atención sanitaria", "kits"),
    ("Paramédicos", "personas"),
    ("Ambulancias", "vehículos"),
    ("Combustible", "litros"),
    ("Mantas", "unidades"),
    ("Carpas", "unidades"),
    ("Generadores", "equipos"),
    ("Bombas de agua", "equipos"),
    ("Camiones", "vehículos"),
    ("Herramientas", "kits"),
    ("Ropa de abrigo", "unidades"),
    ("Motosierras", "equipos"),
    ("Equipos de comunicación", "equipos"),
    ("Personal de logística", "personas"),
)


def _version_demo(
    session: Session,
    oferta: Oferta,
    numero: int,
    lotes: list[Lote],
    participantes: list[tuple[Organizacion, Usuario]],
    fecha: datetime,
    *,
    presentada: bool,
    fraccion: Decimal,
    confirmada: bool = True,
) -> None:
    """Conserva versiones distintas para comprobar que solo se agrega la vigente."""
    version = session.scalar(
        select(OfertaVersion).where(
            OfertaVersion.oferta_id == oferta.id, OfertaVersion.numero == numero
        )
    )
    if version is None:
        version = OfertaVersion(
            oferta_id=oferta.id,
            numero=numero,
            creada_por_usuario_id=oferta.creada_por_usuario_id,
            observaciones="Escenario local de demostración del dashboard.",
            creada_en=fecha,
        )
        session.add(version)
        session.flush()
    version.presentada_en = fecha if presentada else None
    for i, (ong, _) in enumerate(participantes):
        participante = session.get(OfertaVersionParticipante, (version.id, ong.id))
        if participante is None:
            participante = OfertaVersionParticipante(
                oferta_version_id=version.id,
                ong_id=ong.id,
                nombre_ong=ong.nombre,
                rol=TipoParticipacion.LIDER if i == 0 else TipoParticipacion.MIEMBRO,
            )
            session.add(participante)
        participante.confirmada_en = fecha if confirmada or i == 0 else None
    for lote in lotes:
        item = session.scalar(
            select(OfertaItem).where(
                OfertaItem.oferta_version_id == version.id,
                OfertaItem.lote_id == lote.id,
            )
        )
        if item is None:
            item = OfertaItem(
                oferta_version_id=version.id,
                convocatoria_id=oferta.convocatoria_id,
                lote_id=lote.id,
                tipo=TipoAporte.RECURSO,
                descripcion=f"Aporte demo de {lote.tipo_necesidad}",
                unidad=lote.unidad,
                cantidad_ofrecida=lote.cantidad_requerida * fraccion,
            )
            session.add(item)
    session.flush()


def ampliar_demo_auditoria(
    session: Session,
    municipios: list[tuple[Organizacion, Usuario]],
    centro: Organizacion,
    coordinador: Usuario,
    ongs: list[tuple[Organizacion, Usuario]],
    ahora: datetime,
) -> tuple[int, int, int]:
    """Crea diecisiete emergencias reproducibles con siete estados y seis meses de altas."""
    estados = list(EstadoEmergencia)
    gravedades = list(GravedadEmergencia)
    lotes_publicados = ofertas = 0
    for indice in range(17):
        municipio, operador = municipios[indice % len(municipios)]
        estado = estados[indice % len(estados)]
        meses = 0 if indice < 7 else 1 + (indice - 7) // 2
        numero_mes = ahora.year * 12 + ahora.month - 1 - meses
        fecha = ahora.replace(
            year=numero_mes // 12,
            month=numero_mes % 12 + 1,
            day=1,
            hour=9,
            minute=0,
            second=0,
            microsecond=0,
        )
        zona = f"Demo auditoría {indice + 1:02d} — {['Ribera', 'Sierras', 'Zona urbana'][indice % 3]}"
        emergencia = session.scalar(
            select(Emergencia).where(
                Emergencia.zona == zona, Emergencia.municipio_id == municipio.id
            )
        )
        if emergencia is None:
            emergencia = Emergencia(
                municipio_id=municipio.id,
                creada_por_usuario_id=operador.id,
                zona=zona,
                gravedad=gravedades[indice % 4],
                descripcion="Datos de demostración: seguimiento de respuesta regional.",
            )
            session.add(emergencia)
        emergencia.creada_en = fecha
        emergencia.estado = estado
        emergencia.centro_coordinador_id = (
            centro.id if estado != EstadoEmergencia.REGISTRADA else None
        )
        session.flush()
        if estado in {EstadoEmergencia.REGISTRADA, EstadoEmergencia.CANCELADA}:
            continue
        lotes: list[Lote] = []
        for posicion, (nombre, unidad) in enumerate(
            CAPACIDADES_DEMO if indice == 2 else CAPACIDADES_DEMO[:4]
        ):
            lote = session.scalar(
                select(Lote).where(
                    Lote.emergencia_id == emergencia.id, Lote.tipo_necesidad == nombre
                )
            )
            if lote is None:
                lote = Lote(
                    emergencia_id=emergencia.id,
                    creado_por_usuario_id=coordinador.id,
                    tipo_necesidad=nombre,
                    cantidad_requerida=Decimal(100 + posicion * 50),
                    unidad=unidad,
                    creado_en=fecha,
                )
                session.add(lote)
            lote.estado = (
                EstadoLote.BORRADOR
                if estado == EstadoEmergencia.EN_COORDINACION
                else EstadoLote.PUBLICADO
            )
            lotes.append(lote)
        session.flush()
        if estado == EstadoEmergencia.EN_COORDINACION:
            continue
        lotes_publicados += len(lotes)
        convocatoria = session.scalar(
            select(Convocatoria).where(
                Convocatoria.emergencia_id == emergencia.id, Convocatoria.numero == 1
            )
        )
        if convocatoria is None:
            convocatoria = Convocatoria(
                emergencia_id=emergencia.id,
                numero=1,
                publicada_en=fecha,
                cierra_en=fecha + timedelta(hours=12),
            )
            session.add(convocatoria)
        abierta = estado == EstadoEmergencia.PUBLICADA
        convocatoria.estado = (
            EstadoConvocatoria.ABIERTA if abierta else EstadoConvocatoria.CERRADA
        )
        convocatoria.publicada_en = fecha
        convocatoria.cierra_en = (
            ahora + timedelta(days=2) if abierta else fecha + timedelta(hours=12)
        )
        convocatoria.cerrada_en = None if abierta else convocatoria.cierra_en
        session.flush()
        for lote in lotes:
            if session.get(ConvocatoriaLote, (convocatoria.id, lote.id)) is None:
                session.add(
                    ConvocatoriaLote(
                        convocatoria_id=convocatoria.id,
                        lote_id=lote.id,
                        cantidad_publicada=lote.cantidad_requerida,
                        unidad_publicada=lote.unidad,
                    )
                )
        session.flush()
        conjunta = indice % 3 == 0
        pendiente = indice == 4
        creadas: list[Oferta] = []
        for posicion, (ong, representante) in enumerate(ongs):
            oferta = session.scalar(
                select(Oferta).where(
                    Oferta.convocatoria_id == convocatoria.id,
                    Oferta.ong_creadora_id == ong.id,
                )
            )
            if oferta is None:
                oferta = Oferta(
                    convocatoria_id=convocatoria.id,
                    ong_creadora_id=ong.id,
                    creada_por_usuario_id=representante.id,
                    creada_en=fecha,
                )
                session.add(oferta)
                session.flush()
            oferta.estado = (
                EstadoOferta.RETIRADA
                if indice == 10 and posicion == 1
                else EstadoOferta.PRESENTADA
            )
            oferta.version_actual = 1
            _version_demo(
                session,
                oferta,
                1,
                lotes,
                [(ong, representante)],
                fecha,
                presentada=True,
                fraccion=Decimal("0.3"),
            )
            creadas.append(oferta)
            ofertas += 1
        if conjunta or pendiente:
            lider, miembro = creadas
            lider.version_actual = 2
            _version_demo(
                session,
                lider,
                2,
                lotes,
                ongs,
                fecha + timedelta(minutes=10),
                presentada=not pendiente,
                fraccion=Decimal("0.6"),
                confirmada=not pendiente,
            )
            miembro.fusionada_en_oferta_id = lider.id if not pendiente else None
        elif indice % 2 == 0:
            creadas[0].version_actual = 2
            _version_demo(
                session,
                creadas[0],
                2,
                lotes,
                [ongs[0]],
                fecha + timedelta(minutes=5),
                presentada=True,
                fraccion=Decimal("0.5"),
            )
        session.flush()
    return 17, lotes_publicados, ofertas
