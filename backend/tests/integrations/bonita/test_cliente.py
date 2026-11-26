import json
from collections.abc import Iterator

import httpx
import pytest
import respx
from pydantic import SecretStr, ValidationError

from app.db.models.enums import GravedadEmergencia
from app.integrations.bonita.cliente import (
    BonitaCredencialesError,
    BonitaNoDisponibleError,
    BonitaOperacionRechazadaError,
    BonitaProcesoNoDisponibleError,
    BonitaRespuestaInvalidaError,
    BonitaResultadoDesconocidoError,
    ClienteBonita,
    ConfiguracionBonita,
)
from app.integrations.bonita.contratos import ContratoInicioProceso

BASE_URL = "http://bonita:8080/bonita"
PASSWORD = "clave-tecnica-secreta"


@pytest.fixture
def cliente() -> Iterator[ClienteBonita]:
    configuracion = ConfiguracionBonita(
        base_url=BASE_URL,
        usuario="install",
        password=SecretStr(PASSWORD),
        nombre_proceso="RescueSync",
        version_proceso="1.2",
        timeout_conexion_segundos=1,
        timeout_lectura_segundos=1,
    )
    with ClienteBonita(configuracion) as cliente:
        yield cliente


def _login(router: respx.MockRouter, token: str = "csrf-1") -> respx.Route:
    return router.post(f"{BASE_URL}/loginservice").mock(
        return_value=httpx.Response(
            204,
            headers={"set-cookie": f"X-Bonita-API-Token={token}; Path=/bonita"},
        )
    )


def _proceso(
    *,
    activation_state: str = "ENABLED",
    configuration_state: str = "RESOLVED",
) -> dict[str, str]:
    return {
        "id": "7204236220545867063",
        "name": "RescueSync",
        "version": "1.2",
        "activationState": activation_state,
        "configurationState": configuration_state,
    }


def _contrato(**cambios: object) -> ContratoInicioProceso:
    datos: dict[str, object] = {
        "idEmergencia": 123,
        "gravedad": GravedadEmergencia.ALTA,
        "zona": "Zona norte",
        "descripcion": "Inundación con familias evacuadas",
        "municipioId": 7,
    }
    datos.update(cambios)
    return ContratoInicioProceso.model_validate(datos)


def _transicion(identidad: int, *, root: int = 42) -> dict[str, str]:
    return {
        "type": "USER_TASK",
        "sourceObjectId": str(identidad),
        "rootCaseId": str(root),
        "name": "Generar lotes",
        "state": "ready",
        "reached_state_date": "2026-10-15 09:00:00",
    }


@respx.mock
def test_reprograma_solo_el_temporizador_elegido_del_caso(
    cliente: ClienteBonita,
) -> None:
    _login(respx)
    temporizadores = respx.get(f"{BASE_URL}/API/bpm/timerEventTrigger").respond(
        200,
        json=[
            {
                "id": 51,
                "eventInstanceName": "Recordatorio",
                "executionDate": 1795712400000,
            },
            {
                "id": 52,
                "eventInstanceName": "EsperarOfertas",
                "executionDate": 1795719600000,
            },
        ],
    )
    fecha = 1795712460000
    cambio = respx.put(f"{BASE_URL}/API/bpm/timerEventTrigger/52").respond(
        200, json={"executionDate": fecha}
    )

    timer = cliente.buscar_temporizador(42, "EsperarOfertas")
    assert timer is not None
    assert temporizadores.calls.last.request.url.params["caseId"] == "42"
    cliente.reprogramar_temporizador(timer.id, fecha)
    assert json.loads(cambio.calls.last.request.content) == {"executionDate": fecha}


