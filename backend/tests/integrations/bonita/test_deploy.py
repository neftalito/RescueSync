import logging
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
    ensure_initial_admin,
)

BASE_URL = "http://bonita:8080/bonita"
TOKEN = "t" * 40
PARAMETROS = (
    ("backendBaseUrl", "http://backend:8000"),
    ("ventanaOfertasMs", "7200000"),
    ("callbackToken", TOKEN),
)


def _config(
    tmp_path: Path,
    *,
    actor_usernames: tuple[str, ...] = (),
    bar_version: str = "1.0",
) -> Config:
    """Crea una configuración aislada con un BAR de prueba."""

    bar_path = tmp_path / "RescueSync--1.0.bar"
    users = "".join(
        f"<users><user>{username}</user></users>" for username in actor_usernames
    )
    with ZipFile(bar_path, "w") as archive:
        archive.writestr("actorMapping.xml", f"<actorMappings>{users}</actorMappings>")
        archive.writestr("parameters.properties", "# sin configurar\n")
        archive.writestr(
            "process-design.xml",
            f'<processDefinition name="RescueSync" version="{bar_version}"/>',
        )
    return Config(
        base_url=BASE_URL,
        username="install",
        password="install",
        admin_username="admin@rescuesync.org",
        admin_initial_password="administrador123",
        actor_password="clave-actores",
        process_name="RescueSync",
        process_version="1.0",
        process_parameters=PARAMETROS,
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
    router.get(f"{BASE_URL}/API/portal/profile").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "7", "name": "Administrator"}],
        )
    )
    router.get(f"{BASE_URL}/API/identity/user").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "8", "userName": "admin@rescuesync.org"}],
        )
    )
    router.get(f"{BASE_URL}/API/portal/profileMember").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "9", "profile_id": "7", "user_id": "8"}],
        )
    )


def _parametros_instalados(**cambios: str) -> list[dict[str, str]]:
    valores = dict(PARAMETROS) | cambios
    return [
        {"process_id": "123", "name": nombre, "value": valor}
        for nombre, valor in valores.items()
    ]


def _mock_habilitado(router: respx.MockRouter) -> respx.Route:
    return router.get(f"{BASE_URL}/API/bpm/process").mock(
        return_value=httpx.Response(
            200,
            json=[_process_payload(activation_state="ENABLED")],
        )
    )


