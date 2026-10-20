"""Comprueba las credenciales efectivas de Compose sin iniciar servicios."""

import json
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "secreto-descartable-para-pruebas"


def entornos(
    variables: dict[str, str], *, archivo: str = "/dev/null"
) -> dict[str, dict[str, str]]:
    """Resuelve Compose sin heredar secretos ni el .env del operador."""
    resultado = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            archivo,
            "--file",
            str(ROOT / "compose.yaml"),
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env={"PATH": os.environ["PATH"], **variables},
        check=True,
        capture_output=True,
        text=True,
    )
    configuracion = json.loads(resultado.stdout)
    return {
        nombre: configuracion["services"][nombre]["environment"]
        for nombre in ("backend", "migrate", "bonita-deploy")
    }


class ConfiguracionNacionalTest(unittest.TestCase):
    def test_comparte_la_cuenta_entre_alta_catalogo_y_bonita(self) -> None:
        for archivo in ("/dev/null", str(ROOT / ".env.example")):
            with self.subTest(archivo=archivo):
                servicios = entornos(
                    {"NACIONAL_INTEGRACION_PASSWORD": PASSWORD}, archivo=archivo
                )
                for nombre in ("backend", "migrate"):
                    entorno = servicios[nombre]
                    self.assertEqual(
                        entorno["NACIONAL_CATALOGO_LOGIN"], "integracion-rescuesync"
                    )
                    for variable in (
                        "NACIONAL_CATALOGO_PASSWORD",
                        "NACIONAL_APROVISIONAMIENTO_PASSWORD",
                    ):
                        self.assertEqual(entorno[variable], PASSWORD)
                self.assertEqual(
                    servicios["bonita-deploy"]["BONITA_NATIONAL_API_PASSWORD"],
                    PASSWORD,
                )

    def test_conserva_el_administrador_explicito_del_catalogo(self) -> None:
        servicios = entornos(
            {
                "NACIONAL_INTEGRACION_PASSWORD": PASSWORD,
                "NACIONAL_CATALOGO_LOGIN": "administrador-nacional",
                "NACIONAL_CATALOGO_PASSWORD": "secreto-administrativo-descartable",
            }
        )
        entorno = servicios["backend"]
        self.assertEqual(entorno["NACIONAL_CATALOGO_LOGIN"], "administrador-nacional")
        self.assertEqual(
            entorno["NACIONAL_CATALOGO_PASSWORD"],
            "secreto-administrativo-descartable",
        )
        self.assertEqual(entorno["NACIONAL_APROVISIONAMIENTO_PASSWORD"], PASSWORD)

    def test_catalogo_usa_la_cuenta_efectiva_de_aprovisionamiento(self) -> None:
        entorno = entornos(
            {
                "NACIONAL_INTEGRACION_PASSWORD": PASSWORD,
                "NACIONAL_APROVISIONAMIENTO_LOGIN": "otro-emisor",
                "NACIONAL_APROVISIONAMIENTO_PASSWORD": "secreto-anterior-descartable",
                "BONITA_NATIONAL_API_PASSWORD": "secreto-bonita-descartable",
            }
        )
        self.assertEqual(entorno["backend"]["NACIONAL_CATALOGO_LOGIN"], "otro-emisor")
        self.assertEqual(
            entorno["backend"]["NACIONAL_CATALOGO_PASSWORD"],
            "secreto-anterior-descartable",
        )
        self.assertEqual(
            entorno["bonita-deploy"]["BONITA_NATIONAL_API_PASSWORD"],
            "secreto-bonita-descartable",
        )

    def test_overrides_vacios_usan_el_secreto_compartido(self) -> None:
        servicios = entornos(
            {
                "NACIONAL_INTEGRACION_PASSWORD": PASSWORD,
                "NACIONAL_APROVISIONAMIENTO_PASSWORD": "",
                "NACIONAL_CATALOGO_LOGIN": "",
                "NACIONAL_CATALOGO_PASSWORD": "",
                "BONITA_NATIONAL_API_PASSWORD": "",
            }
        )
        self.assertEqual(servicios["backend"]["NACIONAL_CATALOGO_PASSWORD"], PASSWORD)
        self.assertEqual(
            servicios["bonita-deploy"]["BONITA_NATIONAL_API_PASSWORD"], PASSWORD
        )

    def test_no_inventa_una_contrasena_si_falta_el_secreto(self) -> None:
        servicios = entornos({})
        for nombre in ("backend", "migrate"):
            for variable in (
                "NACIONAL_APROVISIONAMIENTO_PASSWORD",
                "NACIONAL_CATALOGO_PASSWORD",
            ):
                self.assertEqual(servicios[nombre][variable], "")
        self.assertEqual(servicios["bonita-deploy"]["BONITA_NATIONAL_API_PASSWORD"], "")


if __name__ == "__main__":
    unittest.main()
