"""Verifica el proceso RescueSync con Bonita, FastAPI y PostgreSQL reales (Entrega 2).

Se ejecuta dentro del contenedor `backend`: Bonita invoca los callbacks en
`http://backend:8000` con el token de `BONITA_CALLBACK_TOKEN`.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    EstadoConvocatoria,
    EstadoOferta,
    EstadoSincronizacionBonita,
    GravedadEmergencia,
    Lote,
    Oferta,
    OfertaItem,
    OfertaVersion,
    Organizacion,
    RolUsuario,
    TipoAporte,
    TipoOrganizacion,
    Usuario,
)
from app.db.session import SessionLocal
from app.integrations.bonita.cliente import (
    BonitaOperacionRechazadaError,
    ClienteBonita,
    ConfiguracionBonita,
)
from app.integrations.bonita.contratos import (
    TAREA_GENERAR_LOTES,
    USUARIO_ACTOR_COORDINADOR,
    ContratoInicioProceso,
)

pytestmark = [
    pytest.mark.bonita_e2e,
    pytest.mark.skipif(
        os.getenv("RUN_BONITA_E2E") != "1",
        reason="Requiere RUN_BONITA_E2E=1 y Bonita levantado.",
    ),
]

TIMEOUT_SEGUNDOS = float(os.getenv("BONITA_E2E_TIMEOUT_SECONDS", "20"))
VENTANA_MAXIMA_PARA_ESPERAR_MS = 60_000
ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


@dataclass
class DatosLocales:
    """Filas creadas por la prueba, en orden inverso de borrado."""

    session: Session
    filas: list[object]
    emergencia: Emergencia
    convocatoria: Convocatoria


@pytest.fixture
def cliente() -> Iterator[ClienteBonita]:
    with ClienteBonita(ConfiguracionBonita.desde_settings(get_settings())) as cliente:
        yield cliente


@pytest.fixture
def observador() -> Iterator[httpx.Client]:
    """Sesión independiente para inspeccionar el caso sin usar el código probado."""

    settings = get_settings()
    with httpx.Client(
        base_url=settings.bonita_base_url.rstrip("/"),
        timeout=TIMEOUT_SEGUNDOS,
    ) as client:
        response = client.post(
            "/loginservice",
            data={
                "username": settings.bonita_username,
                "password": settings.bonita_password.get_secret_value(),
                "redirect": "false",
            },
        )
        assert response.status_code in {200, 204}
        client.headers["X-Bonita-API-Token"] = response.cookies["X-Bonita-API-Token"]
        yield client


@pytest.fixture
def datos() -> Iterator[DatosLocales]:
    """Crea una emergencia con una convocatoria abierta y una oferta que la cubre."""

    sufijo = f"E2E {time.time_ns()}"
    ahora = datetime.now(UTC)
    with SessionLocal() as session:
        filas: list[object] = []

        def agregar[T](fila: T) -> T:
            session.add(fila)
            session.flush()
            filas.append(fila)
            return fila

        municipio = agregar(
            Organizacion(tipo=TipoOrganizacion.MUNICIPIO, nombre=f"Municipio {sufijo}")
        )
        ong = agregar(Organizacion(tipo=TipoOrganizacion.ONG, nombre=f"ONG {sufijo}"))
        operador = agregar(
            Usuario(
                organizacion_id=municipio.id,
                email=f"op-{time.time_ns()}@e2e.org",
                password_hash=ARGON2_HASH,
                rol=RolUsuario.OPERADOR_MUNICIPAL,
            )
        )
        representante = agregar(
            Usuario(
                organizacion_id=ong.id,
                email=f"ong-{time.time_ns()}@e2e.org",
                password_hash=ARGON2_HASH,
                rol=RolUsuario.REPRESENTANTE_ONG,
            )
        )
        emergencia = agregar(
            Emergencia(
                municipio_id=municipio.id,
                creada_por_usuario_id=operador.id,
                gravedad=GravedadEmergencia.CRITICA,
                zona=f"Zona {sufijo}",
                descripcion="Emergencia temporal de la prueba E2E",
            )
        )
        lote = agregar(
            Lote(
                emergencia_id=emergencia.id,
                creado_por_usuario_id=operador.id,
                tipo_necesidad="Agua",
                cantidad_requerida=Decimal(100),
                unidad="litros",
            )
        )
        convocatoria = agregar(
            Convocatoria(
                emergencia_id=emergencia.id,
                numero=1,
                publicada_en=ahora,
                cierra_en=ahora + timedelta(days=1),
            )
        )
        agregar(
            ConvocatoriaLote(
                convocatoria_id=convocatoria.id,
                lote_id=lote.id,
                cantidad_publicada=Decimal(100),
                unidad_publicada="litros",
            )
        )
        oferta = agregar(
            Oferta(
                convocatoria_id=convocatoria.id,
                ong_creadora_id=ong.id,
                creada_por_usuario_id=representante.id,
                estado=EstadoOferta.PRESENTADA,
            )
        )
        version = agregar(
            OfertaVersion(
                oferta_id=oferta.id,
                creada_por_usuario_id=representante.id,
                numero=1,
                presentada_en=ahora,
            )
        )
        agregar(
            OfertaItem(
                oferta_version_id=version.id,
                convocatoria_id=convocatoria.id,
                lote_id=lote.id,
                tipo=TipoAporte.RECURSO,
                descripcion="Agua potable",
                cantidad_ofrecida=Decimal(100),
                unidad="litros",
            )
        )
        session.commit()

        yield DatosLocales(session, filas, emergencia, convocatoria)

        session.rollback()
        for fila in reversed(filas):
            session.delete(fila)
            session.flush()
        session.commit()


def _esperar[T](descripcion: str, obtener: Callable[[], T | None]) -> T:
    deadline = time.monotonic() + TIMEOUT_SEGUNDOS
    while time.monotonic() < deadline:
        if (resultado := obtener()) is not None:
            return resultado
        time.sleep(0.25)
    pytest.fail(f"Se agotó la espera: {descripcion}.")


def _json(response: httpx.Response) -> object:
    assert response.status_code == 200, response.text[:500]
    return response.json()


def _nodos_fallidos(observador: httpx.Client, case_id: int) -> list[str]:
    nodos = _json(
        observador.get(
            "/API/bpm/flowNode",
            params=[("p", 0), ("c", 200), ("f", "state=failed")],
        )
    )
    assert isinstance(nodos, list)
    return [
        str(nodo.get("name"))
        for nodo in nodos
        if isinstance(nodo, dict) and str(nodo.get("rootCaseId")) == str(case_id)
    ]


def _sin_fallos(observador: httpx.Client, case_id: int) -> None:
    if fallidos := _nodos_fallidos(observador, case_id):
        pytest.fail(
            f"Actividades fallidas en el caso {case_id}: {fallidos}. Revisar los "
            "logs de bonita y backend (callbacks de FastAPI)."
        )


def _timer_de_ofertas(observador: httpx.Client, case_id: int) -> int | None:
    _sin_fallos(observador, case_id)
    timers = _json(
        observador.get(
            "/API/bpm/timerEventTrigger",
            params=[("p", 0), ("c", 20), ("caseId", case_id)],
        )
    )
    assert isinstance(timers, list)
    for timer in timers:
        if isinstance(timer, dict) and timer.get("eventInstanceName") == (
            "EsperarOfertas"
        ):
            fecha = timer.get("executionDate")
            assert isinstance(fecha, int)
            return fecha
    return None


def _tarea_lista(
    cliente: ClienteBonita,
    observador: httpx.Client,
    case_id: int,
    nombre: str,
) -> object | None:
    _sin_fallos(observador, case_id)
    return cliente.buscar_tarea_lista(case_id, nombre)


def _ventana_instalada_ms(observador: httpx.Client, proceso_id: int) -> int:
    parametros = _json(
        observador.get(
            "/API/bpm/processParameter",
            params=[("p", 0), ("c", 50), ("f", f"process_id={proceso_id}")],
        )
    )
    assert isinstance(parametros, list)
    valores = {p.get("name"): p.get("value") for p in parametros if isinstance(p, dict)}
    return int(str(valores["ventanaOfertasMs"]))


def test_flujo_bonita_fastapi_hasta_consolidar_ofertas(
    cliente: ClienteBonita,
    observador: httpx.Client,
    datos: DatosLocales,
) -> None:
    """Recorre instanciación, publicación, callbacks, timer y consolidación."""

    session, emergencia = datos.session, datos.emergencia
    proceso = cliente.obtener_proceso_habilitado()
    contrato = ContratoInicioProceso(
        idEmergencia=emergencia.id,
        gravedad=emergencia.gravedad,
        zona=emergencia.zona,
        descripcion=emergencia.descripcion,
        municipioId=emergencia.municipio_id,
    )

    # Se omite la validación local para confirmar que el motor rechaza lo mismo.
    invalido = contrato.model_construct(**(contrato.__dict__ | {"zona": "   "}))
    with pytest.raises(BonitaOperacionRechazadaError, match="HTTP 400"):
        cliente.iniciar_instancia(proceso.id, invalido)

    case_id = cliente.iniciar_instancia(proceso.id, contrato).case_id
    try:
        emergencia.bonita_process_instance_id = case_id
        emergencia.bonita_process_definition_id = proceso.id
        emergencia.bonita_process_version = proceso.version
        emergencia.bonita_sync = EstadoSincronizacionBonita.VINCULADA
        session.commit()

        casos = cliente.buscar_casos_por_emergencia(proceso.id, emergencia.id)
        assert [caso.id for caso in casos] == [case_id]
        for nombre, esperado in contrato.a_payload().items():
            variable = _json(
                observador.get(f"/API/bpm/caseVariable/{case_id}/{nombre}")
            )
            assert isinstance(variable, dict)
            assert variable.get("value") == str(esperado)

        tarea = _esperar(
            f"tarea '{TAREA_GENERAR_LOTES}'",
            lambda: cliente.buscar_tarea_lista(case_id, TAREA_GENERAR_LOTES),
        )
        cliente.ejecutar_tarea(tarea.id, USUARIO_ACTOR_COORDINADOR)

        cierre_bonita_ms = _esperar(
            "timer 'EsperarOfertas'",
            lambda: _timer_de_ofertas(observador, case_id),
        )
        session.refresh(datos.convocatoria)
        cierre_local_ms = int(datos.convocatoria.cierra_en.timestamp() * 1_000)
        assert abs(cierre_local_ms - cierre_bonita_ms) < 1_000, (
            "notificar-apertura no alineó cierra_en con el timer de Bonita."
        )

        ventana_ms = _ventana_instalada_ms(observador, proceso.id)
        if ventana_ms > VENTANA_MAXIMA_PARA_ESPERAR_MS:
            pytest.skip(
                "Verificado hasta notificar-apertura. Tramo posterior al timer "
                f"omitido: ventanaOfertasMs={ventana_ms}; instalar el proceso con "
                "BONITA_OFFER_WINDOW_MS<=60000 para cubrirlo."
            )

        restante_s = max(0.0, cierre_bonita_ms / 1_000 - time.time())
        time.sleep(restante_s)
        seleccion = _esperar(
            "tarea 'Seleccionar ofertas validadas'",
            lambda: _tarea_lista(
                cliente, observador, case_id, "Seleccionar ofertas validadas"
            ),
        )
        assert seleccion is not None
        session.refresh(datos.convocatoria)
        assert datos.convocatoria.estado is EstadoConvocatoria.CERRADA
        assert datos.convocatoria.cerrada_en is not None
        cubiertos = _json(
            observador.get(f"/API/bpm/caseVariable/{case_id}/lotesCubiertos")
        )
        assert isinstance(cubiertos, dict) and cubiertos.get("value") == "true"
    finally:
        response = observador.put(
            f"/API/bpm/case/{case_id}", json={"state": "cancelled"}
        )
        assert response.status_code == 200, f"No se pudo cancelar el caso {case_id}."
