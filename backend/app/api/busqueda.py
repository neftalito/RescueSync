"""Parámetro de texto compartido por los listados con búsqueda."""

from typing import Annotated

from fastapi import Depends, Query


def obtener_busqueda(
    q: Annotated[str, Query(max_length=120, description="Texto a buscar.")] = "",
) -> str:
    return q.strip()


BusquedaDep = Annotated[str, Depends(obtener_busqueda)]