@respx.mock
def test_tareas_activas_pagina_y_rechaza_datos_de_otro_caso(
    cliente: ClienteBonita,
) -> None:
    _login(respx)

    def tarea(identidad: int, root: int = 42) -> dict[str, str]:
        return {
            "id": str(identidad),
            "rootCaseId": str(root),
            "name": "Revisar",
            "type": "USER_TASK",
            "state": "ready",
            "reached_state_date": "2026-10-15 09:00:00",
            "dueDate": "",
        }

    temporizador = {
        "id": "102",
        "rootCaseId": "42",
        "name": "EsperarOfertas",
        "type": "INTERMEDIATE_CATCH_EVENT",
        "state": "waiting",
    }
    ruta = respx.get(f"{BASE_URL}/API/bpm/flowNode").mock(
        side_effect=[
            httpx.Response(200, json=[tarea(i) for i in range(1, 101)]),
            httpx.Response(200, json=[tarea(101), temporizador]),
        ]
    )
    nodos = cliente.obtener_tareas_activas(42)
    assert len(nodos) == 102
    assert nodos[-1].name == "EsperarOfertas"
    assert nodos[-1].reached_state_date is None
    assert ruta.calls[1].request.url.params["p"] == "1"
    assert ruta.calls[0].request.url.params["f"] == "caseId=42"
    ruta.mock(return_value=httpx.Response(200, json=[tarea(1, root=99)]))
    with pytest.raises(BonitaRespuestaInvalidaError, match="otro caso"):
        cliente.obtener_tareas_activas(42)


