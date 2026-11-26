"""Genera casos de demo mediante la API local, Bonita y el Sistema Nacional."""

import argparse
import re
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.models import Convocatoria, Emergencia
from app.db.models.enums import (
    EstadoConvocatoria,
    EstadoEmergencia,
    EstadoLote,
    EstadoSincronizacionBonita,
    EstadoTareaBonita,
    GravedadEmergencia,
    TipoAporte,
)
from app.db.session import SessionLocal, engine
from app.integrations.bonita.cliente import (
    ClienteBonita,
    ConfiguracionBonita,
    ErrorBonita,
)
from app.integrations.bonita.contratos import (
    CABECERA_CASO_RAIZ,
    TAREA_GENERAR_LOTES,
    TemporizadorBonita,
)
from app.schemas import ejecucion as bpm
from app.schemas.auth import SesionResponse
from app.schemas.bonita import NotificacionAperturaRequest
from app.schemas.convocatoria import ConvocatoriaResponse
from app.schemas.emergencia import (
    EmergenciaConPrioridadCreate,
    EmergenciaResponse,
    PrioridadEmergenciaResponse,
    SolicitudPrioridadEmergencia,
    ZonaPrioridad,
)
from app.schemas.inventario import CapacidadResponse, RecursoCreate, RecursoResponse
from app.schemas.lote import LoteItem, LoteResponse, LotesRequest
from app.schemas.metricas import ZONA_REPORTES
from app.schemas.oferta import (
    AporteRequest,
    ConfirmacionConsorcioRequest,
    ConsorcioRequest,
    OfertaCreateRequest,
    OfertaItemRequest,
    OfertaResponse,
)

SELECCIONAR = "Seleccionar ofertas validadas"
EVALUAR = "Evalua situacion"
FINALIZAR = "Marcar como finalizada la tarea"
CERRAR = "Marcar proyecto como terminado"
ESPERAR_OFERTAS = "EsperarOfertas"
API_LOCAL = "http://127.0.0.1:8000/api/v1"

type CantidadesOferta = tuple[int, int]


@dataclass(frozen=True)
class Escenario:
    nombre: str
    gravedad: GravedadEmergencia
    zona: ZonaPrioridad
    demanda: int = 5
    ofertas: CantidadesOferta = (5, 0)
    decision: bpm.AccionEvaluacion | None = None
    destino: Literal["RESUELTA", "EN_EJECUCION", "REGISTRADA", "PUBLICADA"] = "RESUELTA"
    capacidad: str = "PARAMEDICOS"

    @property
    def ofertas_finales(self) -> CantidadesOferta:
        if self.decision is bpm.AccionEvaluacion.REABRIR:
            return (0, self.demanda)
        return self.ofertas


ESCENARIOS = (
    Escenario("HIST-01 Consorcio", GravedadEmergencia.ALTA, "SUR", 10, (6, 4)),
    Escenario("HIST-02 Total individual", GravedadEmergencia.MEDIA, "CENTRO"),
    Escenario(
        "HIST-03 Reapertura",
        GravedadEmergencia.ALTA,
        "SUR",
        ofertas=(3, 0),
        decision=bpm.AccionEvaluacion.REABRIR,
    ),
    Escenario(
        "HIST-04 Reformulación",
        GravedadEmergencia.ALTA,
        "SUR",
        ofertas=(3, 0),
        decision=bpm.AccionEvaluacion.REFORMULAR,
    ),
    Escenario(
        "HIST-05 Cierre parcial",
        GravedadEmergencia.MEDIA,
        "CENTRO",
        ofertas=(3, 0),
        decision=bpm.AccionEvaluacion.CONTINUAR_PARCIAL,
    ),
    Escenario(
        "HIST-06 Distribución de agua",
        GravedadEmergencia.BAJA,
        "NORTE",
        demanda=20,
        ofertas=(20, 0),
        capacidad="AGUA",
    ),
    Escenario(
        "HIST-07 Asistencia alimentaria",
        GravedadEmergencia.CRITICA,
        "SUR",
        demanda=25,
        ofertas=(0, 25),
        capacidad="ALIMENTOS",
    ),
    Escenario(
        "ACTIVO Recursos comprometidos",
        GravedadEmergencia.ALTA,
        "SUR",
        destino="EN_EJECUCION",
    ),
    Escenario(
        "PENDIENTE Generar lotes",
        GravedadEmergencia.MEDIA,
        "NORTE",
        destino="REGISTRADA",
    ),
)
CONVOCATORIA_ABIERTA = Escenario(
    "ABIERTA Convocatoria en curso",
    GravedadEmergencia.MEDIA,
    "CENTRO",
    ofertas=(3, 0),
    destino="PUBLICADA",
)


