from dataclasses import dataclass
from hashlib import sha256

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.core.config import get_settings

_settings = get_settings()
_password_hash = PasswordHash.recommended()
_dummy_password_hash = _password_hash.hash("credencial-inexistente-rescuesync")
_signer_kwargs = {"digest_method": sha256}
_session_serializer = URLSafeTimedSerializer(
    _settings.clave_firma_sesion,
    salt="rescuesync-local-session-v1",
    signer_kwargs=_signer_kwargs,
)
_csrf_serializer = URLSafeTimedSerializer(
    _settings.clave_firma_sesion,
    salt="rescuesync-csrf-v1",
    signer_kwargs=_signer_kwargs,
)


@dataclass(frozen=True)
class CredencialSesion:
    """Identifica una sesión y la versión de credenciales que la emitió."""

    usuario_id: int
    version_sesion: int


def generar_password_hash(password: str) -> str:
    """Genera un hash Argon2 apto para persistir una contraseña local."""

    return _password_hash.hash(password)


def verificar_password(password: str, password_hash: str | None) -> bool:
    """Verifica una contraseña y mantiene un costo similar para usuarios inexistentes."""

    hash_a_verificar = password_hash or _dummy_password_hash
    try:
        return _password_hash.verify(password, hash_a_verificar)
    except UnknownHashError:
        return False


def crear_valor_sesion(usuario_id: int, version_sesion: int = 1) -> str:
    """Firma el identificador y la versión vigentes de una sesión."""

    return _session_serializer.dumps(
        {"usuario_id": usuario_id, "version": version_sesion}
    )


def leer_credencial_sesion(valor_sesion: str | None) -> CredencialSesion | None:
    """Valida una cookie firmada y devuelve su identidad y versión."""

    if valor_sesion is None:
        return None

    try:
        valor = _session_serializer.loads(
            valor_sesion,
            max_age=_settings.session_max_age_seconds,
        )
    except (BadSignature, SignatureExpired):
        return None

    if not isinstance(valor, dict):
        return None

    usuario_id = valor.get("usuario_id")
    version_sesion = valor.get("version")
    if (
        not isinstance(usuario_id, int)
        or isinstance(usuario_id, bool)
        or usuario_id <= 0
        or not isinstance(version_sesion, int)
        or isinstance(version_sesion, bool)
        or version_sesion <= 0
    ):
        return None
    return CredencialSesion(usuario_id=usuario_id, version_sesion=version_sesion)


def crear_token_csrf(usuario_id: int, version_sesion: int = 1) -> str:
    """Emite un token CSRF ligado al usuario y a su versión de sesión."""

    return _csrf_serializer.dumps({"usuario_id": usuario_id, "version": version_sesion})


def verificar_token_csrf(
    token: str | None,
    usuario_id: int,
    version_sesion: int,
) -> bool:
    """Comprueba firma, vigencia, pertenencia y versión de un token CSRF."""

    if token is None:
        return False

    try:
        valor = _csrf_serializer.loads(
            token,
            max_age=_settings.session_max_age_seconds,
        )
    except (BadSignature, SignatureExpired):
        return False

    return valor == {"usuario_id": usuario_id, "version": version_sesion}
