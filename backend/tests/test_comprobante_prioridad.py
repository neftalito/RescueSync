from itsdangerous import TimestampSigner
from pytest import MonkeyPatch

from app.db.models import GravedadEmergencia, Usuario
from app.services.prioridad_emergencias import firmar_prioridad, leer_prioridad


def test_comprobante_caduca_y_queda_ligado_al_contexto(
    monkeypatch: MonkeyPatch,
) -> None:
    tiempo = 1_800_000_000
    monkeypatch.setattr(TimestampSigner, "get_timestamp", lambda _signer: tiempo)
    usuario = Usuario(id=1, organizacion_id=2, version_sesion=3)
    gravedad = GravedadEmergencia.ALTA
    comprobante = firmar_prioridad(usuario, gravedad, "CENTRO", 6)
    assert leer_prioridad(comprobante, usuario, gravedad, "CENTRO") == 6

    otro = Usuario(id=9, organizacion_id=2, version_sesion=3)
    assert leer_prioridad(comprobante, otro, gravedad, "CENTRO") is None
    usuario.organizacion_id = 4
    assert leer_prioridad(comprobante, usuario, gravedad, "CENTRO") is None
    usuario.organizacion_id = 2
    usuario.version_sesion = 4
    assert leer_prioridad(comprobante, usuario, gravedad, "CENTRO") is None
    usuario.version_sesion = 3

    tiempo += 601
    assert leer_prioridad(comprobante, usuario, gravedad, "CENTRO") is None
