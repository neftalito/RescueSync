"""Calcula duraciones observadas sin inferir cierres desde timestamps locales."""

from collections import defaultdict
from datetime import UTC, datetime
from time import monotonic
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Emergencia
from app.integrations.bonita.cliente import (
    BonitaCredencialesError,
    BonitaNoDisponibleError,
    ClienteBonita,
    ErrorBonita,
)
from app.integrations.bonita.contratos import TareaActiva, TransicionTareaArchivada
from app.schemas.metricas import (
    ActividadActual,
    DisponibilidadBonita,
    FiltrosMetricas,
    ReporteTiempos,
    ResumenActividad,
    TiempoEtapa,
)
from app.services.filtros_metricas import emergencias_filtradas


def fecha_bonita(valor: str | None, zona: ZoneInfo) -> datetime | None:
    """Normaliza fechas del Runtime; una fecha ausente no implica duración cero."""
    if not valor:
        return None
    try:
        fecha = datetime.fromisoformat(valor)
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=zona)
        return fecha.astimezone(UTC)
    except ValueError:
        return None


def actividades_actuales(
    emergencia: Emergencia,
    tareas: list[TareaActiva],
    historial: list[TransicionTareaArchivada],
    zona: ZoneInfo,
    ahora: datetime,
) -> list[ActividadActual]:
    """Mide antigüedad desde el primer estado conocido de cada ejecución activa."""
    resultado: list[ActividadActual] = []
    for tarea in {t.id: t for t in tareas}.values():
        if tarea.tipo not in {
            "USER_TASK",
            "AUTOMATIC_TASK",
            "MANUAL_TASK",
        } or tarea.state in {"completed", "aborted", "cancelled", "skipped"}:
            continue
        observadas = [tarea.reached_state_date] + [
            h.reached_state_date
            for h in historial
            if h.source_object_id == tarea.id
            and h.state not in {"completed", "aborted", "cancelled", "skipped"}
        ]
        fechas = [
            f
            for valor in observadas
            if (f := fecha_bonita(valor, zona)) is not None and f <= ahora
        ]
        desde = min(fechas) if fechas else None
        vence = fecha_bonita(tarea.due_date, zona)
        resultado.append(
            ActividadActual(
                emergencia_id=emergencia.id,
                municipio_id=emergencia.municipio_id,
                gravedad=emergencia.gravedad,
                case_id=tarea.root_case_id,
                tarea_id=tarea.id,
                etapa=tarea.name,
                version_proceso=emergencia.bonita_process_version or "Sin versión",
                estado=tarea.state,
                desde_en=desde,
                antiguedad_segundos=(ahora - desde).total_seconds() if desde else None,
                vence_en=vence,
                vencida=vence < ahora if vence else None,
            )
        )
    return resultado


def resumir_actividad(tareas: list[ActividadActual]) -> list[ResumenActividad]:
    """Informa espera media y carga actual, conservando la cobertura temporal."""
    grupos: dict[tuple[str, str], list[ActividadActual]] = defaultdict(list)
    for tarea in tareas:
        grupos[(tarea.etapa, tarea.version_proceso)].append(tarea)
    resultado: list[ResumenActividad] = []
    for (etapa, version), filas in sorted(grupos.items()):
        edades = [
            f.antiguedad_segundos for f in filas if f.antiguedad_segundos is not None
        ]
        resultado.append(
            ResumenActividad(
                etapa=etapa,
                version_proceso=version,
                tareas=len(filas),
                con_fecha=len(edades),
                promedio_antiguedad_segundos=sum(edades) / len(edades)
                if edades
                else None,
                vencidas=sum(f.vencida is True for f in filas),
                sin_plazo=sum(f.vence_en is None for f in filas),
                fallidas=sum(f.estado == "failed" for f in filas),
            )
        )
    return resultado


