"""Forma el contrato ampliado desde snapshots locales, sin completar referencias."""

from app.db.models import Oferta, OfertaVersion
from app.schemas.bonita import (
    AporteConsolidado,
    CodigoMotivoIntegracion,
    ItemOfertaConsolidado,
    LoteConsolidado,
    MotivoIntegracion,
    OfertaConsolidada,
    OfertasConsolidadasResponse,
    ParticipanteConsolidado,
)
from app.services.callbacks_bonita import OfertasConsolidadas


def _oferta(oferta: Oferta, version: OfertaVersion) -> OfertaConsolidada:
    assert version.presentada_en is not None
    motivos: list[MotivoIntegracion] = []
    participantes = sorted(version.participantes, key=lambda p: (p.rol, p.ong_id))
    if not participantes:
        motivos.append(
            MotivoIntegracion(
                codigo=CodigoMotivoIntegracion.PARTICIPANTES_NO_VERSIONADOS,
                mensaje="La versión anterior no conserva participantes nacionales.",
                oferta_id=oferta.id,
                version=version.numero,
            )
        )
    for p in participantes:
        if p.ong_nacional_id is None:
            motivos.append(
                MotivoIntegracion(
                    codigo=CodigoMotivoIntegracion.ONG_NACIONAL_NO_ASOCIADA,
                    mensaje="La participante no tenía identidad nacional asociada.",
                    oferta_id=oferta.id,
                    version=version.numero,
                    ong_id=p.ong_id,
                )
            )
    nacionales = {p.ong_id: p.ong_nacional_id for p in participantes}
    items: list[ItemOfertaConsolidado] = []
    for item in sorted(version.items, key=lambda i: (i.lote_id, i.id)):
        if not item.aportes:
            motivos.append(
                MotivoIntegracion(
                    codigo=CodigoMotivoIntegracion.DESGLOSE_NACIONAL_AUSENTE,
                    mensaje="El ítem anterior no contiene recursos nacionales desglosados.",
                    oferta_id=oferta.id,
                    version=version.numero,
                    lote_id=item.lote_id,
                    item_id=item.id,
                )
            )
        items.append(
            ItemOfertaConsolidado(
                item_id=item.id,
                lote_id=item.lote_id,
                tipo=item.tipo,
                descripcion=item.descripcion,
                cantidad_ofrecida=item.cantidad_ofrecida,
                cantidad_ofrecida_exacta=item.cantidad_ofrecida,
                unidad=item.unidad,
                aportes=[
                    AporteConsolidado(
                        aporte_id=a.id,
                        ong_id=a.ong_id,
                        ong_nacional_id=nacionales.get(a.ong_id),
                        recurso_nacional_id=a.recurso_nacional_id,
                        capacidad_nacional_id=a.capacidad_nacional_id,
                        cantidad=a.cantidad,
                        unidad=a.unidad,
                    )
                    for a in sorted(
                        item.aportes,
                        key=lambda a: (a.ong_id, a.recurso_nacional_id, a.id),
                    )
                ],
            )
        )
    return OfertaConsolidada(
        oferta_id=oferta.id,
        ong_id=oferta.ong_creadora_id,
        ong_nacional_id=nacionales.get(oferta.ong_creadora_id),
        estado=oferta.estado,
        version=version.numero,
        presentada_en=version.presentada_en,
        items=items,
        participantes=[
            ParticipanteConsolidado(
                ong_id=p.ong_id, ong_nacional_id=p.ong_nacional_id, rol=p.rol
            )
            for p in participantes
        ],
        referencias_nacionales_completas=not motivos,
        motivos_integracion=motivos,
    )


def respuesta_consolidada(
    consolidado: OfertasConsolidadas, case_id: int
) -> OfertasConsolidadasResponse:
    """La cobertura legacy conserva su semántica numérica; T31 evalúa competencia."""
    convocatoria = consolidado.convocatoria
    motivos: list[MotivoIntegracion] = []
    if convocatoria.sistema_origen_ref is None:
        motivos.append(
            MotivoIntegracion(
                codigo=CodigoMotivoIntegracion.SISTEMA_ORIGEN_NO_ASOCIADO,
                mensaje="La convocatoria anterior no identifica la instalación nacional.",
            )
        )
    if convocatoria.gravedad_publicada is None:
        motivos.append(
            MotivoIntegracion(
                codigo=CodigoMotivoIntegracion.RIESGO_PUBLICADO_AUSENTE,
                mensaje="La convocatoria anterior no conserva gravedad publicada.",
            )
        )
    lotes: list[LoteConsolidado] = []
    for cobertura in consolidado.lotes:
        publicacion = cobertura.publicacion
        if publicacion.capacidad_nacional_id is None:
            motivos.append(
                MotivoIntegracion(
                    codigo=CodigoMotivoIntegracion.CAPACIDAD_NACIONAL_NO_ASOCIADA,
                    mensaje="El lote publicado no tiene capacidad nacional asociada.",
                    lote_id=publicacion.lote_id,
                )
            )
        if publicacion.riesgo_requerido_publicado is None:
            motivos.append(
                MotivoIntegracion(
                    codigo=CodigoMotivoIntegracion.RIESGO_PUBLICADO_AUSENTE,
                    mensaje="El lote anterior no conserva riesgo publicado.",
                    lote_id=publicacion.lote_id,
                )
            )
        lotes.append(
            LoteConsolidado(
                lote_id=cobertura.lote.id,
                tipo_necesidad=cobertura.lote.tipo_necesidad,
                cantidad_publicada=publicacion.cantidad_publicada,
                cantidad_publicada_exacta=publicacion.cantidad_publicada,
                cantidad_ofrecida=cobertura.cantidad_ofrecida,
                cantidad_ofrecida_exacta=cobertura.cantidad_ofrecida,
                unidad=publicacion.unidad_publicada,
                cubierto=cobertura.cubierto,
                capacidad_nacional_id=publicacion.capacidad_nacional_id,
                codigo_capacidad=publicacion.codigo_capacidad_publicada,
                riesgo_requerido=publicacion.riesgo_requerido_publicado,
            )
        )
    ofertas = [_oferta(oferta, version) for oferta, version in consolidado.ofertas]
    return OfertasConsolidadasResponse(
        id_emergencia=consolidado.emergencia_id,
        convocatoria_id=convocatoria.id,
        numero=convocatoria.numero,
        lotes_cubiertos=consolidado.lotes_cubiertos,
        lotes=lotes,
        ofertas=ofertas,
        sistema_origen=convocatoria.sistema_origen_ref,
        case_id=str(case_id),
        gravedad=convocatoria.gravedad_publicada,
        cerrada_en=convocatoria.cerrada_en,
        referencias_nacionales_completas=not motivos
        and all(o.referencias_nacionales_completas for o in ofertas),
        motivos_integracion=motivos,
    )
