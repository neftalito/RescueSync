"""Callbacks T36/T37 y comandos de usuario con permisos independientes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import (
    ClienteBonitaDep,
    GestorTiempoRealDep,
    requerir_roles,
    validar_callback_bonita,
    validar_csrf,
)
from app.api.routes.bonita import CasoBonitaId, EmergenciaId
from app.db.models import RolUsuario, Usuario
from app.db.models.ejecucion import ComandoBonita, DecisionLocal, OperacionNacional
from app.db.models.enums import EstadoTareaBonita
from app.db.session import get_db
from app.schemas import ErrorResponse
from app.schemas import ejecucion as dto
from app.services import ejecucion as servicio
from app.services import evaluaciones
from app.services.despacho_bonita import despachar
from app.services.evaluaciones import IntegracionLocalError, bloquear_emergencia
from app.services.tiempo_real import programar_evento_confirmado

ERRORES = {c: {"model": ErrorResponse} for c in (401, 403, 404, 409, 422, 503)}
router = APIRouter(responses=ERRORES)
tecnico = APIRouter(dependencies=[Depends(validar_callback_bonita)], responses=ERRORES)
DB = Annotated[Session, Depends(get_db)]
Coordinador = Annotated[
    Usuario, Depends(requerir_roles(RolUsuario.COORDINADOR_REGIONAL))
]
Municipio = Annotated[Usuario, Depends(requerir_roles(RolUsuario.OPERADOR_MUNICIPAL))]
Ong = Annotated[Usuario, Depends(requerir_roles(RolUsuario.REPRESENTANTE_ONG))]
Consulta = Annotated[
    Usuario,
    Depends(
        requerir_roles(
            RolUsuario.COORDINADOR_REGIONAL,
            RolUsuario.OPERADOR_MUNICIPAL,
            RolUsuario.REPRESENTANTE_ONG,
        )
    ),
]


@tecnico.post(
    "/{emergencia_id}/solicitudes-validacion",
    response_model=dto.PreparacionResponse,
    summary="Preparar una evaluación nacional con revisión local",
)
def preparar(
    emergencia_id: EmergenciaId,
    caso: CasoBonitaId,
    datos: dto.PreparacionValidacion,
    session: DB,
) -> dto.PreparacionResponse:
    return evaluaciones.preparar(session, emergencia_id, caso, datos)


@tecnico.post(
    "/{emergencia_id}/perfiles-validacion",
    response_model=dto.PerfilesResponse,
    summary="Confirmar perfiles y cobertura compatible de una evaluación",
)
def perfiles(
    emergencia_id: EmergenciaId,
    caso: CasoBonitaId,
    datos: dto.PerfilesRequest,
    session: DB,
) -> dto.PerfilesResponse:
    return evaluaciones.guardar_perfiles(session, emergencia_id, caso, datos)


@tecnico.get(
    "/{emergencia_id}/decisiones-evaluacion/{decision_id}",
    response_model=dto.DecisionResponse,
    summary="Consultar la decisión inmutable del coordinador",
)
def decision_tecnica(
    emergencia_id: EmergenciaId,
    caso: CasoBonitaId,
    decision_id: UUID,
    session: DB,
    response: Response,
) -> dto.DecisionResponse:
    bloquear_emergencia(session, emergencia_id, caso)
    response.headers["Cache-Control"] = "no-store"
    d = session.get(DecisionLocal, decision_id)
    if d is None or session.get(ComandoBonita, d.id).emergencia_id != emergencia_id:
        raise IntegracionLocalError("La decisión no existe en esta emergencia.", 404)
    return dto.DecisionResponse.model_validate(d.contenido)


@tecnico.get(
    "/{emergencia_id}/adjudicaciones/{adjudicacion_id}",
    response_model=dto.AdjudicacionPreparada,
    summary="Obtener la operación de compromiso congelada",
)
def adjudicacion_tecnica(
    emergencia_id: EmergenciaId,
    caso: CasoBonitaId,
    adjudicacion_id: UUID,
    session: DB,
    response: Response,
    version: Annotated[int, Query(gt=0)],
) -> dto.AdjudicacionPreparada:
    e = bloquear_emergencia(session, emergencia_id, caso)
    response.headers["Cache-Control"] = "no-store"
    return servicio.preparacion_adjudicacion(
        session, servicio.obtener_adjudicacion(session, e, adjudicacion_id), version
    )


@tecnico.post(
    "/{emergencia_id}/compromisos/confirmacion",
    response_model=dto.AdjudicacionResponse,
    summary="Confirmar el conjunto exacto de compromisos nacionales",
)
def confirmar_compromisos(
    emergencia_id: EmergenciaId,
    caso: CasoBonitaId,
    datos: dto.ConfirmarCompromisosRequest,
    session: DB,
    gestor: GestorTiempoRealDep,
) -> dto.AdjudicacionResponse:
    e = bloquear_emergencia(session, emergencia_id, caso)
    resultado = servicio.confirmar_compromisos(session, e, datos)
    programar_evento_confirmado(
        gestor, session, servicio.clave_adjudicacion(datos.adjudicacion_id)
    )
    return resultado


@tecnico.post(
    "/{emergencia_id}/notificar-adjudicacion",
    response_model=dto.AdjudicacionResponse,
    summary="Entregar la notificación de una adjudicación confirmada",
)
def notificar(
    emergencia_id: EmergenciaId,
    caso: CasoBonitaId,
    datos: dto.NotificarAdjudicacionRequest,
    session: DB,
    gestor: GestorTiempoRealDep,
) -> dto.AdjudicacionResponse:
    e = bloquear_emergencia(session, emergencia_id, caso)
    adj = servicio.obtener_adjudicacion(session, e, datos.adjudicacion_id)
    if adj.estado != "CONFIRMADA" or datos.adjudicacion_version != 1:
        raise IntegracionLocalError("La adjudicación aún no está confirmada.")
    op = session.get(OperacionNacional, adj.operacion_id)
    if op.resultado and op.resultado.get("etapa") == "NOTIFICACION":
        op.resultado = None
    session.commit()
    programar_evento_confirmado(gestor, session, servicio.clave_adjudicacion(adj.id))
    return servicio.adjudicacion_response(session, adj)


@tecnico.post(
    "/{emergencia_id}/operaciones-nacionales/{operacion_id}/resultado",
    response_model=dto.OperacionResponse,
    summary="Registrar un resultado seguro sin perder la identidad de operación",
)
def resultado_operacion(
    emergencia_id: EmergenciaId,
    caso: CasoBonitaId,
    operacion_id: UUID,
    datos: dto.ResultadoOperacionRequest,
    session: DB,
) -> dto.OperacionResponse:
    return servicio.informar_resultado(
        session, bloquear_emergencia(session, emergencia_id, caso), operacion_id, datos
    )


@tecnico.get(
    "/{emergencia_id}/finalizaciones/{finalizacion_id}/liberaciones",
    response_model=dto.LiberacionesResponse,
    summary="Obtener todas las liberaciones preparadas de una participante",
)
def liberaciones(
    emergencia_id: EmergenciaId,
    caso: CasoBonitaId,
    finalizacion_id: UUID,
    session: DB,
    response: Response,
) -> dto.LiberacionesResponse:
    response.headers["Cache-Control"] = "no-store"
    return servicio.liberaciones(
        session, bloquear_emergencia(session, emergencia_id, caso), finalizacion_id
    )


@tecnico.post(
    "/{emergencia_id}/compromisos/{compromiso_id}/liberacion-confirmada",
    response_model=dto.ParticipacionResponse,
    summary="Confirmar una liberación sin finalizar las otras ONGs",
)
def confirmar_liberacion(
    emergencia_id: EmergenciaId,
    caso: CasoBonitaId,
    compromiso_id: UUID,
    datos: dto.LiberacionConfirmadaRequest,
    session: DB,
    gestor: GestorTiempoRealDep,
) -> dto.ParticipacionResponse:
    resultado = servicio.confirmar_liberacion(
        session, bloquear_emergencia(session, emergencia_id, caso), compromiso_id, datos
    )
    gestor.programar_metricas()
    return resultado


@tecnico.get(
    "/{emergencia_id}/solicitudes-cierre/{solicitud_id}",
    response_model=dto.CierrePreparado,
    summary="Consultar el cierre nacional preparado",
)
def cierre_tecnico(
    emergencia_id: EmergenciaId,
    caso: CasoBonitaId,
    solicitud_id: UUID,
    session: DB,
    response: Response,
) -> dto.CierrePreparado:
    response.headers["Cache-Control"] = "no-store"
    return servicio.cierre_preparado(
        session, bloquear_emergencia(session, emergencia_id, caso), solicitud_id
    )


@tecnico.post(
    "/{emergencia_id}/resolver",
    response_model=dto.ResolucionResponse,
    summary="Resolver sólo después del cierre nacional y de todas las liberaciones",
)
def resolver(
    emergencia_id: EmergenciaId,
    caso: CasoBonitaId,
    datos: dto.ResolverRequest,
    session: DB,
    gestor: GestorTiempoRealDep,
) -> dto.ResolucionResponse:
    resultado = servicio.resolver(
        session, bloquear_emergencia(session, emergencia_id, caso), datos
    )
    gestor.programar_metricas()
    return resultado


@router.get(
    "/{emergencia_id}/ofertas-validadas",
    response_model=dto.OfertasValidadasResponse,
    summary="Consultar aportes compatibles; diagnósticos sólo para el coordinador",
)
def ofertas_validadas(
    emergencia_id: EmergenciaId, session: DB, usuario: Consulta, response: Response
) -> dto.OfertasValidadasResponse:
    response.headers["Cache-Control"] = "no-store"
    return servicio.ofertas_validadas(
        session, bloquear_emergencia(session, emergencia_id), usuario
    )


@router.post(
    "/{emergencia_id}/decision-evaluacion",
    dependencies=[Depends(validar_csrf)],
    response_model=dto.DecisionResponse,
    summary="Preparar y enviar una alternativa del coordinador",
)
def decidir(
    emergencia_id: EmergenciaId,
    datos: dto.DecisionRequest,
    session: DB,
    usuario: Coordinador,
    cliente: ClienteBonitaDep,
    gestor: GestorTiempoRealDep,
) -> dto.DecisionResponse:
    decision = servicio.decidir(
        session, bloquear_emergencia(session, emergencia_id), usuario, datos
    )
    if despachar(session, decision.id, cliente).estado == EstadoTareaBonita.COMPLETADA:
        gestor.programar_metricas()
    return dto.DecisionResponse.model_validate(decision.contenido)


@router.post(
    "/{emergencia_id}/adjudicaciones",
    dependencies=[Depends(validar_csrf)],
    response_model=dto.AdjudicacionResponse,
    summary="Preparar selección municipal inmutable y solicitar compromiso a Bonita",
)
def adjudicar(
    emergencia_id: EmergenciaId,
    datos: dto.AdjudicacionRequest,
    session: DB,
    usuario: Municipio,
    cliente: ClienteBonitaDep,
) -> dto.AdjudicacionResponse:
    adj = servicio.adjudicar(
        session, bloquear_emergencia(session, emergencia_id), usuario, datos
    )
    despachar(session, adj.id, cliente)
    return servicio.adjudicacion_response(session, adj)


@router.get(
    "/{emergencia_id}/adjudicaciones",
    response_model=dto.SeguimientoResponse,
    summary="Seguir adjudicaciones y liberaciones según organización",
)
def seguimiento(
    emergencia_id: EmergenciaId, session: DB, usuario: Consulta, response: Response
) -> dto.SeguimientoResponse:
    response.headers["Cache-Control"] = "no-store"
    return servicio.seguimiento(
        session, bloquear_emergencia(session, emergencia_id), usuario
    )


@router.post(
    "/{emergencia_id}/participaciones/{participacion_id}/finalizacion",
    dependencies=[Depends(validar_csrf)],
    response_model=dto.FinalizacionResponse,
    summary="Informar la primera finalización de la ONG participante",
)
def finalizar(
    emergencia_id: EmergenciaId,
    participacion_id: UUID,
    session: DB,
    usuario: Ong,
    cliente: ClienteBonitaDep,
    datos: dto.FinalizacionRequest | None = None,
) -> dto.FinalizacionResponse:
    f = servicio.finalizar(
        session,
        bloquear_emergencia(session, emergencia_id),
        usuario,
        participacion_id,
        datos,
    )
    despachar(session, f.id, cliente)
    return dto.FinalizacionResponse(
        finalizacion_id=f.id,
        participacion_id=f.participacion_id,
        solicitada_en=f.solicitada_en,
    )


@router.post(
    "/{emergencia_id}/solicitudes-cierre",
    dependencies=[Depends(validar_csrf)],
    response_model=dto.CierrePreparado,
    summary="Solicitar cierre coordinador tras todas las liberaciones",
)
def solicitar_cierre(
    emergencia_id: EmergenciaId,
    session: DB,
    usuario: Coordinador,
    cliente: ClienteBonitaDep,
) -> dto.CierrePreparado:
    e = bloquear_emergencia(session, emergencia_id)
    c = servicio.solicitar_cierre(session, e, usuario)
    despachar(session, c.id, cliente)
    return servicio.cierre_preparado(session, e, c.id)


@router.get(
    "/{emergencia_id}/comandos-bonita",
    response_model=list[dto.DespachoResponse],
    summary="Consultar sincronización de las intenciones autorizadas",
)
def comandos(
    emergencia_id: EmergenciaId, session: DB, usuario: Consulta
) -> list[dto.DespachoResponse]:
    e = bloquear_emergencia(session, emergencia_id)
    servicio.seguimiento(session, e, usuario)
    query = select(ComandoBonita).where(ComandoBonita.emergencia_id == e.id)
    if usuario.rol == RolUsuario.REPRESENTANTE_ONG:
        query = query.where(ComandoBonita.usuario_id == usuario.id)
    return [
        dto.DespachoResponse(comando_id=c.id, estado=c.estado.value, error=c.error)
        for c in session.scalars(query)
    ]


@router.post(
    "/{emergencia_id}/operaciones-nacionales/{operacion_id}/recuperacion",
    dependencies=[Depends(validar_csrf)],
    response_model=dto.DespachoResponse,
    summary="Retomar una operación nacional desde su incidente exacto",
)
def recuperar(
    emergencia_id: EmergenciaId,
    operacion_id: UUID,
    datos: dto.RecuperacionRequest,
    session: DB,
    usuario: Coordinador,
    cliente: ClienteBonitaDep,
) -> dto.DespachoResponse:
    e = bloquear_emergencia(session, emergencia_id)
    comando = servicio.recuperar(session, e, usuario, operacion_id, datos)
    return despachar(session, comando.id, cliente)


@router.post(
    "/{emergencia_id}/comandos-bonita/{comando_id}/reintentar",
    dependencies=[Depends(validar_csrf)],
    response_model=dto.DespachoResponse,
    summary="Reconciliar la misma actividad sin crear otra intención",
)
def reintentar(
    emergencia_id: EmergenciaId,
    comando_id: UUID,
    session: DB,
    usuario: Consulta,
    cliente: ClienteBonitaDep,
    gestor: GestorTiempoRealDep,
) -> dto.DespachoResponse:
    e = bloquear_emergencia(session, emergencia_id)
    c = session.get(ComandoBonita, comando_id)
    if c is None or c.emergencia_id != e.id:
        raise IntegracionLocalError("El comando no existe en esta emergencia.", 404)
    if usuario.rol == RolUsuario.REPRESENTANTE_ONG:
        if c.usuario_id != usuario.id:
            raise IntegracionLocalError(
                "No podés reintentar la intención de otra persona.", 403
            )
    else:
        servicio.autorizar(e, usuario, usuario.rol)
        if (usuario.rol == RolUsuario.OPERADOR_MUNICIPAL) != (
            c.tarea == "Seleccionar ofertas validadas"
        ):
            raise IntegracionLocalError("La intención corresponde a otro rol.", 403)
    resultado = despachar(session, c.id, cliente)
    if resultado.estado == EstadoTareaBonita.COMPLETADA:
        gestor.programar_metricas()
    return resultado
