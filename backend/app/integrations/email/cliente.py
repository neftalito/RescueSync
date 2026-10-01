"""Cliente SMTP para entregar correos sin exponer credenciales en las rutas."""

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from pydantic import SecretStr

from app.core.config import Settings


class EmailNoDisponibleError(RuntimeError):
    """Indica que el servidor SMTP no pudo aceptar el correo."""


@dataclass(frozen=True)
class ConfiguracionSMTP:
    """Agrupa los parámetros necesarios para conectarse al servidor SMTP."""

    host: str
    puerto: int
    remitente: str
    usuario: str | None
    password: SecretStr | None
    usar_starttls: bool
    timeout_segundos: float
    url_aplicacion: str

    @classmethod
    def desde_settings(cls, settings: Settings) -> "ConfiguracionSMTP":
        """Construye la configuración SMTP desde las variables de entorno."""

        return cls(
            host=settings.smtp_host,
            puerto=settings.smtp_port,
            remitente=str(settings.smtp_sender_email),
            usuario=settings.smtp_username,
            password=settings.smtp_password,
            usar_starttls=settings.smtp_starttls,
            timeout_segundos=settings.smtp_timeout_seconds,
            url_aplicacion=str(settings.frontend_public_url).rstrip("/"),
        )


class ClienteSMTP:
    """Envía los correos transaccionales mediante un servidor SMTP configurable."""

    def __init__(self, configuracion: ConfiguracionSMTP) -> None:
        self.configuracion = configuracion

    def enviar_alta_usuario(self, destinatario: str, password_temporal: str) -> None:
        """Envía al usuario las credenciales temporales de su nueva cuenta.

        Raises:
            EmailNoDisponibleError: si SMTP no acepta o no puede recibir el mensaje.
        """

        mensaje = self._construir_alta_usuario(destinatario, password_temporal)
        try:
            with smtplib.SMTP(
                host=self.configuracion.host,
                port=self.configuracion.puerto,
                timeout=self.configuracion.timeout_segundos,
            ) as smtp:
                if self.configuracion.usar_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if (
                    self.configuracion.usuario is not None
                    and self.configuracion.password is not None
                ):
                    smtp.login(
                        self.configuracion.usuario,
                        self.configuracion.password.get_secret_value(),
                    )
                smtp.send_message(mensaje)
        except (OSError, smtplib.SMTPException) as error:
            raise EmailNoDisponibleError(
                "El servidor de correo no pudo entregar las credenciales temporales."
            ) from error

    def _construir_alta_usuario(
        self,
        destinatario: str,
        password_temporal: str,
    ) -> EmailMessage:
        mensaje = EmailMessage()
        mensaje["Subject"] = "Tu cuenta de RescueSync"
        mensaje["From"] = self.configuracion.remitente
        mensaje["To"] = destinatario
        mensaje.set_content(
            "\n".join(
                (
                    "Se creó una cuenta de RescueSync para vos.",
                    "",
                    f"Usuario: {destinatario}",
                    f"Contraseña temporal: {password_temporal}",
                    f"Ingresá en: {self.configuracion.url_aplicacion}",
                    "",
                    "Por seguridad, deberás cambiar la contraseña en tu primer acceso.",
                    "Si no esperabas este correo, contactá a la administración.",
                )
            )
        )
        return mensaje