def duraciones_tareas(
    historial: list[TransicionTareaArchivada], zona: ZoneInfo
) -> tuple[list[tuple[str, float]], int]:
    """Mide cada tarea completada desde su primera transición observada.

    Las fechas de Bonita sin offset usan la zona del Runtime. Se deduplican
    transiciones de una misma ejecución. Una tarea sin
    inicio, con fechas inválidas o cancelada nunca aporta una duración cero.
    """
    tareas: dict[int, list[TransicionTareaArchivada]] = defaultdict(list)
    for fila in historial:
        if (
            fila.tipo not in {"USER_TASK", "AUTOMATIC_TASK", "MANUAL_TASK"}
            or not fila.name.strip()
        ):
            continue
        tareas[fila.source_object_id].append(fila)
    muestras: list[tuple[str, float]] = []
    descartadas = 0
    for filas in tareas.values():
        if not any(f.state == "completed" for f in filas):
            continue
        fechas: list[tuple[str, datetime]] = []
        for fila in filas:
            fecha = fecha_bonita(fila.reached_state_date, zona)
            if fecha is None:
                break
            fechas.append((fila.state, fecha))
        else:
            inicios = [
                fecha
                for estado, fecha in fechas
                if estado not in {"completed", "aborted", "cancelled", "skipped"}
            ]
            finales = [fecha for estado, fecha in fechas if estado == "completed"]
            if inicios and len({f.name for f in filas}) == 1:
                segundos = (min(finales) - min(inicios)).total_seconds()
                if segundos >= 0:
                    muestras.append((filas[0].name, segundos))
                    continue
        descartadas += 1
    return muestras, descartadas


def obtener_tiempos(
    session: Session, filtros: FiltrosMetricas, cliente: ClienteBonita
) -> ReporteTiempos:
    """Consulta casos ligados a datos locales; tolera indisponibilidad parcial."""
    emergencias = session.scalars(emergencias_filtradas(filtros)).all()
    vinculadas = [e for e in emergencias if e.bonita_process_instance_id is not None]
    grupos: dict[tuple[str, str], list[float]] = defaultdict(list)
    consultados = con_muestras = descartadas = 0
    activos_consultados = 0
    activas: list[ActividadActual] = []
    ahora = datetime.now(UTC)
    zona = ZoneInfo(get_settings().bonita_timezone)
    inicio = monotonic()
    for emergencia in vinculadas:
        # Evita multiplicar el timeout de Bonita por todos los casos de un reporte.
        if monotonic() - inicio >= 20:
            break
        assert emergencia.bonita_process_instance_id is not None
        try:
            historial = cliente.obtener_historial_tareas(
                emergencia.bonita_process_instance_id
            )
        except (BonitaNoDisponibleError, BonitaCredencialesError):
            break
        except ErrorBonita:
            historial = []
        else:
            consultados += 1
        muestras, invalidas = duraciones_tareas(
            historial, ZoneInfo(get_settings().bonita_timezone)
        )
        descartadas += invalidas
        con_muestras += bool(muestras)
        for nombre, segundos in muestras:
            grupos[(nombre, emergencia.bonita_process_version or "Sin versión")].append(
                segundos
            )
        if monotonic() - inicio >= 20:
            continue
        try:
            tareas = cliente.obtener_tareas_activas(
                emergencia.bonita_process_instance_id
            )
        except (BonitaNoDisponibleError, BonitaCredencialesError):
            break
        except ErrorBonita:
            continue
        activos_consultados += 1
        activas.extend(actividades_actuales(emergencia, tareas, historial, zona, ahora))
    errores = len(vinculadas) - consultados
    sin_historial = len(emergencias) - len(vinculadas) + consultados - con_muestras
    disponibilidad = DisponibilidadBonita.DISPONIBLE
    if not grupos:
        disponibilidad = (
            DisponibilidadBonita.NO_DISPONIBLE
            if errores
            else DisponibilidadBonita.SIN_DATOS
        )
    elif errores or sin_historial or descartadas:
        disponibilidad = DisponibilidadBonita.PARCIAL
    return ReporteTiempos(
        actividad_por_etapa=resumir_actividad(activas),
        tareas_activas=sorted(
            activas,
            key=lambda a: (-(a.antiguedad_segundos or 0), a.emergencia_id, a.tarea_id),
        ),
        casos_activos_consultados=activos_consultados,
        casos_activos_con_error=len(vinculadas) - activos_consultados,
        filtros=filtros,
        disponibilidad=disponibilidad,
        casos_seleccionados=len(emergencias),
        casos_vinculados=len(vinculadas),
        casos_consultados=consultados,
        casos_con_muestras=con_muestras,
        casos_sin_historial_suficiente=sin_historial,
        casos_con_error=errores,
        muestras_descartadas=descartadas,
        etapas=[
            TiempoEtapa(
                etapa=nombre,
                version_proceso=version,
                promedio_segundos=sum(valores) / len(valores),
                muestras=len(valores),
            )
            for (nombre, version), valores in sorted(grupos.items())
        ],
    )
