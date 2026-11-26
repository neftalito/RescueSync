"""Comparaciones de búsqueda para las consultas de listados."""

from unicodedata import normalize

from sqlalchemy import String, cast, func
from sqlalchemy.sql import ColumnElement, SQLColumnExpression

_ACENTOS = "áéíóúü"
_VOCALES = "aeiouu"
_TRADUCCION = str.maketrans(_ACENTOS, _VOCALES)


def contiene_texto(
    campo: SQLColumnExpression[str | None], termino: str
) -> ColumnElement[bool]:
    """Compara una subcadena literal sin distinguir mayúsculas ni tildes."""

    texto = normalize("NFC", termino.lower()).translate(_TRADUCCION)
    campo_normalizado = func.translate(
        func.lower(func.normalize(campo)), _ACENTOS, _VOCALES
    )
    return campo_normalizado.contains(texto, autoescape=True)


def coincide_numero(
    campo: SQLColumnExpression[int], termino: str
) -> ColumnElement[bool]:
    """Compara el número completo y admite el prefijo visible `#`."""

    return cast(campo, String) == termino.removeprefix("#")