class ErrorSeed(RuntimeError):
    """Indica qué paso requiere atención antes de continuar la corrida."""


@dataclass(frozen=True)
class VentanaDemo:
    segundos: int
    callbacks: httpx.Client


class ApiDemo:
    """Mantiene una sesión local y el CSRF de su rol de demostración."""

    def __init__(self, cliente: httpx.Client, cuenta: str) -> None:
        self.cliente = cliente
        sesion = self.enviar(
            "POST",
            "/auth/login",
            SesionResponse,
            {"email": f"{cuenta}@rescuesync.org", "password": f"{cuenta}123"},
        )
        self.cliente.headers["X-CSRF-Token"] = sesion.csrf_token
        self.organizacion_id = (
            sesion.usuario.organizacion.id if sesion.usuario.organizacion else None
        )

    def enviar[T](
        self,
        metodo: str,
        ruta: str,
        tipo: type[T],
        datos: BaseModel | dict[str, str] | None = None,
        *,
        params: dict[str, str] | None = None,
    ) -> T:
        try:
            respuesta = self.cliente.request(
                metodo,
                ruta,
                json=datos.model_dump(mode="json")
                if isinstance(datos, BaseModel)
                else datos,
                params=params,
            )
            respuesta.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise ErrorSeed(
                f"{metodo} {ruta} devolvió HTTP {error.response.status_code}."
            ) from error
        except httpx.RequestError as error:
            raise ErrorSeed(f"No se confirmó {metodo} {ruta}.") from error
        return TypeAdapter(tipo).validate_json(respuesta.content)


def _ultima_ronda(emergencia_id: int) -> Convocatoria | None:
    with SessionLocal() as session:
        return session.scalar(
            select(Convocatoria)
            .where(Convocatoria.emergencia_id == emergencia_id)
            .options(selectinload(Convocatoria.lotes))
            .order_by(Convocatoria.numero.desc())
            .limit(1)
        )


def _recurso(ong: ApiDemo, capacidad: CapacidadResponse, marca: str) -> RecursoResponse:
    sufijo = "PP" if capacidad.codigo == "PARAMEDICOS" else capacidad.codigo
    codigo = f"DEMO-{marca}-{sufijo}"
    recursos = ong.enviar("GET", "/mi-ong/recursos", list[RecursoResponse])
    recurso = next((r for r in recursos if r.codigo_interno == codigo), None)
    if recurso is None:
        return ong.enviar(
            "POST",
            "/mi-ong/recursos",
            RecursoResponse,
            RecursoCreate(
                capacidad_id=capacidad.id,
                codigo_interno=codigo,
                nombre=f"{marca} · {capacidad.nombre} de demo",
                cantidad_total=30,
            ),
        )
    if (
        not recurso.activo
        or recurso.capacidad_id != capacidad.id
        or recurso.cantidad_total < 30
    ):
        raise ErrorSeed(
            f"Revisá el recurso existente {codigo}; se requieren al menos 30 {capacidad.unidad} y estado activo."
        )
    return recurso


