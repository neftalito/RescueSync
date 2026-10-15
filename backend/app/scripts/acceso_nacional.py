"""Importa una credencial técnica sin exponerla en argumentos ni logs."""

import argparse
import stat
from collections.abc import Sequence
from getpass import getpass
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.models import RolUsuario
from app.db.session import SessionLocal
from app.integrations.nacional.cliente import ClienteNacional, ErrorNacional
from app.schemas.inventario import CredencialTecnica
from app.services.acceso_nacional import importar_credencial
from app.services.auth import autenticar_usuario


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login", required=True)
    parser.add_argument("--organizacion", type=int, required=True)
    parser.add_argument("--archivo", type=Path, required=True)
    args = parser.parse_args(argv)
    settings = get_settings()
    cliente = ClienteNacional(
        str(settings.nacional_base_url), settings.nacional_timeout_seconds
    )
    try:
        with SessionLocal() as session:
            admin = autenticar_usuario(
                session, args.login, getpass("Contraseña administrativa local: ")
            )
            if (
                admin is None
                or admin.rol != RolUsuario.ADMINISTRADOR
                or admin.requiere_cambio_password
            ):
                raise ValueError("Se requiere una cuenta administrativa local activa.")
            if (
                args.archivo.is_symlink()
                or stat.S_IMODE(args.archivo.stat().st_mode) & 0o077
            ):
                raise ValueError(
                    "El archivo debe ser regular, privado (chmod 600) y no un enlace."
                )
            if not args.archivo.is_file():
                raise ValueError("Se requiere un archivo regular.")
            datos = CredencialTecnica.model_validate_json(args.archivo.read_bytes())
            importar_credencial(session, args.organizacion, datos, cliente)
            session.commit()
        print(
            "Acceso nacional configurado. Eliminá las copias del archivo de credenciales."
        )
        return 0
    except ValidationError:
        print("El archivo de credenciales no tiene un formato válido.")
    except (ValueError, ErrorNacional) as error:
        print(str(error))
    except (OSError, SQLAlchemyError):
        print("No se importó la credencial. Revisá permisos, base y configuración.")
    except (EOFError, KeyboardInterrupt):
        print("Operación cancelada.")
    finally:
        cliente.close()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