def test_historial_pagina_estados_intermedios_y_terminales(
    cliente: ClienteBonita,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        intermedios = router.get(f"{BASE_URL}/API/bpm/archivedFlowNode").mock(
            side_effect=[
                httpx.Response(200, json=[_transicion(i + 1) for i in range(100)]),
                httpx.Response(
                    200,
                    json=[
                        {
                            **_transicion(1),
                            "state": "completed",
                            "reached_state_date": "2026-10-15 10:00:00",
                        }
                    ],
                ),
            ]
        )
        historial = cliente.obtener_historial_tareas(42)
    assert len(historial) == 101
    assert intermedios.calls[1].request.url.params["p"] == "1"
    assert intermedios.calls[0].request.url.params["f"] == "caseId=42"
    assert historial[-1].state == "completed"


def test_historial_rechaza_transiciones_de_otro_caso(cliente: ClienteBonita) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.get(f"{BASE_URL}/API/bpm/archivedFlowNode").mock(
            return_value=httpx.Response(200, json=[_transicion(1, root=99)])
        )
        with pytest.raises(BonitaRespuestaInvalidaError, match="otro caso"):
            cliente.obtener_historial_tareas(42)


def test_resuelve_el_proceso_habilitado_con_token_csrf(cliente: ClienteBonita) -> None:
    with respx.mock(assert_all_called=True) as router:
        login = _login(router)
        busqueda = router.get(f"{BASE_URL}/API/bpm/process").mock(
            return_value=httpx.Response(200, json=[_proceso()])
        )

        proceso = cliente.obtener_proceso_habilitado()
        cliente.obtener_proceso_habilitado()

    assert proceso.id == 7204236220545867063
    assert login.call_count == 1
    peticion = busqueda.calls.last.request
    assert peticion.headers["X-Bonita-API-Token"] == "csrf-1"
    assert peticion.url.params.get_list("f") == ["name=RescueSync", "version=1.2"]


@pytest.mark.parametrize(
    ("activation_state", "configuration_state"),
    [("DISABLED", "RESOLVED"), ("ENABLED", "UNRESOLVED")],
)
def test_rechaza_un_proceso_que_no_puede_iniciar_casos(
    cliente: ClienteBonita,
    activation_state: str,
    configuration_state: str,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.get(f"{BASE_URL}/API/bpm/process").mock(
            return_value=httpx.Response(
                200,
                json=[
                    _proceso(
                        activation_state=activation_state,
                        configuration_state=configuration_state,
                    )
                ],
            )
        )

        with pytest.raises(BonitaProcesoNoDisponibleError, match=activation_state):
            cliente.obtener_proceso_habilitado()


def test_informa_un_proceso_inexistente(cliente: ClienteBonita) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.get(f"{BASE_URL}/API/bpm/process").mock(
            return_value=httpx.Response(200, json=[])
        )

        with pytest.raises(BonitaProcesoNoDisponibleError, match="devolvió 0"):
            cliente.obtener_proceso_habilitado()


def test_credenciales_rechazadas_no_exponen_la_clave(cliente: ClienteBonita) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.post(f"{BASE_URL}/loginservice").mock(return_value=httpx.Response(401))

        with pytest.raises(BonitaCredencialesError) as error:
            cliente.obtener_proceso_habilitado()

    assert PASSWORD not in str(error.value)


def test_informa_bonita_no_disponible_si_no_puede_conectar(
    cliente: ClienteBonita,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.post(f"{BASE_URL}/loginservice").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        with pytest.raises(BonitaNoDisponibleError):
            cliente.obtener_proceso_habilitado()


def test_renueva_una_sesion_expirada_una_sola_vez(cliente: ClienteBonita) -> None:
    with respx.mock(assert_all_called=True) as router:
        login = router.post(f"{BASE_URL}/loginservice").mock(
            side_effect=[
                httpx.Response(204, headers={"set-cookie": "X-Bonita-API-Token=t1"}),
                httpx.Response(204, headers={"set-cookie": "X-Bonita-API-Token=t2"}),
            ]
        )
        busqueda = router.get(f"{BASE_URL}/API/bpm/process").mock(
            side_effect=[
                httpx.Response(401),
                httpx.Response(200, json=[_proceso()]),
            ]
        )

        cliente.obtener_proceso_habilitado()

    assert login.call_count == 2
    assert busqueda.calls.last.request.headers["X-Bonita-API-Token"] == "t2"


def test_rechaza_respuestas_con_formato_inesperado(cliente: ClienteBonita) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.get(f"{BASE_URL}/API/bpm/process").mock(
            return_value=httpx.Response(200, json={"id": "no-es-una-lista"})
        )

        with pytest.raises(BonitaRespuestaInvalidaError):
            cliente.obtener_proceso_habilitado()


def test_rechaza_una_definicion_que_no_coincide_con_el_filtro(
    cliente: ClienteBonita,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.get(f"{BASE_URL}/API/bpm/process").mock(
            return_value=httpx.Response(
                200,
                json=[_proceso() | {"version": "2.0"}],
            )
        )

        with pytest.raises(BonitaRespuestaInvalidaError, match="definición ajena"):
            cliente.obtener_proceso_habilitado()


def test_rechaza_un_identificador_externo_no_positivo(cliente: ClienteBonita) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.get(f"{BASE_URL}/API/bpm/process").mock(
            return_value=httpx.Response(200, json=[_proceso() | {"id": "0"}])
        )

        with pytest.raises(BonitaRespuestaInvalidaError):
            cliente.obtener_proceso_habilitado()


def test_inicia_una_instancia_con_el_contrato_exacto(cliente: ClienteBonita) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        instanciacion = router.post(
            f"{BASE_URL}/API/bpm/process/55/instantiation"
        ).mock(return_value=httpx.Response(201, json={"caseId": 4}))

        instancia = cliente.iniciar_instancia(55, _contrato())

    assert instancia.case_id == 4
    assert json.loads(instanciacion.calls.last.request.content) == {
        "idEmergencia": 123,
        "gravedad": "ALTA",
        "zona": "Zona norte",
        "descripcion": "Inundación con familias evacuadas",
        "municipioId": 7,
    }


@pytest.mark.parametrize("estado", [200, 201])
def test_admite_los_codigos_de_instanciacion_de_bonita_10_4(
    cliente: ClienteBonita,
    estado: int,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.post(f"{BASE_URL}/API/bpm/process/55/instantiation").mock(
            return_value=httpx.Response(estado, json={"caseId": 4})
        )

        instancia = cliente.iniciar_instancia(55, _contrato())

    assert instancia.case_id == 4


def test_rechaza_otro_codigo_de_exito_distinto_del_contrato_http(
    cliente: ClienteBonita,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.post(f"{BASE_URL}/API/bpm/process/55/instantiation").mock(
            return_value=httpx.Response(202, json={"caseId": 4})
        )

        with pytest.raises(
            BonitaRespuestaInvalidaError, match="se esperaba HTTP 200 o 201"
        ):
            cliente.iniciar_instancia(55, _contrato())


def test_traduce_un_contrato_rechazado_por_bonita(cliente: ClienteBonita) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.post(f"{BASE_URL}/API/bpm/process/55/instantiation").mock(
            return_value=httpx.Response(
                400,
                json={
                    "exception": "ContractViolationException",
                    "message": f"Error interno con {PASSWORD}",
                    "explanations": ["Expected input [zona] is missing", None],
                },
            )
        )

        with pytest.raises(BonitaOperacionRechazadaError) as error:
            cliente.iniciar_instancia(55, _contrato())

    assert error.value.explicaciones == ("Expected input [zona] is missing",)
    assert PASSWORD not in str(error.value)


@pytest.mark.parametrize(
    "fallo",
    [httpx.ReadTimeout("timeout"), httpx.RemoteProtocolError("closed")],
)
def test_no_reintenta_una_instanciacion_con_resultado_incierto(
    cliente: ClienteBonita,
    fallo: httpx.TransportError,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        instanciacion = router.post(
            f"{BASE_URL}/API/bpm/process/55/instantiation"
        ).mock(side_effect=fallo)

        with pytest.raises(BonitaResultadoDesconocidoError):
            cliente.iniciar_instancia(55, _contrato())

    assert instanciacion.call_count == 1


def test_un_error_500_al_instanciar_deja_un_resultado_desconocido(
    cliente: ClienteBonita,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        instanciacion = router.post(
            f"{BASE_URL}/API/bpm/process/55/instantiation"
        ).mock(return_value=httpx.Response(500))

        with pytest.raises(BonitaResultadoDesconocidoError, match="HTTP 500"):
            cliente.iniciar_instancia(55, _contrato())

    assert instanciacion.call_count == 1


def test_un_error_500_en_una_consulta_permite_reintentar(
    cliente: ClienteBonita,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.get(f"{BASE_URL}/API/bpm/process").mock(return_value=httpx.Response(500))

        with pytest.raises(BonitaNoDisponibleError, match="HTTP 500"):
            cliente.obtener_proceso_habilitado()


def test_busca_casos_activos_por_id_de_emergencia(cliente: ClienteBonita) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        busqueda = router.get(f"{BASE_URL}/API/bpm/case").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "id": "4",
                        "processDefinitionId": "55",
                        "state": "started",
                        "searchIndex1Label": "idEmergencia",
                        "searchIndex1Value": "123",
                    }
                ],
            )
        )

        casos = cliente.buscar_casos_por_emergencia(55, 123)

    assert [caso.id for caso in casos] == [4]
    assert busqueda.calls.last.request.url.params.get_list("f") == [
        "processDefinitionId=55",
        "searchIndex1Value=123",
    ]


@pytest.mark.parametrize(
    "cambio",
    [
        {"processDefinitionId": "56"},
        {"searchIndex1Label": "otroIndice"},
        {"searchIndex1Value": "124"},
    ],
)
def test_rechaza_un_caso_que_no_coincide_con_la_correlacion(
    cliente: ClienteBonita,
    cambio: dict[str, str],
) -> None:
    caso = {
        "id": "4",
        "processDefinitionId": "55",
        "state": "started",
        "searchIndex1Label": "idEmergencia",
        "searchIndex1Value": "123",
    }
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.get(f"{BASE_URL}/API/bpm/case").mock(
            return_value=httpx.Response(200, json=[caso | cambio])
        )

        with pytest.raises(BonitaRespuestaInvalidaError, match="no coincide"):
            cliente.buscar_casos_por_emergencia(55, 123)


def test_asigna_al_actor_antes_de_ejecutar_la_tarea(cliente: ClienteBonita) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.get(f"{BASE_URL}/API/identity/user").mock(
            return_value=httpx.Response(
                200, json=[{"id": "9", "userName": "coordinador.regional"}]
            )
        )
        asignacion = router.put(f"{BASE_URL}/API/bpm/humanTask/17").mock(
            return_value=httpx.Response(200)
        )
        ejecucion = router.post(f"{BASE_URL}/API/bpm/userTask/17/execution").mock(
            return_value=httpx.Response(204)
        )

        cliente.ejecutar_tarea(17, "coordinador.regional")

    assert asignacion.calls.last.request.content == b'{"assigned_id":"9"}'
    assert ejecucion.call_count == 1
    assert asignacion.calls.last.request.headers["X-Bonita-API-Token"] == "csrf-1"


def test_devuelve_la_tarea_lista_buscada(cliente: ClienteBonita) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.get(f"{BASE_URL}/API/bpm/humanTask").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "id": "17",
                        "name": "Generar lotes de necesidades",
                        "state": "ready",
                        "caseId": "4",
                    }
                ],
            )
        )

        tarea = cliente.buscar_tarea_lista(4, "Generar lotes de necesidades")

    assert tarea is not None
    assert tarea.id == 17


def test_rechaza_una_tarea_que_no_coincide_con_el_filtro(
    cliente: ClienteBonita,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.get(f"{BASE_URL}/API/bpm/humanTask").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "id": "17",
                        "name": "Otra tarea",
                        "state": "ready",
                        "caseId": "4",
                    }
                ],
            )
        )

        with pytest.raises(BonitaRespuestaInvalidaError, match="no coincide"):
            cliente.buscar_tarea_lista(4, "Generar lotes de necesidades")