@dataclass(frozen=True)
class Corrida:
    marca: str
    espera_ronda: int
    municipio: ApiDemo
    coordinador: ApiDemo
    ongs: tuple[ApiDemo, ApiDemo]
    recursos: tuple[RecursoResponse, RecursoResponse]
    capacidad: CapacidadResponse
    bonita: ClienteBonita
    proceso_id: int
    interrumpida: Event
    ventana_demo: VentanaDemo | None

    def ejecutar(self, escenario: Escenario) -> None:
        detalle = (
            "Asistencia paramédica"
            if escenario.capacidad == "PARAMEDICOS"
            else self.capacidad.nombre
        )
        descripcion = f"[DEMO {self.marca}] {escenario.nombre} · {detalle}"
        emergencia = self._emergencia(escenario, descripcion)
        caso = emergencia.bonita_process_instance_id
        if caso is None:
            raise ErrorSeed(
                f"Emergencia {emergencia.id}: {emergencia.bonita_ultimo_error or 'sin caso Bonita'}"
            )
        print(
            f"{escenario.nombre}: emergencia {emergencia.id}, caso Bonita {caso}.",
            flush=True,
        )
        if escenario.destino == "REGISTRADA":
            self._tarea(caso, TAREA_GENERAR_LOTES)
            return
        ruta = f"/emergencias/{emergencia.id}"
        if escenario.destino == "PUBLICADA":
            self._dejar_convocatoria_abierta(
                escenario, emergencia.id, caso, ruta, descripcion
            )
            return
        seguimiento = self.municipio.enviar(
            "GET", f"{ruta}/adjudicaciones", bpm.SeguimientoResponse
        )
        if not seguimiento.adjudicaciones:
            self._adjudicar(escenario, emergencia.id, caso, ruta, descripcion)
        else:
            for pendiente in seguimiento.adjudicaciones:
                if pendiente.estado == "PENDIENTE_COMPROMISO":
                    self._despacho_previo(
                        self.municipio, ruta, pendiente.adjudicacion_id
                    )
        adjudicacion = self._esperar(
            caso,
            "compromiso nacional confirmado",
            lambda: next(
                (
                    a
                    for a in self._seguimiento(ruta).adjudicaciones
                    if a.estado == "CONFIRMADA"
                ),
                None,
            ),
        )
        if escenario.destino == "EN_EJECUCION":
            if any(p.estado != "EN_EJECUCION" for p in adjudicacion.participantes):
                raise ErrorSeed(
                    f"El caso activo {caso} ya avanzó desde el punto de demo."
                )
            self._tarea(caso, FINALIZAR)
        else:
            self._cerrar(ruta, caso, adjudicacion)
            self._esperar(
                caso,
                "cierre y archivo en Bonita",
                lambda: (
                    True
                    if (
                        self._seguimiento(ruta).estado is EstadoEmergencia.RESUELTA
                        and self.bonita.tarea_completada(caso, CERRAR)
                        and not self.bonita.buscar_casos_por_emergencia(
                            self.proceso_id, emergencia.id
                        )
                    )
                    else None
                ),
            )
        ids = ", ".join(
            str(c) for p in adjudicacion.participantes for c in p.compromiso_ids
        )
        print(
            f"{escenario.nombre}: {escenario.destino} · proyecto {adjudicacion.proyecto_id} · compromisos {ids}.",
            flush=True,
        )

    def _emergencia(self, escenario: Escenario, descripcion: str) -> EmergenciaResponse:
        with SessionLocal() as session:
            existente = session.scalars(
                select(Emergencia).where(
                    Emergencia.municipio_id == self.municipio.organizacion_id,
                    Emergencia.descripcion == descripcion,
                )
            ).one_or_none()
        if existente is not None:
            if existente.bonita_sync is EstadoSincronizacionBonita.VINCULADA:
                return EmergenciaResponse.model_validate(existente)
            return self.municipio.enviar(
                "POST",
                f"/emergencias/{existente.id}/reintentar-bonita",
                EmergenciaResponse,
            )
        datos = SolicitudPrioridadEmergencia(
            gravedad=escenario.gravedad, zona=escenario.zona
        )
        prioridad = self.municipio.enviar(
            "POST", "/emergencias/prioridad", PrioridadEmergenciaResponse, datos
        )
        return self.municipio.enviar(
            "POST",
            "/emergencias",
            EmergenciaResponse,
            EmergenciaConPrioridadCreate(
                gravedad=datos.gravedad,
                zona=datos.zona,
                descripcion=descripcion,
                comprobante_prioridad=prioridad.comprobante,
            ),
        )

    def _esperar[T](
        self,
        caso: int,
        paso: str,
        obtener: Callable[[], T | None],
        *,
        segundos: int = 120,
        intervalo: int = 3,
    ) -> T:
        fin = time.monotonic() + segundos
        while not self.interrumpida.is_set():
            resultado = obtener()
            if resultado is not None:
                return resultado
            fallidas = [
                n.name
                for n in self.bonita.listar_tareas_fallidas()
                if n.root_case_id == caso
            ]
            if fallidas:
                raise ErrorSeed(
                    f"Caso Bonita {caso}, {paso}: tareas fallidas {', '.join(fallidas)}."
                )
            restante = fin - time.monotonic()
            if restante <= 0:
                raise ErrorSeed(f"Caso Bonita {caso}: se agotó la espera de {paso}.")
            self.interrumpida.wait(min(intervalo, restante))
        raise ErrorSeed(f"Caso Bonita {caso}: corrida interrumpida durante {paso}.")

    def _tarea(self, caso: int, nombre: str) -> None:
        self._esperar(
            caso, nombre, lambda: self.bonita.tareas_para_comando(caso, nombre) or None
        )

    def _publicar(self, ruta: str, caso: int, cantidad: int, *, nueva: bool) -> None:
        if nueva:
            self._tarea(caso, TAREA_GENERAR_LOTES)
            lotes = self.coordinador.enviar("GET", f"{ruta}/lotes", list[LoteResponse])
            borrador = next((l for l in lotes if l.estado is EstadoLote.BORRADOR), None)
            if borrador is None or borrador.cantidad_requerida != cantidad:
                self.coordinador.enviar(
                    "POST",
                    f"{ruta}/lotes",
                    list[LoteResponse],
                    LotesRequest(
                        lotes=[
                            LoteItem(
                                id=borrador.id if borrador else None,
                                version=borrador.version if borrador else None,
                                cantidad_requerida=cantidad,
                                capacidad_nacional_id=self.capacidad.id,
                                tipo_necesidad=self.capacidad.nombre,
                                unidad=self.capacidad.unidad,
                            )
                        ]
                    ),
                )
        publicada = self.coordinador.enviar(
            "POST", f"{ruta}/publicar", ConvocatoriaResponse
        )
        if publicada.bonita_generar_lotes_estado is not EstadoTareaBonita.COMPLETADA:
            raise ErrorSeed(
                f"Publicación {publicada.id}: {publicada.bonita_generar_lotes_ultimo_error or publicada.bonita_generar_lotes_estado}."
            )

    def _ofertar(
        self, ronda: Convocatoria, cantidades: CantidadesOferta, descripcion: str
    ) -> None:
        if ronda.estado is not EstadoConvocatoria.ABIERTA:
            return
        (lote,) = ronda.lotes
        ofertas = []
        for ong, recurso, cantidad in zip(
            self.ongs, self.recursos, cantidades, strict=True
        ):
            if not cantidad:
                continue
            previas = ong.enviar(
                "GET", "/ofertas", list[OfertaResponse], params={"q": descripcion}
            )
            oferta = next((o for o in previas if o.convocatoria_id == ronda.id), None)
            if oferta is None:
                oferta = ong.enviar(
                    "POST",
                    "/ofertas",
                    OfertaResponse,
                    OfertaCreateRequest(
                        convocatoria_id=ronda.id,
                        items=[
                            OfertaItemRequest(
                                lote_id=lote.lote_id,
                                tipo=TipoAporte.PERSONAL
                                if self.capacidad.tipo == "PERSONAL"
                                else TipoAporte.RECURSO,
                                descripcion=f"{self.capacidad.nombre} para la emergencia de demostración",
                                cantidad_ofrecida=cantidad,
                                unidad=lote.unidad_publicada,
                                aportes=[
                                    AporteRequest(
                                        recurso_nacional_id=recurso.id,
                                        cantidad=cantidad,
                                    )
                                ],
                            )
                        ],
                    ),
                )
            ofertas.append(oferta)
        if len(ofertas) == 2:
            lider, socia = ofertas
            ruta = f"/ofertas/{lider.id}/consorcio"
            if lider.id != socia.id:
                lider = self.ongs[0].enviar(
                    "POST",
                    ruta,
                    OfertaResponse,
                    ConsorcioRequest(
                        version_bloqueo=lider.version_bloqueo,
                        ong_ids=[socia.ong_creadora_id],
                    ),
                )
            for ong in self.ongs:
                if any(
                    p.ong_id == ong.organizacion_id and not p.confirmada
                    for p in lider.participantes
                ):
                    lider = ong.enviar(
                        "POST",
                        f"{ruta}/confirmacion",
                        OfertaResponse,
                        ConfirmacionConsorcioRequest(
                            version_bloqueo=lider.version_bloqueo
                        ),
                    )

    def _evaluacion(self, ruta: str, caso: int) -> bpm.OfertasValidadasResponse:
        def consultar() -> bpm.OfertasValidadasResponse | None:
            datos = self.municipio.enviar(
                "GET", f"{ruta}/ofertas-validadas", bpm.OfertasValidadasResponse
            )
            return datos if datos.validacion and datos.validacion.vigente else None

        return self._esperar(
            caso,
            "cierre de la ventana y validación nacional",
            consultar,
            segundos=self.espera_ronda,
            intervalo=10,
        )

    def _acortar_ventana(self, ronda: Convocatoria, caso: int, ruta: str) -> None:
        """Reprograma el timer de esta ronda tras presentar las ofertas del seed."""
        ajuste = self.ventana_demo
        if ajuste is None or ronda.estado is not EstadoConvocatoria.ABIERTA:
            return

        def consultar() -> tuple[Convocatoria, TemporizadorBonita | None] | None:
            actual = _ultima_ronda(ronda.emergencia_id)
            if actual is None or actual.id != ronda.id:
                raise ErrorSeed(f"La convocatoria vigente del caso {caso} cambió.")
            if actual.estado is not EstadoConvocatoria.ABIERTA:
                return actual, None
            timer = self.bonita.buscar_temporizador(caso, ESPERAR_OFERTAS)
            return (actual, timer) if timer else None

        actual, timer = self._esperar(caso, ESPERAR_OFERTAS, consultar)
        if timer is None:
            return
        fecha_ms = min(
            timer.execution_date_ms,
            time.time_ns() // 1_000_000 + ajuste.segundos * 1000,
        )
        if fecha_ms < timer.execution_date_ms:
            self.bonita.reprogramar_temporizador(timer.id, fecha_ms)
        if fecha_ms != round(actual.cierra_en.timestamp() * 1000):
            datos = NotificacionAperturaRequest(
                id_emergencia=actual.emergencia_id,
                intento_convocatoria=actual.numero,
                fecha_cierre_ofertas=datetime.fromtimestamp(fecha_ms / 1000, UTC),
            )
            try:
                respuesta = ajuste.callbacks.post(
                    f"{ruta}/notificar-apertura",
                    headers={CABECERA_CASO_RAIZ: str(caso)},
                    json=datos.model_dump(mode="json"),
                )
                respuesta.raise_for_status()
            except httpx.HTTPError as error:
                with SessionLocal() as session:
                    guardada = session.get(Convocatoria, actual.id)
                    if guardada is None or (
                        guardada.estado is EstadoConvocatoria.ABIERTA
                        and round(guardada.cierra_en.timestamp() * 1000) != fecha_ms
                    ):
                        raise ErrorSeed(
                            f"Bonita programó la ronda {actual.numero} del caso {caso}, "
                            "pero no se confirmó su vencimiento local. Repetí la misma corrida."
                        ) from error
        fecha = datetime.fromtimestamp(fecha_ms / 1000, ZONA_REPORTES)
        print(
            f"Caso Bonita {caso}, ronda {ronda.numero}: cierre previsto {fecha:%H:%M:%S %Z}.",
            flush=True,
        )

    def _despacho_previo(self, api: ApiDemo, ruta: str, identidad: UUID) -> bool:
        comandos = api.enviar(
            "GET", f"{ruta}/comandos-bonita", list[bpm.DespachoResponse]
        )
        comando = next((c for c in comandos if c.comando_id == identidad), None)
        if comando is None:
            return False
        if comando.estado != EstadoTareaBonita.COMPLETADA:
            comando = api.enviar(
                "POST",
                f"{ruta}/comandos-bonita/{identidad}/reintentar",
                bpm.DespachoResponse,
            )
            if comando.estado != EstadoTareaBonita.COMPLETADA:
                raise ErrorSeed(
                    f"Comando {identidad}: {comando.error or comando.estado}."
                )
        return True

    def _decidir(
        self,
        ruta: str,
        caso: int,
        identidad: UUID,
        validacion: bpm.PerfilesResponse,
        accion: bpm.AccionEvaluacion,
    ) -> None:
        self._tarea(caso, EVALUAR)
        self.coordinador.enviar(
            "POST",
            f"{ruta}/decision-evaluacion",
            bpm.DecisionResponse,
            bpm.DecisionRequest(
                decision_id=identidad,
                validacion_id=validacion.validacion_id,
                revision=validacion.revision,
                convocatoria_id=validacion.convocatoria_id,
                accion=accion,
                motivo="Ajustar la respuesta del escenario de demostración.",
            ),
        )
        self._despacho_previo(self.coordinador, ruta, identidad)

    def _dejar_convocatoria_abierta(
        self,
        escenario: Escenario,
        emergencia_id: int,
        caso: int,
        ruta: str,
        descripcion: str,
    ) -> None:
        ronda = _ultima_ronda(emergencia_id)
        if ronda is None or (
            ronda.numero == 1
            and ronda.estado is EstadoConvocatoria.ABIERTA
            and ronda.bonita_generar_lotes_estado is not EstadoTareaBonita.COMPLETADA
        ):
            self._publicar(ruta, caso, escenario.demanda, nueva=ronda is None)
            ronda = _ultima_ronda(emergencia_id)
        assert ronda is not None

        if ronda.numero > 1:
            self._despacho_previo(
                self.coordinador, ruta, _id_reapertura(caso, ronda.numero - 1)
            )
        if (
            ronda.estado is not EstadoConvocatoria.ABIERTA
            or ronda.cierra_en <= datetime.now(UTC)
        ):
            evaluacion = self._evaluacion(ruta, caso)
            validacion = evaluacion.validacion
            assert validacion is not None
            if validacion.lotes_compatibles_cubiertos:
                raise ErrorSeed(
                    f"La ronda {ronda.id} alcanzó cobertura completa y avanzó a selección."
                )
            self._decidir(
                ruta,
                caso,
                _id_reapertura(caso, ronda.numero),
                validacion,
                bpm.AccionEvaluacion.REABRIR,
            )
            ronda = _ultima_ronda(emergencia_id)
            assert ronda is not None
        self._ofertar(ronda, escenario.ofertas, descripcion)
        print(
            f"{escenario.nombre}: convocatoria {ronda.id} abierta en la ronda {ronda.numero}.",
            flush=True,
        )

    def _adjudicar(
        self,
        escenario: Escenario,
        emergencia_id: int,
        caso: int,
        ruta: str,
        descripcion: str,
    ) -> None:
        ronda = _ultima_ronda(emergencia_id)
        if ronda is None:
            self._publicar(ruta, caso, escenario.demanda, nueva=True)
            ronda = _ultima_ronda(emergencia_id)
        assert ronda is not None
        if ronda.numero == 1 and ronda.estado is EstadoConvocatoria.ABIERTA:
            if ronda.bonita_generar_lotes_estado is not EstadoTareaBonita.COMPLETADA:
                self._publicar(ruta, caso, escenario.demanda, nueva=False)
            self._ofertar(ronda, escenario.ofertas, descripcion)
            self._acortar_ventana(ronda, caso, ruta)

        accion = escenario.decision
        if accion is not None:
            identidad = uuid5(
                NAMESPACE_URL, f"rescuesync:{caso}:{emergencia_id}:decision-demo"
            )
            if not self._despacho_previo(self.coordinador, ruta, identidad):
                evaluacion = self._evaluacion(ruta, caso)
                validacion = evaluacion.validacion
                assert validacion is not None
                if not evaluacion.aportes:
                    raise ErrorSeed(
                        f"La ronda {ronda.id} cerró sin aportes compatibles."
                    )
                self._decidir(ruta, caso, identidad, validacion, accion)
            if accion is bpm.AccionEvaluacion.REFORMULAR and ronda.numero == 1:
                self._publicar(ruta, caso, sum(escenario.ofertas_finales), nueva=True)
            if accion is not bpm.AccionEvaluacion.CONTINUAR_PARCIAL:
                ronda = _ultima_ronda(emergencia_id)
                if ronda is None or ronda.numero != 2:
                    raise ErrorSeed(f"No se confirmó la segunda ronda del caso {caso}.")
                if (
                    accion is bpm.AccionEvaluacion.REFORMULAR
                    and ronda.estado is EstadoConvocatoria.ABIERTA
                    and ronda.bonita_generar_lotes_estado
                    is not EstadoTareaBonita.COMPLETADA
                ):
                    self._publicar(
                        ruta, caso, sum(escenario.ofertas_finales), nueva=False
                    )
                self._ofertar(ronda, escenario.ofertas_finales, descripcion)
                self._acortar_ventana(ronda, caso, ruta)

        evaluacion = self._evaluacion(ruta, caso)
        validacion = evaluacion.validacion
        assert validacion is not None
        esperadas = {
            recurso.id: cantidad
            for recurso, cantidad in zip(
                self.recursos, escenario.ofertas_finales, strict=True
            )
            if cantidad
        }
        observadas = {
            a.recurso_nacional_id: a.cantidad_ofrecida for a in evaluacion.aportes
        }
        if validacion.convocatoria_id != ronda.id or observadas != esperadas:
            raise ErrorSeed(
                f"Los aportes validados de la ronda {ronda.id} difieren del escenario."
            )
        self._tarea(caso, SELECCIONAR)
        self.municipio.enviar(
            "POST",
            f"{ruta}/adjudicaciones",
            bpm.AdjudicacionResponse,
            bpm.AdjudicacionRequest(
                adjudicacion_id=uuid5(
                    NAMESPACE_URL,
                    f"rescuesync:{caso}:{emergencia_id}:adjudicacion-demo",
                ),
                validacion_id=validacion.validacion_id,
                revision=validacion.revision,
                aportes=[
                    bpm.Seleccion(aporte_id=a.aporte_id, cantidad=a.cantidad_ofrecida)
                    for a in evaluacion.aportes
                ],
            ),
        )

    def _seguimiento(self, ruta: str) -> bpm.SeguimientoResponse:
        return self.coordinador.enviar(
            "GET", f"{ruta}/adjudicaciones", bpm.SeguimientoResponse
        )

    def _cerrar(
        self, ruta: str, caso: int, adjudicacion: bpm.AdjudicacionResponse
    ) -> None:
        for p in adjudicacion.participantes:
            if p.estado == "LIBERADA":
                continue
            ong = next(o for o in self.ongs if o.organizacion_id == p.ong_id)
            if p.finalizacion_id and self._despacho_previo(
                ong, ruta, p.finalizacion_id
            ):
                continue
            self._tarea(caso, FINALIZAR)
            ong.enviar(
                "POST",
                f"{ruta}/participaciones/{p.participacion_id}/finalizacion",
                bpm.FinalizacionResponse,
                bpm.FinalizacionRequest(
                    cantidades=[
                        bpm.CantidadFinalizada(
                            lote_id=l.lote_id,
                            movilizada=l.cantidad,
                            cumplida=l.cantidad,
                        )
                        for l in p.lotes
                    ]
                ),
            )
        if self._seguimiento(ruta).estado is EstadoEmergencia.RESUELTA:
            return

        def listo_para_cerrar() -> bpm.SeguimientoResponse | None:
            seguimiento = self._seguimiento(ruta)
            return (
                seguimiento
                if seguimiento.puede_solicitar_cierre or seguimiento.cierre
                else None
            )

        seguimiento = self._esperar(caso, "liberaciones nacionales", listo_para_cerrar)
        if seguimiento.cierre:
            self._despacho_previo(
                self.coordinador, ruta, seguimiento.cierre.solicitud_cierre_id
            )
        else:
            self._tarea(caso, CERRAR)
            self.coordinador.enviar(
                "POST", f"{ruta}/solicitudes-cierre", bpm.CierrePreparado
            )


