"""Vincula el resultado de una consulta al operador y al futuro registro."""

from hashlib import sha256

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import get_settings
from app.db.models import GravedadEmergencia, Usuario

_VIGENCIA_SEGUNDOS = 600
_serializer = URLSafeTimedSerializer(
    get_settings().clave_firma_sesion,
    salt="rescuesync-prioridad-emergencia-v1",
    signer_kwargs={"digest_method": sha256},
)


def _contexto(
    usuario: Usuario, gravedad: GravedadEmergencia, zona: str
) -> dict[str, str | int | None]:
    return {
        "usuario_id": usuario.id,
        "version_sesion": usuario.version_sesion,
        "municipio_id": usuario.organizacion_id,
        "gravedad": gravedad.value,
        "zona": zona,
    }


def firmar_prioridad(
    usuario: Usuario, gravedad: GravedadEmergencia, zona: str, prioridad: int
) -> str:
    """Emite un comprobante que caduca tras diez minutos."""

    return _serializer.dumps(
        {**_contexto(usuario, gravedad, zona), "prioridad": prioridad}
    )


def leer_prioridad(
    comprobante: str | None, usuario: Usuario, gravedad: GravedadEmergencia, zona: str
) -> int | None:
    """Recupera la puntuación si la firma, vigencia y datos coinciden."""

    if not comprobante:
        return None
    try:
        datos = _serializer.loads(comprobante, max_age=_VIGENCIA_SEGUNDOS)
    except BadSignature:
        return None
    if not isinstance(datos, dict):
        return None
    prioridad = datos.pop("prioridad", None)
    if datos != _contexto(usuario, gravedad, zona):
        return None
    return prioridad if type(prioridad) is int and 1 <= prioridad <= 10 else None
