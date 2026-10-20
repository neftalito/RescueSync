"""Comprueba que Bonita real conserva los estados usados para medir tiempos."""

import os
import time
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.core.config import get_settings
from app.integrations.bonita.cliente import ClienteBonita, ConfiguracionBonita
from app.integrations.bonita.contratos import (
    TAREA_GENERAR_LOTES,
    USUARIO_ACTOR_COORDINADOR,
    ContratoInicioProceso,
)
from app.services.metricas_bonita import duraciones_tareas

pytestmark = [
    pytest.mark.bonita_e2e,
    pytest.mark.skipif(
        os.getenv("RUN_BONITA_E2E") != "1",
        reason="Requiere RUN_BONITA_E2E=1 y Bonita levantado.",
    ),
]


def test_historial_real_mide_tarea_completada_y_limpia_caso_temporal() -> None:
    """Crea solo un caso temporal del motor; no altera emergencias locales."""
    settings = get_settings()
    with (
        ClienteBonita(ConfiguracionBonita.desde_settings(settings)) as cliente,
        httpx.Client(base_url=settings.bonita_base_url, timeout=10) as observador,
    ):
        login = observador.post(
            "/loginservice",
            data={
                "username": settings.bonita_username,
                "password": settings.bonita_password.get_secret_value(),
                "redirect": "false",
            },
        )
        assert login.status_code in {200, 204}
        observador.headers["X-Bonita-API-Token"] = login.cookies["X-Bonita-API-Token"]
        proceso = cliente.obtener_proceso_habilitado()
        caso = cliente.iniciar_instancia(
            proceso.id,
            ContratoInicioProceso(
                idEmergencia=time.time_ns() // 1000,
                gravedad="MEDIA",
                zona="Prueba temporal de indicadores",
                descripcion="Caso temporal para validar historial de Bonita",
                municipioId=999999,
            ),
        ).case_id
        try:
            tarea = None
            for _ in range(40):
                tarea = cliente.buscar_tarea_lista(caso, TAREA_GENERAR_LOTES)
                if tarea is not None:
                    break
                time.sleep(0.25)
            assert tarea is not None
            activas = cliente.obtener_tareas_activas(caso)
            assert any(t.id == tarea.id and t.root_case_id == caso for t in activas)
            cliente.ejecutar_tarea(tarea.id, USUARIO_ACTOR_COORDINADOR)
            for _ in range(40):
                historial = cliente.obtener_historial_tareas(caso)
                muestras, _ = duraciones_tareas(
                    historial, ZoneInfo(settings.bonita_timezone)
                )
                if any(nombre == TAREA_GENERAR_LOTES for nombre, _ in muestras):
                    break
                time.sleep(0.25)
            assert all(fila.root_case_id == caso for fila in historial)
            assert any(
                nombre == TAREA_GENERAR_LOTES and segundos >= 0
                for nombre, segundos in muestras
            )
        finally:
            respuesta = observador.delete(f"/API/bpm/case/{caso}")
            assert respuesta.status_code in {200, 204}
