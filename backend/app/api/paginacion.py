"""Valida los parámetros compartidos de los listados HTTP."""

from typing import Annotated

from fastapi import Depends, Query

from app.schemas.paginacion import Paginacion


def obtener_paginacion(
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Paginacion:
    """Permite páginas de hasta 100 filas; omitir limit conserva el contrato previo."""
    return Paginacion(limit=limit, offset=offset)


PaginacionDep = Annotated[Paginacion, Depends(obtener_paginacion)]