def _id_reapertura(caso: int, numero: int) -> UUID:
    return uuid5(NAMESPACE_URL, f"rescuesync:{caso}:{numero}:reapertura-demo-abierta")


def _ejecutar(marca: str, espera_ronda: int, ventana_segundos: int | None) -> int:
    settings = get_settings()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conexion:
        bloqueo = text("SELECT pg_try_advisory_lock(928531, 1)")
        if not conexion.scalar(bloqueo):
            raise ErrorSeed("Ya hay una corrida del seed operativo en esta base.")
        try:
            return _cargar(
                marca,
                espera_ronda,
                ConfiguracionBonita.desde_settings(settings),
                ventana_segundos,
            )
        finally:
            conexion.execute(text("SELECT pg_advisory_unlock(928531, 1)"))


def _cargar(
    marca: str,
    espera_ronda: int,
    config: ConfiguracionBonita,
    ventana_segundos: int | None,
) -> int:
    def cliente(cuenta: str) -> ApiDemo:
        http = recursos_abiertos.enter_context(
            httpx.Client(base_url=API_LOCAL, timeout=60, trust_env=False)
        )
        return ApiDemo(http, cuenta)

    with ExitStack() as recursos_abiertos:
        ventana_demo = None
        if ventana_segundos is not None:
            token = get_settings().bonita_callback_token
            if token is None:
                raise ErrorSeed(
                    "Configurá BONITA_CALLBACK_TOKEN para sincronizar el plazo acortado."
                )
            callbacks = recursos_abiertos.enter_context(
                httpx.Client(
                    base_url=API_LOCAL,
                    timeout=10,
                    trust_env=False,
                    headers={"Authorization": f"Bearer {token.get_secret_value()}"},
                )
            )
            ventana_demo = VentanaDemo(ventana_segundos, callbacks)
        bonita = recursos_abiertos.enter_context(ClienteBonita(config))
        proceso = bonita.obtener_proceso_habilitado()
        municipio, coordinador = cliente("municipio"), cliente("coordinador")
        ongs = (cliente("ong"), cliente("redmedica"))
        capacidades = coordinador.enviar(
            "GET",
            "/emergencias/catalogos/capacidades-nacionales",
            list[CapacidadResponse],
        )
        catalogo = {c.codigo: c for c in capacidades}
        interrumpida = Event()
        por_capacidad: dict[str, Corrida] = {}
        for codigo in dict.fromkeys(
            e.capacidad for e in (*ESCENARIOS, CONVOCATORIA_ABIERTA)
        ):
            capacidad = catalogo.get(codigo)
            if capacidad is None:
                raise ErrorSeed(f"El catálogo nacional no tiene la capacidad {codigo}.")
            recursos = (
                _recurso(ongs[0], capacidad, marca),
                _recurso(ongs[1], capacidad, marca),
            )
            por_capacidad[codigo] = Corrida(
                marca,
                espera_ronda,
                municipio,
                coordinador,
                ongs,
                recursos,
                capacidad,
                bonita,
                proceso.id,
                interrumpida,
                ventana_demo,
            )
        errores = 0
        with ThreadPoolExecutor(max_workers=len(ESCENARIOS)) as pool:
            tareas = {
                pool.submit(
                    por_capacidad[escenario.capacidad].ejecutar, escenario
                ): escenario
                for escenario in ESCENARIOS
            }
            try:
                for tarea in as_completed(tareas):
                    try:
                        tarea.result()
                    except (
                        ErrorSeed,
                        ErrorBonita,
                        SQLAlchemyError,
                        ValidationError,
                    ) as error:
                        errores += 1
                        _imprimir_error(tareas[tarea].nombre, error)
                if not errores:
                    por_capacidad[CONVOCATORIA_ABIERTA.capacidad].ejecutar(
                        CONVOCATORIA_ABIERTA
                    )
            finally:
                interrumpida.set()
        return errores


