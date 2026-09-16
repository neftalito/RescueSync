"""Comprueba desde el backend el acceso a la API de Bonita y el proceso RescueSync."""

from __future__ import annotations

import sys

from app.core.config import get_settings
from app.integrations.bonita.cliente import (
    ClienteBonita,
    ConfiguracionBonita,
    ErrorBonita,
)


def main() -> int:
    """Ejecuta la verificación y comunica un resultado apto para scripts de shell."""

    configuracion = ConfiguracionBonita.desde_settings(get_settings())
    try:
        with ClienteBonita(configuracion) as cliente:
            proceso = cliente.obtener_proceso_habilitado()
    except ErrorBonita as error:
        print(f"[ERROR] La API de Bonita no está lista: {error}", file=sys.stderr)
        return 1

    print(f"[OK] Conexión y autenticación: {configuracion.base_url}")
    print(
        "[OK] Proceso listo: "
        f"{proceso.name}:{proceso.version} (id={proceso.id}, "
        f"{proceso.configuration_state}, {proceso.activation_state})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
