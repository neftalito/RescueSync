from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
import respx

from app.integrations.bonita.deploy import (
    Config,
    DeploymentError,
    _configured_bar_content,
    deploy,
    ensure_actor_users,
)

BASE_URL = "http://bonita:8080/bonita"


def _config(
    tmp_path: Path,
    *,
    actor_usernames: tuple[str, ...] = (),
) -> Config:
    """Crea una configuración aislada con un BAR de prueba."""

    bar_path = tmp_path / "RescueSync--1.0.bar"
    users = "".join(
        f"<users><user>{username}</user></users>" for username in actor_usernames
    )
    with ZipFile(bar_path, "w") as archive:
        archive.writestr("actorMapping.xml", f"<actorMappings>{users}</actorMappings>")
        archive.writestr("parameters.properties", "# sin configurar\n")
    return Config(
        base_url=BASE_URL,
        username="install",
        password="install",
        actor_password="clave-actores",
        process_name="RescueSync",
        process_version="1.0",
        process_parameters=(
            ("callbackToken", "token-de-prueba"),
            ("backendBaseUrl", "http://backend:8000"),
            ("ventanaOfertasMs", "7200000"),
        ),
        bar_path=bar_path,
        startup_timeout_seconds=1,
        request_timeout_seconds=1,
    )


def _process_payload(
    *,
    activation_state: str,
    configuration_state: str = "RESOLVED",
) -> dict[str, str]:
    """Devuelve una definición mínima válida de Bonita."""

    return {
        "id": "123",
        "name": "RescueSync",
        "version": "1.0",
        "activationState": activation_state,
        "configurationState": configuration_state,
    }


def _mock_login(router: respx.MockRouter) -> None:
    """Simula el inicio de sesión y la cookie CSRF de Bonita."""

    router.post(f"{BASE_URL}/loginservice").mock(
        return_value=httpx.Response(
            204,
            headers={"set-cookie": "X-Bonita-API-Token=csrf-token; Path=/bonita"},
        )
    )


def test_no_reinstala_un_proceso_ya_habilitado(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with respx.mock(assert_all_called=True) as router:
        _mock_login(router)
        process_search = router.get(f"{BASE_URL}/API/bpm/process").mock(
            return_value=httpx.Response(
                200,
                json=[_process_payload(activation_state="ENABLED")],
            )
        )

        deploy(config)

    assert process_search.call_count == 1


def test_instala_y_habilita_un_proceso_ausente(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with respx.mock(assert_all_called=True) as router:
        _mock_login(router)
        router.get(f"{BASE_URL}/API/bpm/process").mock(
            return_value=httpx.Response(200, json=[])
        )
        upload = router.post(f"{BASE_URL}/portal/processUpload").mock(
            return_value=httpx.Response(200, text="tmp_rescuesync.bar")
        )
        install = router.post(f"{BASE_URL}/API/bpm/process").mock(
            return_value=httpx.Response(
                200,
                json=[_process_payload(activation_state="DISABLED")][0],
            )
        )
        enable = router.put(f"{BASE_URL}/API/bpm/process/123").mock(
            return_value=httpx.Response(200)
        )

        deploy(config)

    assert upload.call_count == 1
    assert install.calls.last.request.content == b'{"fileupload":"tmp_rescuesync.bar"}'
    assert enable.calls.last.request.content == b'{"activationState":"ENABLED"}'


def test_rechaza_habilitar_un_proceso_sin_resolver(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with respx.mock(assert_all_called=True) as router:
        _mock_login(router)
        unresolved = httpx.Response(
            200,
            json=[
                _process_payload(
                    activation_state="DISABLED",
                    configuration_state="UNRESOLVED",
                )
            ],
        )
        router.get(f"{BASE_URL}/API/bpm/process").mock(return_value=unresolved)
        router.get(f"{BASE_URL}/API/bpm/processResolutionProblem").mock(
            return_value=httpx.Response(
                200,
                json=[{"message": "Actor 'ONG' does not contain any members"}],
            )
        )

        with pytest.raises(DeploymentError, match="Actor 'ONG'"):
            deploy(config)


def test_inyecta_los_parametros_en_una_copia_del_bar(tmp_path: Path) -> None:
    config = _config(tmp_path)

    content = _configured_bar_content(config.bar_path, config.process_parameters)

    with ZipFile(BytesIO(content.read())) as archive:
        properties = archive.read("parameters.properties").decode("iso-8859-1")
    assert properties == (
        "callbackToken=token-de-prueba\n"
        "backendBaseUrl=http://backend:8000\n"
        "ventanaOfertasMs=7200000\n"
    )
    with ZipFile(config.bar_path) as original:
        assert original.read("parameters.properties") == b"# sin configurar\n"


def test_crea_los_usuarios_referenciados_por_los_actores(tmp_path: Path) -> None:
    config = _config(tmp_path, actor_usernames=("api.rescuesync",))

    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/API/identity/user").mock(
            return_value=httpx.Response(200, json=[])
        )
        create_user = router.post(f"{BASE_URL}/API/identity/user").mock(
            return_value=httpx.Response(200, json={"id": "42"})
        )

        with httpx.Client() as client:
            ensure_actor_users(client, config, config.bar_path)

    assert create_user.calls.last.request.content == (
        b'{"userName":"api.rescuesync","password":"clave-actores",'
        b'"password_confirm":"clave-actores","firstname":"Api",'
        b'"lastname":"Rescuesync","enabled":"true"}'
    )