def _imprimir_error(contexto: str, error: Exception) -> None:
    detalle = (
        str(error)
        if isinstance(error, (ErrorSeed, ErrorBonita))
        else type(error).__name__
    )
    print(f"{contexto}: {detalle}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corrida",
        default="DEMO-01",
        help="Marca de 1 a 24 caracteres alfanuméricos o guiones.",
    )
    parser.add_argument(
        "--espera-ronda-segundos",
        type=int,
        default=7500,
        help="Tiempo máximo para esperar cada ventana y su validación.",
    )
    parser.add_argument(
        "--ventana-segundos",
        type=int,
        help="Acorta las rondas que avanza el seed una vez presentadas sus ofertas.",
    )
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{0,23}", marca := args.corrida.upper()):
        parser.error(
            "Usá de 1 a 24 caracteres ASCII alfanuméricos o guiones para --corrida."
        )
    if args.espera_ronda_segundos <= 0:
        parser.error("--espera-ronda-segundos debe ser positivo.")
    if args.ventana_segundos is not None and args.ventana_segundos <= 0:
        parser.error("--ventana-segundos debe ser positivo.")
    if get_settings().app_env.casefold() not in {"development", "test"}:
        parser.error("El seed operativo está disponible en desarrollo y pruebas.")

    try:
        errores = _ejecutar(marca, args.espera_ronda_segundos, args.ventana_segundos)
    except (ErrorSeed, ErrorBonita, ValidationError, SQLAlchemyError) as error:
        _imprimir_error(f"Corrida {marca}", error)
        errores = 1
    except KeyboardInterrupt:
        errores = 1
    if errores:
        print(
            f"Corrida {marca} incompleta. Se preservaron los datos y casos; repetí la misma marca para retomar.",
            file=sys.stderr,
        )
        return 1
    print(f"Corrida {marca} lista. Abrí el tablero como auditor@rescuesync.org.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
