"""Ventanas de consulta compatibles con los consumidores de listas completas."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Paginacion:
    """Limita una consulta sin cambiar su orden ni sus filtros de autorización."""

    limit: int | None = None
    offset: int = 0


SIN_PAGINACION = Paginacion()
