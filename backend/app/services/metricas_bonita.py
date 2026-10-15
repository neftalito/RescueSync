"""Calcula duraciones observadas sin inferir cierres desde timestamps locales."""

from collections import defaultdict
from datetime import UTC, datetime
from time import monotonic
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.bonita.cliente import (
    BonitaCredencialesError,
    BonitaNoDisponibleError,
    ClienteBonita,
    ErrorBonita,
)
from app.integrations.bonita.contratos import TransicionTareaArchivada
from app.schemas.metricas import (
    DisponibilidadBonita,
    FiltrosMetricas,
    ReporteTiempos,
    TiempoEtapa,
)
from app.services.metricas import emergencias_filtradas


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
        try:
            fechas: list[tuple[str, datetime]] = []
            for fila in filas:
                fecha = datetime.fromisoformat(fila.reached_state_date)
                if fecha.tzinfo is None:
                    fecha = fecha.replace(tzinfo=zona)
                fechas.append((fila.state, fecha.astimezone(UTC)))
            inicios = [
                fecha
                for estado, fecha in fechas
                if estado not in {"completed", "aborted", "cancelled", "skipped"}
            ]
            finales = [fecha for estado, fecha in fechas if estado == "completed"]
            if not inicios or len({f.name for f in filas}) != 1:
                descartadas += 1
                continue
            segundos = (min(finales) - min(inicios)).total_seconds()
            if segundos < 0:
                descartadas += 1
                continue
            muestras.append((filas[0].name, segundos))
        except ValueError:
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
            continue
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
