import argparse
import getpass
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.roles import TIPO_ORGANIZACION_POR_ROL
from app.core.security import generar_password_hash
from app.db.models import Organizacion, RolUsuario, Usuario
from app.db.session import SessionLocal

_email_adapter = TypeAdapter(EmailStr)


def _rol(valor: str) -> RolUsuario:
    try:
        return RolUsuario(valor)
    except ValueError as error:
        opciones = ", ".join(rol.value for rol in RolUsuario)
        raise argparse.ArgumentTypeError(
            f"rol inválido; opciones: {opciones}"
        ) from error


def _crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Crea un usuario local sin exponer su contraseña en la terminal.",
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--rol", required=True, type=_rol)
    parser.add_argument(
        "--organizacion",
        help="Nombre de la organización; se crea con el tipo exigido por el rol.",
    )
    return parser


def _leer_password() -> str:
    password = getpass.getpass("Contraseña (8 a 128 caracteres): ")
    confirmacion = getpass.getpass("Repetir contraseña: ")
    if password != confirmacion:
        raise ValueError("las contraseñas no coinciden")
    if not 8 <= len(password) <= 128:
        raise ValueError("la contraseña debe tener entre 8 y 128 caracteres")
    return password


def _obtener_organizacion(
    session: Session,
    rol: RolUsuario,
    nombre: str | None,
) -> Organizacion | None:
    tipo = TIPO_ORGANIZACION_POR_ROL.get(rol)
    if tipo is None:
        if nombre is not None:
            raise ValueError("el rol seleccionado no admite una organización")
        return None
    if nombre is None or not nombre.strip():
        raise ValueError("el rol seleccionado requiere --organizacion")

    nombre_normalizado = nombre.strip()
    organizacion = session.scalar(
        select(Organizacion).where(
            Organizacion.tipo == tipo,
            Organizacion.nombre == nombre_normalizado,
        )
    )
    if organizacion is None:
        organizacion = Organizacion(tipo=tipo, nombre=nombre_normalizado)
        session.add(organizacion)
        session.flush()
    elif not organizacion.activa:
        raise ValueError("la organización indicada está inactiva")
    return organizacion


def _crear_usuario(
    session: Session,
    email: str,
    rol: RolUsuario,
    organizacion_nombre: str | None,
    password: str,
) -> Usuario:
    existente = session.scalar(
        select(Usuario).where(func.lower(Usuario.email) == email.lower())
    )
    if existente is not None:
        raise ValueError("ya existe un usuario con ese correo")

    organizacion = _obtener_organizacion(session, rol, organizacion_nombre)
    usuario = Usuario(
        organizacion_id=organizacion.id if organizacion is not None else None,
        email=email.lower(),
        password_hash=generar_password_hash(password),
        rol=rol,
    )
    session.add(usuario)
    session.flush()
    return usuario


def main() -> int:
    """Solicita una contraseña y persiste una identidad local lista para ingresar."""

    argumentos = _crear_parser().parse_args()
    try:
        email = str(_email_adapter.validate_python(argumentos.email)).lower()
        password = _leer_password()
        with SessionLocal.begin() as session:
            usuario = _crear_usuario(
                session,
                email,
                argumentos.rol,
                argumentos.organizacion,
                password,
            )
            usuario_id = usuario.id
    except (EOFError, KeyboardInterrupt):
        print("\nOperación cancelada.", file=sys.stderr)
        return 1
    except IntegrityError:
        print(
            "No se pudo crear el usuario por una restricción de los datos.",
            file=sys.stderr,
        )
        return 1
    except (ValidationError, ValueError) as error:
        print(f"No se pudo crear el usuario: {error}", file=sys.stderr)
        return 1

    print(f"Usuario {email} creado con id {usuario_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
