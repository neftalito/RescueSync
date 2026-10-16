"""Revisiones serializadas entre conexiones PostgreSQL independientes."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session
from test_ofertas import ARGON2_HASH

from app.db.models import Convocatoria, Emergencia, Organizacion, Usuario
from app.db.models.ejecucion import EvaluacionLocal
from app.db.session import engine
from app.schemas.ejecucion import PreparacionResponse, PreparacionValidacion
from app.services.evaluaciones import preparar


@pytest.fixture
def ronda_confirmada() -> Iterator[tuple[int, int, int]]:
    sufijo = uuid4().hex
    ahora = datetime.now(UTC)
    with Session(engine) as session:
        municipio = Organizacion(
            tipo="MUNICIPIO", nombre=f"Municipio concurrencia {sufijo}"
        )
        session.add(municipio)
        session.flush()
        usuario = Usuario(
            organizacion_id=municipio.id,
            rol="OPERADOR_MUNICIPAL",
            email=f"{sufijo}@test.org",
            password_hash=ARGON2_HASH,
        )
        session.add(usuario)
        session.flush()
        caso = int(sufijo[:12], 16)
        e = Emergencia(
            municipio_id=municipio.id,
            creada_por_usuario_id=usuario.id,
            gravedad="ALTA",
            zona="Prueba",
            descripcion="Evaluaciones concurrentes",
            estado="EN_EVALUACION",
            bonita_process_instance_id=caso,
        )
        session.add(e)
        session.flush()
        c = Convocatoria(
            emergencia_id=e.id,
            numero=1,
            estado="CERRADA",
            publicada_en=ahora - timedelta(hours=2),
            cierra_en=ahora - timedelta(hours=1),
            cerrada_en=ahora,
            sistema_origen_ref="instalacion-prueba",
            gravedad_publicada="ALTA",
        )
        session.add(c)
        session.commit()
        emergencia_id, convocatoria_id, usuario_id, municipio_id = (
            e.id,
            c.id,
            usuario.id,
            municipio.id,
        )
    try:
        yield emergencia_id, convocatoria_id, caso
    finally:
        with Session(engine) as session:
            session.execute(
                delete(EvaluacionLocal).where(
                    EvaluacionLocal.emergencia_id == emergencia_id
                )
            )
            session.execute(
                delete(Convocatoria).where(Convocatoria.id == convocatoria_id)
            )
            session.execute(delete(Emergencia).where(Emergencia.id == emergencia_id))
            session.execute(delete(Usuario).where(Usuario.id == usuario_id))
            session.execute(delete(Organizacion).where(Organizacion.id == municipio_id))
            session.commit()


@pytest.mark.parametrize("misma_identidad", [True, False])
def test_preparaciones_concurrentes_asignan_revision_una_sola_vez(
    ronda_confirmada: tuple[int, int, int], misma_identidad: bool
) -> None:
    emergencia_id, convocatoria_id, caso = ronda_confirmada
    identidad = uuid4()
    barrera = Barrier(2)

    def ejecutar(indice: int) -> PreparacionResponse:
        with Session(engine) as session:
            barrera.wait(timeout=10)
            return preparar(
                session,
                emergencia_id,
                caso,
                PreparacionValidacion(
                    validacion_id=identidad
                    if misma_identidad or indice == 0
                    else uuid4(),
                    convocatoria_id=convocatoria_id,
                    intento_convocatoria=1,
                ),
            )

    with ThreadPoolExecutor(max_workers=2) as workers:
        resultados = list(workers.map(ejecutar, [0, 1]))
    assert sorted(r.revision for r in resultados) == (
        [1, 1] if misma_identidad else [1, 2]
    )
    if misma_identidad:
        assert resultados[0] == resultados[1]
