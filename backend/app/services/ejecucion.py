"""Selección y ciclo bilateral; sólo Bonita realiza escrituras en la API nacional."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    EstadoConvocatoria,
    EstadoEmergencia,
    EstadoLote,
    EstadoOferta,
    Lote,
    Notificacion,
    Oferta,
    RolUsuario,
    TipoNotificacion,
    Usuario,
)
from app.db.models.ejecucion import (
    AdjudicacionLocal,
    CierreLocal,
    ComandoBonita,
    CompromisoLocal,
    DecisionLocal,
    EvaluacionLocal,
    FinalizacionLocal,
    OperacionNacional,
    ParticipacionLocal,
)
from app.db.models.enums import EstadoOperacion, EstadoTareaBonita, TipoOperacion
from app.integrations.bonita.contratos import (
    ContratoCierre,
    ContratoDecision,
    ContratoFinalizacion,
    ContratoRecuperacion,
    ContratoSeleccion,
)
from app.schemas import ejecucion as dto
from app.schemas.bonita import OfertasConsolidadasResponse
from app.services.evaluaciones import (
    IntegracionLocalError,
    confirmacion,
    elegibles,
    huella,
    leer_resultado,
    objeto,
    ultima_evaluacion,
    ultima_ronda,
    vigente,
)


def autorizar(e: Emergencia, usuario: Usuario, rol: RolUsuario) -> None:
    """Revalida rol, pertenencia y organización activa para cada comando."""
    esperada = (
        e.municipio_id
        if rol == RolUsuario.OPERADOR_MUNICIPAL
        else e.centro_coordinador_id
    )
    if (
        usuario.rol != rol
        or usuario.organizacion is None
        or not usuario.organizacion.activa
        or usuario.organizacion_id != esperada
    ):
        raise IntegracionLocalError("No pertenecés a la organización responsable.", 403)


def _evaluacion(
    session: Session, e: Emergencia, validacion_id: UUID, revision: int
) -> EvaluacionLocal:
    v = session.get(EvaluacionLocal, validacion_id)
    if (
        v is None
        or v.emergencia_id != e.id
        or v.revision != revision
        or v.resultado is None
        or not vigente(session, v)
        or e.estado != EstadoEmergencia.EN_EVALUACION
    ):
        raise IntegracionLocalError("Se necesita una evaluación confirmada vigente.")
    if session.scalar(
        select(AdjudicacionLocal.id).where(
            AdjudicacionLocal.convocatoria_id == v.convocatoria_id,
            AdjudicacionLocal.estado != "REQUIERE_REVISION",
        )
    ):
        raise IntegracionLocalError("Ya existe una selección pendiente o confirmada.")
    return v


def _comando(
    session: Session,
    e: Emergencia,
    usuario: Usuario,
    identidad: UUID,
    tarea: str,
    actor: str,
    correlacion: str,
    contrato: BaseModel,
) -> ComandoBonita:
    if session.get(ComandoBonita, identidad) is not None:
        raise IntegracionLocalError("El identificador ya pertenece a otra intención.")
    c = ComandoBonita(
        id=identidad,
        emergencia_id=e.id,
        usuario_id=usuario.id,
        tarea=tarea,
        actor=actor,
        correlacion=correlacion,
        contrato=objeto(contrato),
    )
    session.add(c)
    session.flush()
    return c


def _operacion(
    session: Session, e: Emergencia, tipo: TipoOperacion, request: dto.Contrato
) -> OperacionNacional:
    identidad = uuid4()
    contenido = objeto(request)
    op = OperacionNacional(
        id=identidad,
        emergencia_id=e.id,
        tipo=tipo,
        clave=str(identidad),
        huella=huella(contenido),
        request=contenido,
    )
    session.add(op)
    session.flush()
    return op


def _parcial(session: Session, v: EvaluacionLocal) -> bool:
    d = session.scalar(select(DecisionLocal).where(DecisionLocal.evaluacion_id == v.id))
    if d is None or d.contenido["accion"] != dto.AccionEvaluacion.CONTINUAR_PARCIAL:
        return False
    comando = session.get(ComandoBonita, d.id)
    return comando.estado == EstadoTareaBonita.COMPLETADA


def ofertas_validadas(
    session: Session, e: Emergencia, usuario: Usuario
) -> dto.OfertasValidadasResponse:
    if usuario.rol == RolUsuario.OPERADOR_MUNICIPAL:
        autorizar(e, usuario, usuario.rol)
    else:
        autorizar(e, usuario, RolUsuario.COORDINADOR_REGIONAL)
    c = ultima_ronda(session, e.id)
    v = ultima_evaluacion(session, c.id)
    if v is None or v.resultado is None or c.estado != EstadoConvocatoria.CERRADA:
        return dto.OfertasValidadasResponse(
            validacion=None, aportes=[], diagnosticos=[], permite_parcial=False
        )
    resultado = leer_resultado(v.resultado)
    return dto.OfertasValidadasResponse(
        validacion=confirmacion(session, v),
        aportes=elegibles(session, v, resultado),
        diagnosticos=resultado.aportes,
        permite_parcial=_parcial(session, v),
    )


def decidir(
    session: Session, e: Emergencia, usuario: Usuario, datos: dto.DecisionRequest
) -> DecisionLocal:
    autorizar(e, usuario, RolUsuario.COORDINADOR_REGIONAL)
    previa = session.get(DecisionLocal, datos.decision_id)
    if previa is not None:
        esperado = dto.DecisionRequest.model_validate(
            {k: previa.contenido[k] for k in objeto(datos)}
        )
        if (
            esperado != datos
            or session.get(ComandoBonita, previa.id).emergencia_id != e.id
        ):
            raise IntegracionLocalError("La decisión ya tiene otro contenido.")
        return previa
    v = _evaluacion(session, e, datos.validacion_id, datos.revision)
    if datos.convocatoria_id != v.convocatoria_id or session.scalar(
        select(DecisionLocal.id).where(DecisionLocal.evaluacion_id == v.id)
    ):
        raise IntegracionLocalError("La ronda no coincide o ya tiene una decisión.")
    if confirmacion(session, v).lotes_compatibles_cubiertos:
        raise IntegracionLocalError(
            "La evaluación tiene cobertura completa; corresponde seleccionar."
        )
    c = ultima_ronda(session, e.id)
    preparada = None
    if datos.accion == dto.AccionEvaluacion.CONTINUAR_PARCIAL:
        if not elegibles(session, v, leer_resultado(v.resultado)):
            raise IntegracionLocalError("No hay aportes compatibles para continuar.")
    elif datos.accion == dto.AccionEvaluacion.REABRIR:
        ahora = datetime.now(UTC)
        nueva = Convocatoria(
            emergencia_id=e.id,
            numero=c.numero + 1,
            publicada_en=ahora,
            cierra_en=ahora + timedelta(hours=2),
            sistema_origen_ref=c.sistema_origen_ref,
            gravedad_publicada=c.gravedad_publicada,
        )
        session.add(nueva)
        session.flush()
        for p in session.scalars(
            select(ConvocatoriaLote).where(ConvocatoriaLote.convocatoria_id == c.id)
        ):
            session.add(
                ConvocatoriaLote(
                    convocatoria_id=nueva.id,
                    lote_id=p.lote_id,
                    cantidad_publicada=p.cantidad_publicada,
                    unidad_publicada=p.unidad_publicada,
                    capacidad_nacional_id=p.capacidad_nacional_id,
                    codigo_capacidad_publicada=p.codigo_capacidad_publicada,
                    admite_fracciones_publicada=p.admite_fracciones_publicada,
                    riesgo_requerido_publicado=p.riesgo_requerido_publicado,
                )
            )
        e.estado = EstadoEmergencia.PUBLICADA
        preparada = dto.ConvocatoriaPreparada(
            convocatoria_id=nueva.id, numero=nueva.numero
        )
    else:
        for p in session.scalars(
            select(ConvocatoriaLote).where(ConvocatoriaLote.convocatoria_id == c.id)
        ):
            l = session.get(Lote, p.lote_id)
            session.add(
                Lote(
                    emergencia_id=e.id,
                    creado_por_usuario_id=usuario.id,
                    tipo_necesidad=l.tipo_necesidad,
                    descripcion=l.descripcion,
                    cantidad_requerida=p.cantidad_publicada,
                    unidad=p.unidad_publicada,
                    capacidad_nacional_id=p.capacidad_nacional_id,
                    codigo_capacidad=p.codigo_capacidad_publicada,
                    admite_fracciones=p.admite_fracciones_publicada,
                    riesgo_requerido=p.riesgo_requerido_publicado,
                    estado=EstadoLote.BORRADOR,
                )
            )
        e.estado = EstadoEmergencia.EN_COORDINACION
    _comando(
        session,
        e,
        usuario,
        datos.decision_id,
        "Evalua situacion",
        "coordinador.regional",
        str(c.numero),
        ContratoDecision(
            accion_seleccionada=datos.accion.value,
            decision_coordinador_id=datos.decision_id,
        ),
    )
    respuesta = dto.DecisionResponse(
        **datos.model_dump(),
        case_id=str(e.bonita_process_instance_id),
        intento_convocatoria=c.numero,
        convocatoria_preparada=preparada,
    )
    decision = DecisionLocal(
        id=datos.decision_id, evaluacion_id=v.id, contenido=objeto(respuesta)
    )
    session.add(decision)
    session.commit()
    return decision


def adjudicar(
    session: Session, e: Emergencia, usuario: Usuario, datos: dto.AdjudicacionRequest
) -> AdjudicacionLocal:
    autorizar(e, usuario, RolUsuario.OPERADOR_MUNICIPAL)
    previa = session.get(AdjudicacionLocal, datos.adjudicacion_id)
    if previa is not None:
        if (
            previa.seleccion != objeto(datos)
            or session.get(ComandoBonita, previa.id).emergencia_id != e.id
        ):
            raise IntegracionLocalError("La adjudicación ya tiene otro contenido.")
        return previa
    v = _evaluacion(session, e, datos.validacion_id, datos.revision)
    disponibles = {
        a.aporte_id: a for a in elegibles(session, v, leer_resultado(v.resultado))
    }
    if len({a.aporte_id for a in datos.aportes}) != len(datos.aportes):
        raise IntegracionLocalError("La selección repite aportes.", 422)
    por_recurso: dict[UUID, Decimal] = {}
    por_lote: dict[int, Decimal] = {}
    nacionales: list[dto.AporteCompromiso] = []
    for seleccionado in sorted(datos.aportes, key=lambda a: a.aporte_id):
        a = disponibles.get(seleccionado.aporte_id)
        cantidad = seleccionado.cantidad
        if (
            a is None
            or cantidad > a.cantidad_ofrecida
            or (not a.admite_fracciones and cantidad % 1)
        ):
            raise IntegracionLocalError(
                "La selección contiene cantidades o aportes incompatibles.", 422
            )
        por_recurso[a.recurso_nacional_id] = (
            por_recurso.get(a.recurso_nacional_id, Decimal(0)) + cantidad
        )
        por_lote[a.lote_id] = por_lote.get(a.lote_id, Decimal(0)) + cantidad
        if por_recurso[a.recurso_nacional_id] > a.cantidad_disponible:
            raise IntegracionLocalError(
                "La selección excede la disponibilidad consultada."
            )
        nacionales.append(
            dto.AporteCompromiso(
                oferta_id=str(a.oferta_id),
                version=a.version,
                lote_id=str(a.lote_id),
                aporte_id=str(a.aporte_id),
                ong_nacional_id=a.ong_nacional_id,
                recurso_nacional_id=a.recurso_nacional_id,
                capacidad_nacional_id=a.capacidad_nacional_id,
                riesgo_requerido=a.riesgo_requerido,
                cantidad=cantidad,
                unidad=a.unidad,
            )
        )
    s = OfertasConsolidadasResponse.model_validate(v.snapshot)
    faltante = False
    for l in s.lotes:
        cantidad = por_lote.get(l.lote_id, Decimal(0))
        if cantidad > l.cantidad_publicada_exacta:
            raise IntegracionLocalError(
                "La selección excede el requerimiento publicado.", 422
            )
        faltante |= cantidad < l.cantidad_publicada_exacta
    if faltante and not _parcial(session, v):
        raise IntegracionLocalError(
            "El coordinador debe autorizar continuar con cobertura parcial."
        )
    request = dto.CompromisoRequest(
        sistema_origen=s.sistema_origen,
        id_emergencia=str(e.id),
        case_id=s.case_id,
        convocatoria_id=str(v.convocatoria_id),
        adjudicacion_id=str(datos.adjudicacion_id),
        aportes=nacionales,
    )
    op = _operacion(session, e, TipoOperacion.COMPROMISO, request)
    _comando(
        session,
        e,
        usuario,
        datos.adjudicacion_id,
        "Seleccionar ofertas validadas",
        "operador.municipal",
        str(s.numero),
        ContratoSeleccion(
            adjudicacion_id=datos.adjudicacion_id,
            adjudicacion_version=1,
            convocatoria_id=v.convocatoria_id,
            operacion_compromiso_id=op.id,
        ),
    )
    adj = AdjudicacionLocal(
        id=datos.adjudicacion_id,
        convocatoria_id=v.convocatoria_id,
        evaluacion_id=v.id,
        operacion_id=op.id,
        seleccion=objeto(datos),
    )
    session.add(adj)
    session.commit()
    return adj


def obtener_adjudicacion(
    session: Session, e: Emergencia, identidad: UUID
) -> AdjudicacionLocal:
    adj = session.get(AdjudicacionLocal, identidad)
    if adj is None or session.get(ComandoBonita, identidad).emergencia_id != e.id:
        raise IntegracionLocalError(
            "La adjudicación no existe en esta emergencia.", 404
        )
    return adj


def preparacion_adjudicacion(
    session: Session, adj: AdjudicacionLocal, version: int
) -> dto.AdjudicacionPreparada:
    if version != 1:
        raise IntegracionLocalError("La versión de adjudicación no coincide.")
    op = session.get(OperacionNacional, adj.operacion_id)
    return dto.AdjudicacionPreparada(
        adjudicacion_id=adj.id,
        version=1,
        convocatoria_id=adj.convocatoria_id,
        validacion_id=adj.evaluacion_id,
        operacion_compromiso_id=op.id,
        idempotency_key=op.clave,
        huella_request=op.huella,
        compromiso=dto.CompromisoRequest.model_validate(op.request),
    )


def participacion_response(
    session: Session, p: ParticipacionLocal
) -> dto.ParticipacionResponse:
    f = session.scalar(
        select(FinalizacionLocal).where(FinalizacionLocal.participacion_id == p.id)
    )
    return dto.ParticipacionResponse(
        participacion_id=p.id,
        ong_id=p.ong_id,
        ong_nacional_id=p.ong_nacional_id,
        compromiso_ids=list(
            session.scalars(
                select(CompromisoLocal.id)
                .where(CompromisoLocal.participacion_id == p.id)
                .order_by(CompromisoLocal.id)
            )
        ),
        estado=p.estado,
        finalizacion_id=f.id if f else None,
    )


def adjudicacion_response(
    session: Session, adj: AdjudicacionLocal, ong_id: int | None = None
) -> dto.AdjudicacionResponse:
    op = session.get(OperacionNacional, adj.operacion_id)
    query = (
        select(ParticipacionLocal)
        .where(ParticipacionLocal.adjudicacion_id == adj.id)
        .order_by(ParticipacionLocal.ong_id)
    )
    if ong_id is not None:
        query = query.where(ParticipacionLocal.ong_id == ong_id)
    return dto.AdjudicacionResponse(
        adjudicacion_id=adj.id,
        version=1,
        estado=adj.estado,
        operacion_compromiso_id=op.id,
        estado_integracion=op.estado,
        proyecto_id=adj.proyecto_id,
        participantes=[
            participacion_response(session, p) for p in session.scalars(query)
        ],
    )


def confirmar_compromisos(
    session: Session, e: Emergencia, datos: dto.ConfirmarCompromisosRequest
) -> dto.AdjudicacionResponse:
    adj = obtener_adjudicacion(session, e, datos.adjudicacion_id)
    preparado = preparacion_adjudicacion(session, adj, datos.adjudicacion_version)
    op = session.get(OperacionNacional, adj.operacion_id)
    if datos.operacion_compromiso_id != op.id or datos.huella_request != op.huella:
        raise IntegracionLocalError(
            "La confirmación no corresponde a la operación preparada."
        )
    contenido = objeto(datos)
    if op.confirmacion is not None:
        if op.confirmacion != contenido:
            raise IntegracionLocalError("La operación ya tiene otra confirmación.")
        return adjudicacion_response(session, adj)
    if (
        adj.estado != "PENDIENTE_COMPROMISO"
        or e.estado != EstadoEmergencia.EN_EVALUACION
        or not vigente(session, session.get(EvaluacionLocal, adj.evaluacion_id))
    ):
        raise IntegracionLocalError("La adjudicación ya no admite esta confirmación.")
    ids = datos.confirmacion.compromiso_ids
    if (
        len(set(ids)) != len(ids)
        or len({c.id for c in datos.compromisos}) != len(datos.compromisos)
        or set(ids) != {c.id for c in datos.compromisos}
    ):
        raise IntegracionLocalError(
            "El conjunto de compromisos es incompleto o está repetido."
        )
    request = preparado.compromiso
    esperados = {a.aporte_id: a for a in request.aportes}
    recibidos: dict[str, dto.AporteCompromiso] = {}
    por_ong: dict[UUID, list[dto.DetalleCompromiso]] = {}
    item_ids: set[UUID] = set()
    for c in datos.compromisos:
        if (
            c.proyecto_id,
            c.sistema_origen,
            c.id_emergencia,
            c.case_id,
            c.adjudicacion_id,
            c.estado,
        ) != (
            datos.confirmacion.proyecto_id,
            request.sistema_origen,
            request.id_emergencia,
            request.case_id,
            request.adjudicacion_id,
            "ACTIVO",
        ) or not c.items:
            raise IntegracionLocalError(
                "El detalle de compromiso tiene otra correlación o estado."
            )
        por_ong.setdefault(c.ong_nacional_id, []).append(c)
        for item in c.items:
            a = dto.AporteCompromiso.model_validate(
                item.model_dump(exclude={"id", "convocatoria_id"})
            )
            if (
                item.convocatoria_id != request.convocatoria_id
                or a.ong_nacional_id != c.ong_nacional_id
                or a.aporte_id in recibidos
                or item.id in item_ids
            ):
                raise IntegracionLocalError(
                    "Un compromiso repite ítems o contiene referencias ajenas."
                )
            recibidos[a.aporte_id] = a
            item_ids.add(item.id)
    if recibidos != esperados:
        raise IntegracionLocalError(
            "Los compromisos no coinciden exactamente con la selección."
        )
    v = session.get(EvaluacionLocal, adj.evaluacion_id)
    # La operación ya fue seleccionada y el resultado nacional coincide con su
    # request inmutable. Usar el snapshot conserva callbacks pendientes legacy.
    snapshot = OfertasConsolidadasResponse.model_validate(v.snapshot)
    aportes = {
        str(a.aporte_id): a
        for oferta in snapshot.ofertas
        for item in oferta.items
        for a in item.aportes
    }
    for ong_id, compromisos in por_ong.items():
        local_ids = {
            aportes[a.aporte_id].ong_id
            for a in request.aportes
            if a.ong_nacional_id == ong_id
        }
        if len(local_ids) != 1:
            raise IntegracionLocalError(
                "La ONG nacional no tiene un mapping local único."
            )
        p = ParticipacionLocal(
            id=uuid4(),
            adjudicacion_id=adj.id,
            ong_id=local_ids.pop(),
            ong_nacional_id=ong_id,
        )
        session.add(p)
        session.flush()
        for c in compromisos:
            if session.get(CompromisoLocal, c.id) is not None:
                raise IntegracionLocalError(
                    "El compromiso ya pertenece a otra adjudicación."
                )
            session.add(
                CompromisoLocal(id=c.id, participacion_id=p.id, detalle=objeto(c))
            )
        _notificar(session, e.id, adj.id, p.ong_id)
    adj.proyecto_id = datos.confirmacion.proyecto_id
    adj.estado = "CONFIRMADA"
    op.estado = EstadoOperacion.CONFIRMADA
    op.confirmacion = contenido
    op.resultado = None
    e.estado = EstadoEmergencia.EN_EJECUCION
    seleccionadas = {int(a.oferta_id) for a in request.aportes}
    for o in session.scalars(
        select(Oferta).where(
            Oferta.convocatoria_id == adj.convocatoria_id,
            Oferta.fusionada_en_oferta_id.is_(None),
            Oferta.estado.in_(
                [
                    EstadoOferta.PRESENTADA,
                    EstadoOferta.EN_VALIDACION,
                    EstadoOferta.VALIDADA,
                ]
            ),
        )
    ):
        o.estado = (
            EstadoOferta.ADJUDICADA
            if o.id in seleccionadas
            else EstadoOferta.NO_ADJUDICADA
        )
    session.commit()
    return adjudicacion_response(session, adj)


def clave_adjudicacion(adjudicacion_id: UUID) -> str:
    return f"adjudicacion:{adjudicacion_id}:confirmada"


def _notificar(
    session: Session, emergencia_id: int, adjudicacion_id: UUID, ong_id: int
) -> None:
    usuarios = session.scalars(
        select(Usuario.id).where(
            Usuario.organizacion_id == ong_id,
            Usuario.activo.is_(True),
            Usuario.rol == RolUsuario.REPRESENTANTE_ONG,
        )
    ).all()
    for usuario_id in usuarios:
        session.execute(
            insert(Notificacion)
            .values(
                usuario_id=usuario_id,
                clave_evento=clave_adjudicacion(adjudicacion_id),
                tipo=TipoNotificacion.EMERGENCIA_ESTADO_ACTUALIZADO,
                titulo="Adjudicación confirmada",
                mensaje="Los recursos de tu ONG quedaron comprometidos para esta emergencia.",
                ruta=f"/emergencias/{emergencia_id}/ejecucion",
            )
            .on_conflict_do_nothing(constraint="uq_notificacion_usuario_evento")
        )


def obtener_operacion(
    session: Session, e: Emergencia, identidad: UUID
) -> OperacionNacional:
    op = session.get(OperacionNacional, identidad)
    if op is None or op.emergencia_id != e.id:
        raise IntegracionLocalError("La operación no existe en esta emergencia.", 404)
    return op


def informar_resultado(
    session: Session,
    e: Emergencia,
    identidad: UUID,
    datos: dto.ResultadoOperacionRequest,
) -> dto.OperacionResponse:
    op = obtener_operacion(session, e, identidad)
    if op.clave != datos.idempotency_key or op.tipo != datos.tipo:
        raise IntegracionLocalError(
            "La clave o el tipo no corresponden a la operación."
        )
    if op.estado == EstadoOperacion.CONFIRMADA and (
        (op.tipo == TipoOperacion.COMPROMISO and datos.etapa == "NOTIFICACION")
        or (op.tipo == TipoOperacion.CIERRE and datos.etapa == "RESOLVER")
    ):
        op.resultado = objeto(datos)
        session.commit()
    if op.estado == EstadoOperacion.RECHAZO_DEFINITIVO and op.resultado != objeto(
        datos
    ):
        raise IntegracionLocalError(
            "El rechazo definitivo ya cerró esta operación; prepará otra selección."
        )
    if op.estado != EstadoOperacion.CONFIRMADA:
        # Nunca degradar incertidumbre a un rechazo: un intento anterior pudo confirmar.
        if datos.estado_integracion == "RECHAZO_DEFINITIVO" and (
            datos.http_status != 409 or op.estado == EstadoOperacion.INCIERTO
        ):
            raise IntegracionLocalError(
                "El resultado no demuestra un rechazo definitivo sin efectos."
            )
        op.estado = (
            EstadoOperacion.INCIERTO
            if op.estado == EstadoOperacion.INCIERTO
            else EstadoOperacion(datos.estado_integracion)
        )
        op.resultado = objeto(datos)
        if (
            op.tipo == TipoOperacion.COMPROMISO
            and op.estado == EstadoOperacion.RECHAZO_DEFINITIVO
        ):
            adj = session.scalar(
                select(AdjudicacionLocal).where(AdjudicacionLocal.operacion_id == op.id)
            )
            adj.estado = "REQUIERE_REVISION"
        session.commit()
    return dto.OperacionResponse(
        operacion_id=op.id, tipo=op.tipo, estado_integracion=op.estado
    )


def finalizar(
    session: Session, e: Emergencia, usuario: Usuario, identidad: UUID
) -> FinalizacionLocal:
    p = session.get(ParticipacionLocal, identidad)
    if p is None or session.get(ComandoBonita, p.adjudicacion_id).emergencia_id != e.id:
        raise IntegracionLocalError(
            "La participación no existe en esta emergencia.", 404
        )
    if (
        usuario.rol != RolUsuario.REPRESENTANTE_ONG
        or usuario.organizacion_id != p.ong_id
        or usuario.organizacion is None
        or not usuario.organizacion.activa
    ):
        raise IntegracionLocalError(
            "Sólo la ONG participante puede informar su finalización.", 403
        )
    previa = session.scalar(
        select(FinalizacionLocal).where(FinalizacionLocal.participacion_id == p.id)
    )
    if previa is not None:
        return previa
    if e.estado != EstadoEmergencia.EN_EJECUCION or p.estado != "EN_EJECUCION":
        raise IntegracionLocalError("La participación aún no está en ejecución.")
    f_id = uuid4()
    _comando(
        session,
        e,
        usuario,
        f_id,
        "Marcar como finalizada la tarea",
        "ong.representante",
        str(p.id),
        ContratoFinalizacion(participacion_id=p.id, finalizacion_id=f_id),
    )
    f = FinalizacionLocal(id=f_id, participacion_id=p.id)
    session.add(f)
    for c in session.scalars(
        select(CompromisoLocal)
        .where(CompromisoLocal.participacion_id == p.id)
        .order_by(CompromisoLocal.id)
    ):
        op = _operacion(
            session,
            e,
            TipoOperacion.LIBERACION,
            dto.RequestCaso(case_id=str(e.bonita_process_instance_id)),
        )
        c.liberacion_id = op.id
    p.estado = "FINALIZACION_SOLICITADA"
    session.commit()
    return f


def liberaciones(
    session: Session, e: Emergencia, identidad: UUID
) -> dto.LiberacionesResponse:
    f = session.get(FinalizacionLocal, identidad)
    if f is None or session.get(ComandoBonita, identidad).emergencia_id != e.id:
        raise IntegracionLocalError(
            "La finalización no existe en esta emergencia.", 404
        )
    operaciones: list[dto.LiberacionPreparada] = []
    for c in session.scalars(
        select(CompromisoLocal)
        .where(CompromisoLocal.participacion_id == f.participacion_id)
        .order_by(CompromisoLocal.id)
    ):
        op = session.get(OperacionNacional, c.liberacion_id)
        operaciones.append(
            dto.LiberacionPreparada(
                operacion_id=op.id,
                compromiso_id=c.id,
                idempotency_key=op.clave,
                request=dto.RequestCaso.model_validate(op.request),
            )
        )
    return dto.LiberacionesResponse(
        finalizacion_id=f.id,
        participacion_id=f.participacion_id,
        solicitada_en=f.solicitada_en,
        operaciones=operaciones,
    )


def confirmar_liberacion(
    session: Session,
    e: Emergencia,
    compromiso_id: UUID,
    datos: dto.LiberacionConfirmadaRequest,
) -> dto.ParticipacionResponse:
    preparadas = liberaciones(session, e, datos.finalizacion_id)
    c = session.get(CompromisoLocal, compromiso_id)
    if (
        c is None
        or c.participacion_id != datos.participacion_id
        or preparadas.participacion_id != datos.participacion_id
        or c.liberacion_id != datos.operacion_id
    ):
        raise IntegracionLocalError("La liberación no corresponde a esta finalización.")
    p = session.get(ParticipacionLocal, c.participacion_id)
    adj = session.get(AdjudicacionLocal, p.adjudicacion_id)
    r = datos.confirmacion
    if (r.compromiso_id, r.proyecto_id, r.ong_nacional_id) != (
        c.id,
        adj.proyecto_id,
        p.ong_nacional_id,
    ):
        raise IntegracionLocalError("La confirmación nacional tiene otra correlación.")
    op = session.get(OperacionNacional, c.liberacion_id)
    contenido = objeto(r)
    if op.confirmacion is not None and op.confirmacion != contenido:
        raise IntegracionLocalError("La liberación ya recibió otra confirmación.")
    op.confirmacion = contenido
    op.estado = EstadoOperacion.CONFIRMADA
    op.resultado = None
    c.liberado_en = r.liberado_en
    session.flush()
    if not session.scalar(
        select(CompromisoLocal.id).where(
            CompromisoLocal.participacion_id == p.id,
            CompromisoLocal.liberado_en.is_(None),
        )
    ):
        p.estado = "LIBERADA"
    session.commit()
    return participacion_response(session, p)


def _puede_cerrar(session: Session, adj: AdjudicacionLocal) -> bool:
    participantes = list(
        session.scalars(
            select(ParticipacionLocal).where(
                ParticipacionLocal.adjudicacion_id == adj.id
            )
        )
    )
    return (
        adj.estado == "CONFIRMADA"
        and adj.proyecto_id is not None
        and bool(participantes)
        and all(p.estado == "LIBERADA" for p in participantes)
    )


def solicitar_cierre(session: Session, e: Emergencia, usuario: Usuario) -> CierreLocal:
    autorizar(e, usuario, RolUsuario.COORDINADOR_REGIONAL)
    adj = session.scalar(
        select(AdjudicacionLocal)
        .join(ComandoBonita, ComandoBonita.id == AdjudicacionLocal.id)
        .where(
            ComandoBonita.emergencia_id == e.id,
            AdjudicacionLocal.estado == "CONFIRMADA",
        )
    )
    if adj is None:
        raise IntegracionLocalError("No hay una adjudicación confirmada para cerrar.")
    previa = session.scalar(
        select(CierreLocal).where(CierreLocal.adjudicacion_id == adj.id)
    )
    if previa is not None:
        return previa
    if e.estado != EstadoEmergencia.EN_EJECUCION or not _puede_cerrar(session, adj):
        raise IntegracionLocalError(
            "Todas las ONGs deben finalizar y confirmar sus liberaciones antes del cierre."
        )
    op = _operacion(
        session,
        e,
        TipoOperacion.CIERRE,
        dto.RequestCaso(case_id=str(e.bonita_process_instance_id)),
    )
    identidad = uuid4()
    _comando(
        session,
        e,
        usuario,
        identidad,
        "Marcar proyecto como terminado",
        "coordinador.regional",
        str(adj.id),
        ContratoCierre(solicitud_cierre_id=identidad),
    )
    cierre = CierreLocal(id=identidad, adjudicacion_id=adj.id, operacion_id=op.id)
    session.add(cierre)
    session.commit()
    return cierre


def cierre_preparado(
    session: Session, e: Emergencia, identidad: UUID
) -> dto.CierrePreparado:
    c = session.get(CierreLocal, identidad)
    if c is None or session.get(ComandoBonita, identidad).emergencia_id != e.id:
        raise IntegracionLocalError(
            "La solicitud de cierre no existe en esta emergencia.", 404
        )
    adj = session.get(AdjudicacionLocal, c.adjudicacion_id)
    op = session.get(OperacionNacional, c.operacion_id)
    return dto.CierrePreparado(
        solicitud_cierre_id=c.id,
        proyecto_id=adj.proyecto_id,
        case_id=str(e.bonita_process_instance_id),
        operacion_cierre_id=op.id,
        idempotency_key=op.clave,
        request=dto.RequestCaso.model_validate(op.request),
        liberaciones_confirmadas=_puede_cerrar(session, adj),
        operaciones_inciertas=op.estado == EstadoOperacion.INCIERTO,
    )


def resolver(
    session: Session, e: Emergencia, datos: dto.ResolverRequest
) -> dto.ResolucionResponse:
    c = cierre_preparado(session, e, datos.solicitud_cierre_id)
    if (
        datos.id_emergencia,
        datos.proyecto_nacional_id,
        datos.operacion_cierre_id,
        datos.cierre.proyecto_id,
    ) != (
        e.id,
        c.proyecto_id,
        c.operacion_cierre_id,
        c.proyecto_id,
    ) or not c.liberaciones_confirmadas:
        raise IntegracionLocalError(
            "El cierre no corresponde a una operación preparada con todas las liberaciones confirmadas."
        )
    op = session.get(OperacionNacional, c.operacion_cierre_id)
    contenido = objeto(datos.cierre)
    if op.confirmacion is not None and op.confirmacion != contenido:
        raise IntegracionLocalError("El cierre ya recibió otra confirmación.")
    if e.estado not in (EstadoEmergencia.EN_EJECUCION, EstadoEmergencia.RESUELTA):
        raise IntegracionLocalError("La emergencia no admite resolución.")
    op.confirmacion = contenido
    op.estado = EstadoOperacion.CONFIRMADA
    op.resultado = None
    e.estado = EstadoEmergencia.RESUELTA
    session.commit()
    return dto.ResolucionResponse(
        id_emergencia=e.id,
        estado=e.estado,
        proyecto_nacional_id=c.proyecto_id,
        cerrado_en=datos.cierre.cerrado_en,
    )


def seguimiento(
    session: Session, e: Emergencia, usuario: Usuario
) -> dto.SeguimientoResponse:
    ong_id = None
    if usuario.rol == RolUsuario.REPRESENTANTE_ONG:
        if usuario.organizacion is None or not usuario.organizacion.activa:
            raise IntegracionLocalError("La ONG no está activa.", 403)
        ong_id = usuario.organizacion_id
    else:
        autorizar(e, usuario, usuario.rol)
    adjudicaciones = list(
        session.scalars(
            select(AdjudicacionLocal)
            .join(ComandoBonita, ComandoBonita.id == AdjudicacionLocal.id)
            .where(ComandoBonita.emergencia_id == e.id)
            .order_by(AdjudicacionLocal.id)
        )
    )
    if ong_id is not None:
        adjudicaciones = [
            a
            for a in adjudicaciones
            if session.scalar(
                select(ParticipacionLocal.id).where(
                    ParticipacionLocal.adjudicacion_id == a.id,
                    ParticipacionLocal.ong_id == ong_id,
                )
            )
        ]
        if not adjudicaciones:
            raise IntegracionLocalError("La ONG no participa en esta emergencia.", 403)
    efectiva = next((a for a in adjudicaciones if a.estado == "CONFIRMADA"), None)
    cierre = (
        session.scalar(
            select(CierreLocal).where(CierreLocal.adjudicacion_id == efectiva.id)
        )
        if efectiva is not None
        else None
    )
    return dto.SeguimientoResponse(
        id_emergencia=e.id,
        estado=e.estado,
        adjudicaciones=[
            adjudicacion_response(session, a, ong_id) for a in adjudicaciones
        ],
        puede_solicitar_cierre=usuario.rol == RolUsuario.COORDINADOR_REGIONAL
        and e.estado == EstadoEmergencia.EN_EJECUCION
        and efectiva is not None
        and _puede_cerrar(session, efectiva),
        cierre=cierre_preparado(session, e, cierre.id)
        if cierre is not None and ong_id is None
        else None,
        operaciones=[
            dto.OperacionResponse(
                operacion_id=op.id,
                tipo=op.tipo,
                estado_integracion=op.estado,
                etapa_pendiente=op.resultado.get("etapa") if op.resultado else None,
            )
            for op in session.scalars(
                select(OperacionNacional)
                .where(OperacionNacional.emergencia_id == e.id)
                .order_by(OperacionNacional.id)
            )
        ]
        if ong_id is None
        else [],
    )


def recuperar(
    session: Session,
    e: Emergencia,
    usuario: Usuario,
    operacion_id: UUID,
    datos: dto.RecuperacionRequest,
) -> ComandoBonita:
    """Prepara el retorno al paso fallido; un resultado incierto nunca cambia selección."""
    autorizar(e, usuario, RolUsuario.COORDINADOR_REGIONAL)
    op = obtener_operacion(session, e, operacion_id)
    contrato = ContratoRecuperacion(accion_incidente=datos.accion, operacion_id=op.id)
    previo = session.get(ComandoBonita, datos.recuperacion_id)
    if previo is not None:
        if previo.emergencia_id != e.id or previo.contrato != objeto(contrato):
            raise IntegracionLocalError("La recuperación ya tiene otro contenido.")
        return previo
    if op.estado == EstadoOperacion.CONFIRMADA and (
        op.resultado is None
        or op.resultado.get("etapa") not in {"NOTIFICACION", "RESOLVER"}
    ):
        raise IntegracionLocalError("La operación ya está confirmada.")
    if datos.accion == "VOLVER_A_SELECCION" and (
        op.tipo != TipoOperacion.COMPROMISO
        or op.estado != EstadoOperacion.RECHAZO_DEFINITIVO
    ):
        raise IntegracionLocalError(
            "Sólo un rechazo definitivo permite otra selección."
        )
    if (
        op.estado == EstadoOperacion.RECHAZO_DEFINITIVO
        and datos.accion == "REINTENTAR_MISMA_OPERACION"
    ):
        raise IntegracionLocalError(
            "El rechazo definitivo requiere una nueva selección con otra identidad."
        )
    nombres = {
        TipoOperacion.COMPROMISO: "Atender incidente de compromiso",
        TipoOperacion.LIBERACION: "Atender incidente de liberación",
        TipoOperacion.CIERRE: "Atender incidente de cierre",
    }
    c = _comando(
        session,
        e,
        usuario,
        datos.recuperacion_id,
        nombres[op.tipo],
        "coordinador.regional",
        str(op.id),
        contrato,
    )
    session.commit()
    return c
