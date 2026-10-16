"""Camino bilateral y rechazos de correlación/idempotencia sobre PostgreSQL real."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_ofertas import (
    Escenario,
    _autenticar_con_cookie,
    _organizacion,
    _usuario,
    client,
    escenario,
)
from test_snapshot_nacional import capacidad, cerrar, presentar

from app.core.config import get_settings
from app.db.models import (
    EstadoEmergencia,
    Notificacion,
    RolUsuario,
    TipoOrganizacion,
    Usuario,
)
from app.db.models.ejecucion import ComandoBonita, EvaluacionLocal, OperacionNacional
from app.db.models.enums import EstadoTareaBonita
from app.schemas import ejecucion as dto
from app.schemas.bonita import OfertasConsolidadasResponse
from app.services import ejecucion as servicio
from app.services import evaluaciones
from app.services.evaluaciones import IntegracionLocalError, objeto

__all__ = ["capacidad", "client", "escenario"]


@pytest.fixture
def coordinador(db_session: Session, escenario: Escenario) -> Usuario:
    centro = _organizacion(
        db_session, TipoOrganizacion.CENTRO_COORDINADOR, "Centro ejecución"
    )
    usuario = _usuario(
        db_session,
        centro,
        RolUsuario.COORDINADOR_REGIONAL,
        "coordinador-ejecucion@test.org",
    )
    escenario.emergencia.centro_coordinador_id = centro.id
    db_session.commit()
    return usuario


def preparar(
    db: Session, esc: Escenario, cap: UUID, dos_ongs: bool = False
) -> dto.PerfilesRequest:
    presentar(db, esc, esc.representante, cap, "300")
    if dos_ongs:
        miembro = _usuario(
            db, esc.otra_ong, RolUsuario.REPRESENTANTE_ONG, "segunda-ejecucion@test.org"
        )
        presentar(db, esc, miembro, cap, "300")
    cerrar(db, esc)
    esc.emergencia.estado = EstadoEmergencia.EN_EVALUACION
    db.commit()
    prep = evaluaciones.preparar(
        db,
        esc.emergencia.id,
        4242,
        dto.PreparacionValidacion(
            validacion_id=uuid4(),
            convocatoria_id=esc.convocatoria.id,
            intento_convocatoria=1,
        ),
    )
    v = db.get(EvaluacionLocal, prep.validacion_id)
    s = OfertasConsolidadasResponse.model_validate(v.snapshot)
    perfiles: list[dto.AporteEvaluado] = []
    recursos: list[dto.RecursoConsultado] = []
    for o in s.ofertas:
        for i in o.items:
            for a in i.aportes:
                perfiles.append(
                    dto.AporteEvaluado(
                        oferta_id=o.oferta_id,
                        version=o.version,
                        item_id=i.item_id,
                        lote_id=i.lote_id,
                        aporte_id=a.aporte_id,
                        ong_id=a.ong_id,
                        ong_nacional_id=a.ong_nacional_id,
                        recurso_nacional_id=a.recurso_nacional_id,
                        cantidad_ofrecida=a.cantidad,
                        unidad=a.unidad,
                        clasificacion=dto.Clasificacion.PRINCIPAL,
                        capacidades_habilitadas=[
                            {
                                "capacidadId": str(cap),
                                "codigo": "AGUA",
                                "nombre": "Agua",
                                "unidad": "litros",
                                "riesgoMaximo": "ALTA",
                                "nivelesRiesgoPermitidos": ["BAJA", "MEDIA", "ALTA"],
                                "acreditacionIds": [],
                            }
                        ],
                        niveles_riesgo_permitidos=["BAJA", "MEDIA", "ALTA"],
                        cantidad_disponible_consultada=Decimal(1000),
                        motivos=[],
                    )
                )
                recursos.append(
                    dto.RecursoConsultado(
                        recurso_nacional_id=a.recurso_nacional_id,
                        ong_nacional_id=a.ong_nacional_id,
                        capacidad_nacional_id=cap,
                        unidad=a.unidad,
                        cantidad_disponible=Decimal(1000),
                        cantidad_solicitada_snapshot=a.cantidad,
                    )
                )
    r = dto.ValidacionNacional(
        contrato_version=2,
        sistema_origen=s.sistema_origen,
        id_emergencia=s.id_emergencia,
        case_id=s.case_id,
        convocatoria_id=s.convocatoria_id,
        numero=s.numero,
        evaluado_en=datetime.now(UTC),
        aportes=perfiles,
        recursos_consultados=recursos,
    )
    return dto.PerfilesRequest(**prep.model_dump(), validacion=r)


def adjudicar(
    db: Session, esc: Escenario, coord: Usuario, datos: dto.PerfilesRequest
) -> dto.AdjudicacionPreparada:
    evaluaciones.guardar_perfiles(db, esc.emergencia.id, 4242, datos)
    decision = servicio.decidir(
        db,
        esc.emergencia,
        coord,
        dto.DecisionRequest(
            decision_id=uuid4(),
            validacion_id=datos.validacion_id,
            revision=datos.revision,
            convocatoria_id=esc.convocatoria.id,
            accion="CONTINUAR_PARCIAL",
            motivo="Atender primero los aportes compatibles",
        ),
    )
    db.get(ComandoBonita, decision.id).estado = EstadoTareaBonita.COMPLETADA
    db.commit()
    adj = servicio.adjudicar(
        db,
        esc.emergencia,
        esc.operador_municipal,
        dto.AdjudicacionRequest(
            adjudicacion_id=uuid4(),
            validacion_id=datos.validacion_id,
            revision=datos.revision,
            aportes=[
                dto.Seleccion(aporte_id=p.aporte_id, cantidad=Decimal(100))
                for p in datos.validacion.aportes
            ],
        ),
    )
    return servicio.preparacion_adjudicacion(db, adj, 1)


def confirmacion(prep: dto.AdjudicacionPreparada) -> dto.ConfirmarCompromisosRequest:
    proyecto = uuid4()
    ahora = datetime.now(UTC)
    detalles = [
        dto.DetalleCompromiso(
            id=uuid4(),
            proyecto_id=proyecto,
            sistema_origen=prep.compromiso.sistema_origen,
            id_emergencia=prep.compromiso.id_emergencia,
            case_id=prep.compromiso.case_id,
            adjudicacion_id=str(prep.adjudicacion_id),
            ong_nacional_id=a.ong_nacional_id,
            estado="ACTIVO",
            creado_en=ahora,
            liberado_en=None,
            liberado_por_id=None,
            items=[
                dto.ItemCompromiso(
                    **a.model_dump(),
                    id=uuid4(),
                    convocatoria_id=str(prep.convocatoria_id),
                )
            ],
        )
        for a in prep.compromiso.aportes
    ]
    return dto.ConfirmarCompromisosRequest(
        adjudicacion_id=prep.adjudicacion_id,
        adjudicacion_version=1,
        operacion_compromiso_id=prep.operacion_compromiso_id,
        huella_request=prep.huella_request,
        confirmacion=dto.ConfirmacionCompromisos(
            operacion_id=uuid4(),
            proyecto_id=proyecto,
            compromiso_ids=[d.id for d in detalles],
            registrado_en=ahora,
        ),
        compromisos=detalles,
    )


def test_perfiles_replay_no_reactiva_revision_anterior(
    db_session: Session, escenario: Escenario, capacidad: UUID
) -> None:
    datos = preparar(db_session, escenario, capacidad)
    primera = evaluaciones.guardar_perfiles(
        db_session, escenario.emergencia.id, 4242, datos
    )
    assert primera.vigente and not primera.lotes_compatibles_cubiertos
    assert (
        evaluaciones.guardar_perfiles(db_session, escenario.emergencia.id, 4242, datos)
        == primera
    )
    nueva = evaluaciones.preparar(
        db_session,
        escenario.emergencia.id,
        4242,
        dto.PreparacionValidacion(
            validacion_id=uuid4(),
            convocatoria_id=escenario.convocatoria.id,
            intento_convocatoria=1,
        ),
    )
    assert nueva.revision == datos.revision + 1
    assert not evaluaciones.guardar_perfiles(
        db_session, escenario.emergencia.id, 4242, datos
    ).vigente
    assert (
        evaluaciones.preparar(
            db_session,
            escenario.emergencia.id,
            4242,
            dto.PreparacionValidacion(
                validacion_id=nueva.validacion_id,
                convocatoria_id=escenario.convocatoria.id,
                intento_convocatoria=1,
            ),
        )
        == nueva
    )


@pytest.mark.parametrize(
    "error",
    [
        "duplicado",
        "faltante",
        "cantidad",
        "ong",
        "caso",
        "disponibilidad",
        "recurso_ajeno",
    ],
)
def test_callback_rechaza_resultados_ajenos_sin_persistencia_parcial(
    db_session: Session, escenario: Escenario, capacidad: UUID, error: str
) -> None:
    datos = preparar(db_session, escenario, capacidad)
    r = datos.validacion
    if error == "duplicado":
        r.aportes.append(r.aportes[0])
    elif error == "faltante":
        r.aportes.clear()
    elif error == "cantidad":
        r.aportes[0].cantidad_ofrecida = Decimal(200)
    elif error == "ong":
        r.aportes[0].ong_nacional_id = uuid4()
    elif error == "caso":
        r.case_id = "9999"
    elif error == "disponibilidad":
        r.aportes[0].cantidad_disponible_consultada = Decimal(2)
    else:
        r.recursos_consultados.append(
            r.recursos_consultados[0].model_copy(
                update={"recurso_nacional_id": uuid4()}
            )
        )
    with pytest.raises(IntegracionLocalError):
        evaluaciones.guardar_perfiles(db_session, escenario.emergencia.id, 4242, datos)
    assert db_session.get(EvaluacionLocal, datos.validacion_id).resultado is None


def test_timeout_compromiso_bloquea_nueva_seleccion_y_conflicto_replay(
    db_session: Session, escenario: Escenario, capacidad: UUID, coordinador: Usuario
) -> None:
    datos = preparar(db_session, escenario, capacidad)
    prep = adjudicar(db_session, escenario, coordinador, datos)
    servicio.informar_resultado(
        db_session,
        escenario.emergencia,
        prep.operacion_compromiso_id,
        dto.ResultadoOperacionRequest(
            tipo="COMPROMISO",
            estado_integracion="INCIERTO",
            http_status=None,
            codigo_error="TIMEOUT",
            idempotency_key=prep.idempotency_key,
        ),
    )
    with pytest.raises(IntegracionLocalError):
        servicio.adjudicar(
            db_session,
            escenario.emergencia,
            escenario.operador_municipal,
            dto.AdjudicacionRequest(
                adjudicacion_id=uuid4(),
                validacion_id=datos.validacion_id,
                revision=datos.revision,
                aportes=[
                    dto.Seleccion(
                        aporte_id=datos.validacion.aportes[0].aporte_id,
                        cantidad=Decimal(100),
                    )
                ],
            ),
        )
    with pytest.raises(IntegracionLocalError):
        servicio.informar_resultado(
            db_session,
            escenario.emergencia,
            prep.operacion_compromiso_id,
            dto.ResultadoOperacionRequest(
                tipo="COMPROMISO",
                estado_integracion="RECHAZO_DEFINITIVO",
                http_status=409,
                idempotency_key=prep.idempotency_key,
            ),
        )
    r = confirmacion(prep)
    respuesta = servicio.confirmar_compromisos(db_session, escenario.emergencia, r)
    assert (
        respuesta.estado == "CONFIRMADA"
        and escenario.emergencia.estado == EstadoEmergencia.EN_EJECUCION
    )
    assert (
        servicio.confirmar_compromisos(db_session, escenario.emergencia, r) == respuesta
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Notificacion)
            .where(
                Notificacion.clave_evento
                == servicio.clave_adjudicacion(prep.adjudicacion_id)
            )
        )
        == 1
    )


def test_dos_ongs_liberan_independientemente_y_cierre_exige_confirmacion(
    db_session: Session, escenario: Escenario, capacidad: UUID, coordinador: Usuario
) -> None:
    datos = preparar(db_session, escenario, capacidad, dos_ongs=True)
    prep = adjudicar(db_session, escenario, coordinador, datos)
    r = confirmacion(prep)
    respuesta = servicio.confirmar_compromisos(db_session, escenario.emergencia, r)
    assert len(respuesta.participantes) == 2
    with pytest.raises(IntegracionLocalError):
        servicio.solicitar_cierre(db_session, escenario.emergencia, coordinador)
    for p in respuesta.participantes:
        representante = db_session.scalar(
            select(Usuario).where(Usuario.organizacion_id == p.ong_id)
        )
        f = servicio.finalizar(
            db_session, escenario.emergencia, representante, p.participacion_id
        )
        assert (
            servicio.finalizar(
                db_session, escenario.emergencia, representante, p.participacion_id
            ).id
            == f.id
        )
        liberaciones = servicio.liberaciones(db_session, escenario.emergencia, f.id)
        assert {op.compromiso_id for op in liberaciones.operaciones} == set(
            p.compromiso_ids
        )
        for op in liberaciones.operaciones:
            payload = dto.LiberacionConfirmadaRequest(
                finalizacion_id=f.id,
                participacion_id=p.participacion_id,
                operacion_id=op.operacion_id,
                confirmacion=dto.ConfirmacionLiberacion(
                    operacion_id=uuid4(),
                    proyecto_id=respuesta.proyecto_id,
                    compromiso_id=op.compromiso_id,
                    ong_nacional_id=p.ong_nacional_id,
                    liberado_en=datetime.now(UTC),
                ),
            )
            liberada = servicio.confirmar_liberacion(
                db_session, escenario.emergencia, op.compromiso_id, payload
            )
            assert liberada.estado == "LIBERADA"
            assert (
                servicio.confirmar_liberacion(
                    db_session, escenario.emergencia, op.compromiso_id, payload
                )
                == liberada
            )
        if p == respuesta.participantes[0]:
            with pytest.raises(IntegracionLocalError):
                servicio.solicitar_cierre(db_session, escenario.emergencia, coordinador)
    cierre = servicio.solicitar_cierre(db_session, escenario.emergencia, coordinador)
    assert escenario.emergencia.estado == EstadoEmergencia.EN_EJECUCION
    preparado = servicio.cierre_preparado(db_session, escenario.emergencia, cierre.id)
    payload = dto.ResolverRequest(
        id_emergencia=escenario.emergencia.id,
        estado="RESUELTA",
        proyecto_nacional_id=respuesta.proyecto_id,
        solicitud_cierre_id=cierre.id,
        operacion_cierre_id=preparado.operacion_cierre_id,
        cierre=dto.ConfirmacionCierre(
            operacion_id=uuid4(),
            proyecto_id=respuesta.proyecto_id,
            cerrado_en=datetime.now(UTC),
        ),
    )
    resolucion = servicio.resolver(db_session, escenario.emergencia, payload)
    assert resolucion.estado == EstadoEmergencia.RESUELTA
    assert servicio.resolver(db_session, escenario.emergencia, payload) == resolucion


@pytest.mark.parametrize("fallo", ["items", "proyecto", "duplicados"])
def test_confirmacion_compromisos_exige_conjunto_exacto(
    db_session: Session,
    escenario: Escenario,
    capacidad: UUID,
    coordinador: Usuario,
    fallo: str,
) -> None:
    prep = adjudicar(
        db_session, escenario, coordinador, preparar(db_session, escenario, capacidad)
    )
    r = confirmacion(prep)
    if fallo == "items":
        r.compromisos[0].items[0].cantidad = Decimal(99)
    elif fallo == "proyecto":
        r.compromisos[0].proyecto_id = uuid4()
    else:
        r.compromisos.append(r.compromisos[0])
    with pytest.raises(IntegracionLocalError):
        servicio.confirmar_compromisos(db_session, escenario.emergencia, r)
    assert escenario.emergencia.estado == EstadoEmergencia.EN_EVALUACION
    assert (
        db_session.get(OperacionNacional, prep.operacion_compromiso_id).confirmacion
        is None
    )


@pytest.mark.parametrize("accion", ["REABRIR", "REFORMULAR"])
def test_alternativas_conservan_historial_y_no_duplican_ronda(
    db_session: Session,
    escenario: Escenario,
    capacidad: UUID,
    coordinador: Usuario,
    accion: str,
) -> None:
    datos = preparar(db_session, escenario, capacidad)
    evaluaciones.guardar_perfiles(db_session, escenario.emergencia.id, 4242, datos)
    request = dto.DecisionRequest(
        decision_id=uuid4(),
        validacion_id=datos.validacion_id,
        revision=datos.revision,
        convocatoria_id=escenario.convocatoria.id,
        accion=accion,
        motivo="Revisar las necesidades de la zona",
    )
    d = servicio.decidir(db_session, escenario.emergencia, coordinador, request)
    assert (
        servicio.decidir(db_session, escenario.emergencia, coordinador, request).id
        == d.id
    )
    assert escenario.convocatoria.numero == 1
    assert (
        not evaluaciones.guardar_perfiles(
            db_session, escenario.emergencia.id, 4242, datos
        ).vigente
        if accion == "REABRIR"
        else escenario.emergencia.estado == EstadoEmergencia.EN_COORDINACION
    )


def test_endpoints_callback_y_rbac_no_confian_en_caso_o_ids_del_cliente(
    client: TestClient,
    db_session: Session,
    escenario: Escenario,
    capacidad: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    datos = preparar(db_session, escenario, capacidad)
    ruta = f"/api/v1/emergencias/{escenario.emergencia.id}"
    token = "callback-t36-prueba-32-caracteres-seguro"
    monkeypatch.setattr(get_settings(), "bonita_callback_token", SecretStr(token))
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Bonita-Root-Process-Instance-Id": "4242",
    }
    assert (
        client.post(f"{ruta}/perfiles-validacion", json=objeto(datos)).status_code
        == 401
    )
    assert (
        client.post(
            f"{ruta}/perfiles-validacion",
            headers=headers | {"X-Bonita-Root-Process-Instance-Id": "9999"},
            json=objeto(datos),
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{ruta}/perfiles-validacion", headers=headers, json=objeto(datos)
        ).status_code
        == 200
    )
    _autenticar_con_cookie(client, escenario.representante)
    assert client.get(f"{ruta}/ofertas-validadas").status_code == 403
    csrf = _autenticar_con_cookie(client, escenario.operador_municipal)
    response = client.get(f"{ruta}/ofertas-validadas")
    assert response.status_code == 200 and response.json()["diagnosticos"] == []
    assert (
        client.post(
            f"{ruta}/adjudicaciones",
            json={
                "adjudicacionId": str(uuid4()),
                "validacionId": str(datos.validacion_id),
                "revision": 1,
                "aportes": [
                    {
                        "aporteId": datos.validacion.aportes[0].aporte_id,
                        "cantidad": "100",
                    }
                ],
            },
        ).status_code
        == 403
    )
    assert csrf


def test_recorrido_http_consulta_confirmacion_finalizacion_liberacion_y_resolver(
    client: TestClient,
    db_session: Session,
    escenario: Escenario,
    capacidad: UUID,
    coordinador: Usuario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.integrations.bonita.cliente import ClienteBonita

    monkeypatch.setattr(
        ClienteBonita, "tareas_para_comando", lambda _self, _case, _nombre: []
    )
    token = "callback-t37-prueba-segura-de-32-caracteres"
    monkeypatch.setattr(get_settings(), "bonita_callback_token", SecretStr(token))
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Bonita-Root-Process-Instance-Id": "4242",
    }
    base = f"/api/v1/emergencias/{escenario.emergencia.id}"
    datos = preparar(db_session, escenario, capacidad)
    prep = adjudicar(db_session, escenario, coordinador, datos)
    consulta = client.get(
        f"{base}/adjudicaciones/{prep.adjudicacion_id}?version=1", headers=headers
    )
    assert (
        consulta.status_code == 200
        and consulta.json()["huellaRequest"] == prep.huella_request
    )
    confirmada = client.post(
        f"{base}/compromisos/confirmacion",
        headers=headers,
        json=objeto(confirmacion(prep)),
    )
    assert confirmada.status_code == 200
    participante = confirmada.json()["participantes"][0]
    csrf = _autenticar_con_cookie(client, escenario.representante)
    finalizada = client.post(
        f"{base}/participaciones/{participante['participacionId']}/finalizacion",
        headers={"X-CSRF-Token": csrf},
    )
    assert finalizada.status_code == 200
    fid = finalizada.json()["finalizacionId"]
    operaciones = client.get(
        f"{base}/finalizaciones/{fid}/liberaciones", headers=headers
    )
    assert (
        operaciones.status_code == 200 and len(operaciones.json()["operaciones"]) == 1
    )
    op = operaciones.json()["operaciones"][0]
    request = dto.LiberacionConfirmadaRequest(
        finalizacion_id=fid,
        participacion_id=participante["participacionId"],
        operacion_id=op["operacionId"],
        confirmacion=dto.ConfirmacionLiberacion(
            operacion_id=uuid4(),
            proyecto_id=confirmada.json()["proyectoId"],
            compromiso_id=op["compromisoId"],
            ong_nacional_id=participante["ongNacionalId"],
            liberado_en=datetime.now(UTC),
        ),
    )
    assert (
        client.post(
            f"{base}/compromisos/{op['compromisoId']}/liberacion-confirmada",
            headers=headers,
            json=objeto(request),
        ).status_code
        == 200
    )
    csrf = _autenticar_con_cookie(client, coordinador)
    cierre = client.post(f"{base}/solicitudes-cierre", headers={"X-CSRF-Token": csrf})
    assert cierre.status_code == 200
    c = cierre.json()
    assert (
        client.get(
            f"{base}/solicitudes-cierre/{c['solicitudCierreId']}", headers=headers
        ).status_code
        == 200
    )
    payload = dto.ResolverRequest(
        id_emergencia=escenario.emergencia.id,
        estado="RESUELTA",
        proyecto_nacional_id=c["proyectoId"],
        solicitud_cierre_id=c["solicitudCierreId"],
        operacion_cierre_id=c["operacionCierreId"],
        cierre=dto.ConfirmacionCierre(
            operacion_id=uuid4(),
            proyecto_id=c["proyectoId"],
            cerrado_en=datetime.now(UTC),
        ),
    )
    response = client.post(f"{base}/resolver", headers=headers, json=objeto(payload))
    assert response.status_code == 200 and response.json()["estado"] == "RESUELTA"


def test_recuperacion_no_vuelve_a_seleccion_ante_incertidumbre(
    db_session: Session, escenario: Escenario, capacidad: UUID, coordinador: Usuario
) -> None:
    prep = adjudicar(
        db_session, escenario, coordinador, preparar(db_session, escenario, capacidad)
    )
    servicio.informar_resultado(
        db_session,
        escenario.emergencia,
        prep.operacion_compromiso_id,
        dto.ResultadoOperacionRequest(
            tipo="COMPROMISO",
            estado_integracion="INCIERTO",
            idempotency_key=prep.idempotency_key,
        ),
    )
    with pytest.raises(IntegracionLocalError):
        servicio.recuperar(
            db_session,
            escenario.emergencia,
            coordinador,
            prep.operacion_compromiso_id,
            dto.RecuperacionRequest(
                recuperacion_id=uuid4(), accion="VOLVER_A_SELECCION"
            ),
        )
    datos = dto.RecuperacionRequest(
        recuperacion_id=uuid4(), accion="REINTENTAR_MISMA_OPERACION"
    )
    comando = servicio.recuperar(
        db_session,
        escenario.emergencia,
        coordinador,
        prep.operacion_compromiso_id,
        datos,
    )
    assert (
        servicio.recuperar(
            db_session,
            escenario.emergencia,
            coordinador,
            prep.operacion_compromiso_id,
            datos,
        ).id
        == comando.id
    )