def test_confirma_una_tarea_completada_en_el_archivo(cliente: ClienteBonita) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.get(f"{BASE_URL}/API/bpm/archivedHumanTask").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "id": "17",
                        "name": "Generar lotes de necesidades",
                        "state": "completed",
                        "caseId": "4",
                    }
                ],
            )
        )

        assert cliente.tarea_completada(4, "Generar lotes de necesidades") is True


def test_no_confirma_una_tarea_sin_archivo(cliente: ClienteBonita) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.get(f"{BASE_URL}/API/bpm/archivedHumanTask").mock(
            return_value=httpx.Response(200, json=[])
        )

        assert cliente.tarea_completada(4, "Generar lotes de necesidades") is False


def test_rechaza_una_tarea_archivada_que_no_coincide_con_el_filtro(
    cliente: ClienteBonita,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        _login(router)
        router.get(f"{BASE_URL}/API/bpm/archivedHumanTask").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "id": "17",
                        "name": "Otra tarea",
                        "state": "completed",
                        "caseId": "4",
                    }
                ],
            )
        )

        with pytest.raises(BonitaRespuestaInvalidaError, match="no coincide"):
            cliente.tarea_completada(4, "Generar lotes de necesidades")


@pytest.mark.parametrize("gravedad", list(GravedadEmergencia))
def test_el_contrato_admite_las_gravedades_del_dominio(
    gravedad: GravedadEmergencia,
) -> None:
    assert _contrato(gravedad=gravedad).a_payload()["gravedad"] == gravedad.value


@pytest.mark.parametrize("zona", ["", "   ", "z" * 256])
def test_el_contrato_rechaza_zonas_invalidas(zona: str) -> None:
    with pytest.raises(ValidationError):
        _contrato(zona=zona)
