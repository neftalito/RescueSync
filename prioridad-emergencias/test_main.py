"""Pruebas del contrato HTTP y de la escala de prioridades."""

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.mark.parametrize(
    ("gravedad", "esperadas"),
    [
        ("BAJA", (1, 2, 3)),
        ("MEDIA", (3, 4, 5)),
        ("ALTA", (5, 6, 7)),
        ("CRITICA", (8, 9, 10)),
    ],
)
def test_calcula_prioridad_por_gravedad_y_zona(
    gravedad: str, esperadas: tuple[int, int, int]
) -> None:
    for zona, prioridad in zip(("NORTE", "CENTRO", "SUR"), esperadas, strict=True):
        respuesta = client.post(
            "/prioridades", json={"gravedad": gravedad, "zona": zona}
        )
        assert respuesta.status_code == 200
        assert respuesta.json() == {"prioridad": prioridad}


@pytest.mark.parametrize(
    "datos",
    [
        {},
        {"gravedad": "EXTREMA", "zona": "NORTE"},
        {"gravedad": "ALTA", "zona": "ESTE"},
    ],
)
def test_rechaza_datos_fuera_del_catalogo(datos: dict[str, str]) -> None:
    assert client.post("/prioridades", json=datos).status_code == 422


def test_health_esta_disponible() -> None:
    assert client.get("/health").status_code == 200