def test_no_reinstala_un_proceso_ya_habilitado(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with respx.mock(assert_all_called=True) as router:
        _mock_login(router)
        process_search = _mock_habilitado(router)
        router.get(f"{BASE_URL}/API/bpm/processParameter").mock(
            return_value=httpx.Response(200, json=_parametros_instalados())
        )

        deploy(config)

    assert process_search.call_count == 1


def test_rechaza_un_proceso_instalado_con_otro_token_sin_revelarlo(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    token_instalado = "i" * 40

    with respx.mock(assert_all_called=True) as router:
        _mock_login(router)
        _mock_habilitado(router)
        router.get(f"{BASE_URL}/API/bpm/processParameter").mock(
            return_value=httpx.Response(
                200, json=_parametros_instalados(callbackToken=token_instalado)
            )
        )

        with pytest.raises(DeploymentError, match="callbackToken") as error:
            deploy(config)

    assert TOKEN not in str(error.value)
    assert token_instalado not in str(error.value)


def test_advierte_otros_parametros_distintos_sin_fallar(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = _config(tmp_path)

    with respx.mock(assert_all_called=True) as router:
        _mock_login(router)
        _mock_habilitado(router)
        router.get(f"{BASE_URL}/API/bpm/processParameter").mock(
            return_value=httpx.Response(
                200, json=_parametros_instalados(ventanaOfertasMs="60000")
            )
        )

        with caplog.at_level(logging.WARNING, logger="bonita-deploy"):
            deploy(config)

    assert "ventanaOfertasMs" in caplog.text


def test_rechaza_un_bar_de_otra_version_antes_de_contactar_bonita(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, bar_version="9.9")

    with (
        respx.mock(assert_all_called=False) as router,
        pytest.raises(DeploymentError, match="RescueSync:9.9"),
    ):
        deploy(config)

    assert not router.calls


def test_el_entorno_exige_un_token_de_callback_robusto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for nombre, valor in {
        "BONITA_BASE_URL": BASE_URL,
        "BONITA_USERNAME": "install",
        "BONITA_PASSWORD": "install",
        "ADMIN_EMAIL": "admin@rescuesync.org",
        "ADMIN_INITIAL_PASSWORD": "administrador123",
        "BONITA_BAR_PATH": "/bonita-source",
        "BONITA_PROCESS_NAME": "RescueSync",
        "BONITA_PROCESS_VERSION": "1.2",
    }.items():
        monkeypatch.setenv(nombre, valor)

    monkeypatch.setenv("BONITA_CALLBACK_TOKEN", "corto")
    with pytest.raises(DeploymentError, match="al menos 32"):
        Config.from_environment()

    monkeypatch.setenv("BONITA_CALLBACK_TOKEN", TOKEN)
    config = Config.from_environment()
    assert (config.process_name, config.process_version) == ("RescueSync", "1.2")
    assert ("callbackToken", TOKEN) in config.process_parameters


def test_crea_el_administrador_inicial_y_le_asigna_su_perfil(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    with respx.mock(assert_all_called=True) as router:
        profile_search = router.get(f"{BASE_URL}/API/portal/profile").mock(
            return_value=httpx.Response(
                200, json=[{"id": "7", "name": "Administrator"}]
            )
        )
        user_search = router.get(f"{BASE_URL}/API/identity/user").mock(
            return_value=httpx.Response(200, json=[])
        )
        create_user = router.post(f"{BASE_URL}/API/identity/user").mock(
            return_value=httpx.Response(
                200,
                json={"id": "8", "userName": "admin@rescuesync.org"},
            )
        )
        member_search = router.get(f"{BASE_URL}/API/portal/profileMember").mock(
            return_value=httpx.Response(200, json=[])
        )
        create_member = router.post(f"{BASE_URL}/API/portal/profileMember").mock(
            return_value=httpx.Response(
                200,
                json={"id": "9", "profile_id": "7", "user_id": "8"},
            )
        )

        with httpx.Client() as client:
            ensure_initial_admin(client, config)

    assert profile_search.calls.last.request.url.params.get_list("f") == [
        "name=Administrator"
    ]
    assert user_search.calls.last.request.url.params.get_list("f") == [
        "userName=admin@rescuesync.org"
    ]
    assert create_user.calls.last.request.content == (
        b'{"userName":"admin@rescuesync.org","password":"administrador123",'
        b'"password_confirm":"administrador123","firstname":"Administrador",'
        b'"lastname":"RescueSync","enabled":"true"}'
    )
    assert member_search.calls.last.request.url.params.get_list("f") == [
        "member_type=user",
        "profile_id=7",
        "user_id=8",
    ]
    assert create_member.calls.last.request.content == (
        b'{"profile_id":"7","member_type":"USER","user_id":"8"}'
    )


def test_no_modifica_un_administrador_ya_mapeado(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with respx.mock(assert_all_called=False) as router:
        profile_search = router.get(f"{BASE_URL}/API/portal/profile").mock(
            return_value=httpx.Response(200, json=[{"id": 7, "name": "Administrator"}])
        )
        user_search = router.get(f"{BASE_URL}/API/identity/user").mock(
            return_value=httpx.Response(
                200, json=[{"id": 8, "userName": "admin@rescuesync.org"}]
            )
        )
        member_search = router.get(f"{BASE_URL}/API/portal/profileMember").mock(
            return_value=httpx.Response(
                200, json=[{"id": 9, "profile_id": 7, "user_id": 8}]
            )
        )
        create_user = router.post(f"{BASE_URL}/API/identity/user")
        create_member = router.post(f"{BASE_URL}/API/portal/profileMember")

        with httpx.Client() as client:
            ensure_initial_admin(client, config)

    assert profile_search.call_count == 1
    assert user_search.call_count == 1
    assert member_search.call_count == 1
    assert not create_user.called
    assert not create_member.called


def test_no_eleva_una_cuenta_homonima_con_otra_password(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/API/portal/profile").mock(
            return_value=httpx.Response(
                200, json=[{"id": "7", "name": "Administrator"}]
            )
        )
        router.get(f"{BASE_URL}/API/identity/user").mock(
            return_value=httpx.Response(
                200, json=[{"id": "8", "userName": "admin@rescuesync.org"}]
            )
        )
        router.get(f"{BASE_URL}/API/portal/profileMember").mock(
            return_value=httpx.Response(200, json=[])
        )
        router.post(f"{BASE_URL}/loginservice").mock(return_value=httpx.Response(401))

        with (
            httpx.Client() as client,
            pytest.raises(DeploymentError, match="otras credenciales"),
        ):
            ensure_initial_admin(client, config)


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


def _sin_resolver() -> httpx.Response:
    return httpx.Response(
        200,
        json=[
            _process_payload(
                activation_state="DISABLED",
                configuration_state="UNRESOLVED",
            )
        ],
    )


def _conteo(total: int) -> httpx.Response:
    return httpx.Response(200, json=[], headers={"Content-Range": f"0-1/{total}"})


def test_no_elimina_un_proceso_sin_resolver_que_tiene_casos(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with respx.mock(assert_all_called=False) as router:
        _mock_login(router)
        router.get(f"{BASE_URL}/API/bpm/process").mock(return_value=_sin_resolver())
        router.get(f"{BASE_URL}/API/bpm/case").mock(return_value=_conteo(1))
        router.get(f"{BASE_URL}/API/bpm/processParameter").mock(
            return_value=httpx.Response(200, json=_parametros_instalados())
        )
        router.get(f"{BASE_URL}/API/bpm/processResolutionProblem").mock(
            return_value=httpx.Response(
                200,
                json=[{"message": "Actor 'ONG' does not contain any members"}],
            )
        )
        eliminar = router.delete(f"{BASE_URL}/API/bpm/process/123")

        with pytest.raises(DeploymentError, match="Actor 'ONG'"):
            deploy(config)

    assert not eliminar.called


def test_reinstala_un_proceso_sin_resolver_y_sin_casos(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with respx.mock(assert_all_called=True) as router:
        _mock_login(router)
        router.get(f"{BASE_URL}/API/bpm/process").mock(return_value=_sin_resolver())
        router.get(f"{BASE_URL}/API/bpm/case").mock(return_value=_conteo(0))
        router.get(f"{BASE_URL}/API/bpm/archivedCase").mock(return_value=_conteo(0))
        router.get(f"{BASE_URL}/API/bpm/processResolutionProblem").mock(
            return_value=httpx.Response(
                200, json=[{"message": "Parameter 'callbackToken' is not set."}]
            )
        )
        eliminar = router.delete(f"{BASE_URL}/API/bpm/process/123").mock(
            return_value=httpx.Response(200)
        )
        router.post(f"{BASE_URL}/portal/processUpload").mock(
            return_value=httpx.Response(200, text="tmp_rescuesync.bar")
        )
        instalar = router.post(f"{BASE_URL}/API/bpm/process").mock(
            return_value=httpx.Response(
                200, json=_process_payload(activation_state="DISABLED")
            )
        )
        habilitar = router.put(f"{BASE_URL}/API/bpm/process/123").mock(
            return_value=httpx.Response(200)
        )

        deploy(config)

    assert eliminar.call_count == 1
    assert instalar.call_count == 1
    assert habilitar.call_count == 1


def test_inyecta_los_parametros_en_una_copia_del_bar(tmp_path: Path) -> None:
    config = _config(tmp_path)

    content = _configured_bar_content(config.bar_path, config.process_parameters)

    with ZipFile(BytesIO(content.read())) as archive:
        properties = archive.read("parameters.properties").decode("iso-8859-1")
    assert properties == (
        "backendBaseUrl=http://backend:8000\nventanaOfertasMs=7200000\n"
        f"callbackToken={TOKEN}\n"
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
