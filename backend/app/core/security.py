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


def crear_valor_sesion(usuario_id: int) -> str:
    """Firma el único identificador almacenado en la cookie de sesión."""

    return _session_serializer.dumps(str(usuario_id))


def leer_usuario_id_sesion(valor_sesion: str | None) -> int | None:
    """Valida una cookie firmada y devuelve el usuario mientras siga vigente."""

    if valor_sesion is None:
        return None

    try:
        valor = _session_serializer.loads(
            valor_sesion,
            max_age=_settings.session_max_age_seconds,
        )
    except (BadSignature, SignatureExpired):
        return None

    if not isinstance(valor, str) or not valor.isdecimal():
        return None

    usuario_id = int(valor)
    return usuario_id if usuario_id > 0 else None


def crear_token_csrf(usuario_id: int) -> str:
    """Emite un token CSRF firmado y ligado al usuario autenticado."""

    return _csrf_serializer.dumps(str(usuario_id))


def verificar_token_csrf(token: str | None, usuario_id: int) -> bool:
    """Comprueba la firma, vigencia y pertenencia de un token CSRF."""

    if token is None:
        return False

    try:
        valor = _csrf_serializer.loads(
            token,
            max_age=_settings.session_max_age_seconds,
        )
    except (BadSignature, SignatureExpired):
        return False

    return isinstance(valor, str) and valor == str(usuario_id)
