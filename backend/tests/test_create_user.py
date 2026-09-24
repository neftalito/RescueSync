import pytest

from app.scripts.create_user import _leer_password


def test_creacion_manual_acepta_password_de_ocho_caracteres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respuestas = iter(("12345678", "12345678"))

    def responder(_: str) -> str:
        return next(respuestas)

    monkeypatch.setattr("app.scripts.create_user.getpass.getpass", responder)

    assert _leer_password() == "12345678"


def test_creacion_manual_rechaza_password_de_siete_caracteres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respuestas = iter(("1234567", "1234567"))

    def responder(_: str) -> str:
        return next(respuestas)

    monkeypatch.setattr("app.scripts.create_user.getpass.getpass", responder)

    with pytest.raises(ValueError, match="entre 8 y 128 caracteres"):
        _leer_password()
