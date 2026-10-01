import smtplib
import ssl
from email.message import EmailMessage
from types import TracebackType
from typing import Self

import pytest

from app.core.config import Settings
from app.integrations.email.cliente import (
    ClienteSMTP,
    ConfiguracionSMTP,
    EmailNoDisponibleError,
)


class ServidorSMTPPrueba:
    """Registra la conversación SMTP para verificar el adaptador."""

    def __init__(self) -> None:
        self.mensaje: EmailMessage | None = None
        self.login_recibido: tuple[str, str] | None = None
        self.starttls_recibido = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def starttls(self, *, context: ssl.SSLContext) -> tuple[int, bytes]:
        self.starttls_recibido = isinstance(context, ssl.SSLContext)
        return 220, b"ready"

    def login(self, usuario: str, password: str) -> tuple[int, bytes]:
        self.login_recibido = (usuario, password)
        return 235, b"authenticated"

    def send_message(self, mensaje: EmailMessage) -> dict[str, tuple[int, bytes]]:
        self.mensaje = mensaje
        return {}


def test_envia_credenciales_con_starttls_y_autenticacion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    servidor = ServidorSMTPPrueba()

    def crear_servidor(
        *,
        host: str,
        port: int,
        timeout: float,
    ) -> ServidorSMTPPrueba:
        assert host == "sandbox.smtp.mailtrap.io"
        assert port == 2525
        assert timeout == 7
        return servidor

    monkeypatch.setattr(smtplib, "SMTP", crear_servidor)
    settings = Settings(
        _env_file=None,
        smtp_host="sandbox.smtp.mailtrap.io",
        smtp_port=2525,
        smtp_username="sandbox-user",
        smtp_password="sandbox-password",
        smtp_starttls=True,
        smtp_timeout_seconds=7,
        frontend_public_url="https://rescuesync.example",
    )
    cliente = ClienteSMTP(ConfiguracionSMTP.desde_settings(settings))

    cliente.enviar_alta_usuario("persona@example.org", "clave-temporal")

    assert servidor.starttls_recibido is True
    assert servidor.login_recibido == ("sandbox-user", "sandbox-password")
    assert servidor.mensaje is not None
    assert servidor.mensaje["To"] == "persona@example.org"
    assert servidor.mensaje["Subject"] == "Tu cuenta de RescueSync"
    contenido = servidor.mensaje.get_content()
    assert "persona@example.org" in contenido
    assert "clave-temporal" in contenido
    assert "https://rescuesync.example" in contenido


def test_traduce_fallo_de_conexion_sin_exponer_detalles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def rechazar_conexion(*, host: str, port: int, timeout: float) -> None:
        raise OSError(f"falló {host}:{port} tras {timeout}")

    monkeypatch.setattr(smtplib, "SMTP", rechazar_conexion)
    cliente = ClienteSMTP(ConfiguracionSMTP.desde_settings(Settings(_env_file=None)))

    with pytest.raises(
        EmailNoDisponibleError,
        match="El servidor de correo no pudo entregar las credenciales temporales",
    ):
        cliente.enviar_alta_usuario("persona@example.org", "clave-secreta")
