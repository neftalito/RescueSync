"""Semántica de tiempos del motor, independiente de la base local."""

from zoneinfo import ZoneInfo

from app.integrations.bonita.contratos import TransicionTareaArchivada
from app.services.metricas_bonita import duraciones_tareas


def fila(identidad: int, estado: str, fecha: str) -> TransicionTareaArchivada:
    return TransicionTareaArchivada(
        type="USER_TASK",
        sourceObjectId=identidad,
        rootCaseId=99,
        name="Generar lotes",
        state=estado,
        reached_state_date=fecha,
    )


def test_repeticiones_y_transiciones_duplicadas_no_inflan_promedios() -> None:
    historial = [
        fila(1, "ready", "2026-10-15 09:00:00"),
        fila(1, "executing", "2026-10-15 09:30:00"),
        fila(1, "completed", "2026-10-15 10:00:00"),
        fila(1, "completed", "2026-10-15 10:00:00"),
        fila(2, "ready", "2026-10-15 11:00:00"),
        fila(2, "completed", "2026-10-15 13:00:00"),
    ]
    muestras, descartadas = duraciones_tareas(historial, ZoneInfo("UTC"))
    assert muestras == [("Generar lotes", 3600), ("Generar lotes", 7200)]
    assert descartadas == 0


def test_descarta_muestras_invalidas_e_ignora_tareas_sin_completar() -> None:
    historial = [
        fila(1, "completed", "2026-10-15 10:00:00"),
        fila(2, "ready", "inválida"),
        fila(2, "completed", "2026-10-15 10:00:00"),
        fila(3, "ready", "2026-10-15 11:00:00"),
        fila(3, "completed", "2026-10-15 10:00:00"),
        fila(4, "ready", "2026-10-15 09:00:00"),
        fila(4, "cancelled", "2026-10-15 10:00:00"),
        fila(5, "ready", "2026-10-15 10:00:00"),
    ]
    assert duraciones_tareas(historial, ZoneInfo("UTC")) == ([], 3)


def test_normaliza_offsets_y_zona_del_runtime() -> None:
    historial = [
        fila(1, "ready", "2026-10-15T09:00:00-03:00"),
        fila(1, "completed", "2026-10-15T13:00:00Z"),
        fila(2, "ready", "2026-10-15 09:00:00"),
        fila(2, "completed", "2026-10-15T13:00:00Z"),
    ]
    muestras, descartadas = duraciones_tareas(
        historial, ZoneInfo("America/Argentina/Buenos_Aires")
    )
    assert muestras == [("Generar lotes", 3600), ("Generar lotes", 3600)]
    assert descartadas == 0
