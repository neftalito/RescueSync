# Cliente HTTPX reutilizable de Bonita

`ClienteBonita`, ubicado en `backend/app/integrations/bonita/cliente.py`, es el
adaptador tipado entre FastAPI y la API REST de Bonita. Centraliza el pool HTTP,
la sesión técnica, cookies, token CSRF, timeouts, validación de respuestas y
traducción de errores.

El frontend nunca utiliza este cliente ni llama directamente a Bonita.

## Ciclo de vida en FastAPI

El `lifespan` de `backend/app/main.py` crea una sola instancia para toda la
aplicación y cierra su pool al apagarla. Las rutas obtienen esa instancia con
`ClienteBonitaDep`; el siguiente fragmento pertenece al health check existente:

```python
from app.api.dependencies import ClienteBonitaDep


@router.get("/bonita", response_model=HealthResponse)
def bonita_health(cliente: ClienteBonitaDep) -> HealthResponse:
    cliente.obtener_proceso_habilitado()
    return HealthResponse(service="bonita")
```

No se crea un `ClienteBonita` o un `httpx.Client` por petición y la ruta no
llama a `close()` sobre el cliente inyectado. Sus métodos son sincrónicos, por lo
que las rutas que los invocan se declaran con `def` para ejecutarse en el
threadpool de FastAPI.

La dependencia resuelve el recurso compartido; la transacción, la persistencia
y la orquestación pertenecen a un servicio o caso de uso que recibe un
`ClienteBonita`.

## Iniciar una instancia

El caso de uso primero resuelve la definición habilitada por nombre y versión,
construye el contrato tipado y luego inicia el caso:

```python
from app.db.models.enums import GravedadEmergencia
from app.integrations.bonita.cliente import ClienteBonita
from app.integrations.bonita.contratos import ContratoInicioProceso


def iniciar_caso(cliente: ClienteBonita, emergencia_id: int) -> int:
    proceso = cliente.obtener_proceso_habilitado()
    contrato = ContratoInicioProceso(
        idEmergencia=emergencia_id,
        gravedad=GravedadEmergencia.ALTA,
        zona="Zona norte",
        descripcion="Inundación con familias evacuadas",
        municipioId=7,
    )
    return cliente.iniciar_instancia(proceso.id, contrato).case_id
```

El caso de uso real también delimita la transacción local y persiste el
`caseId`, el estado de sincronización y el último error seguro. El ID numérico de
la definición no se configura: se resuelve mediante `BONITA_PROCESS_NAME` y
`BONITA_PROCESS_VERSION`.

La instanciación admite HTTP `200` y `201`: Bonita Runtime 10.4.0 devuelve `200`,
aunque su especificación OpenAPI 1.0.6 declara `201`.

## Operaciones disponibles

| Método | Uso |
| --- | --- |
| `obtener_proceso_habilitado()` | Resuelve y valida la definición configurada. |
| `iniciar_instancia(proceso_id, contrato)` | Inicia el proceso y devuelve el `caseId`. |
| `buscar_casos_por_emergencia(proceso_id, id_emergencia)` | Busca casos activos por el índice `idEmergencia`. |
| `buscar_tarea_lista(case_id, nombre)` | Localiza una tarea humana pendiente por caso y nombre. |
| `ejecutar_tarea(tarea_id, usuario_actor)` | Asigna y completa una tarea cuyo contrato está vacío. |

`ejecutar_tarea()` busca al usuario de Bonita indicado, asigna la tarea y luego
la ejecuta. La cuenta técnica no reemplaza al miembro del actor funcional.

## Sesión y concurrencia

El cliente conserva las cookies de sesión y agrega `X-Bonita-API-Token` a cada
petición. Cuando Bonita responde `401`, invalida el token rechazado, renueva la
sesión una sola vez y repite la petición. Un lock evita renovaciones simultáneas
desde distintos hilos.

Los timeouts se configuran con:

- `BONITA_CLIENT_CONNECT_TIMEOUT_SECONDS`;
- `BONITA_CLIENT_READ_TIMEOUT_SECONDS`.

Las credenciales técnicas provienen de `BONITA_USERNAME` y `BONITA_PASSWORD` y
nunca deben registrarse.

## Errores y reintentos

| Excepción | Significado | Acción esperada |
| --- | --- | --- |
| `BonitaNoDisponibleError` | No se confirmó una operación segura de repetir. | Registrar un error seguro y permitir reintento. |
| `BonitaResultadoDesconocidoError` | Bonita pudo aplicar una operación con efectos antes de perderse la respuesta. | Reconciliar antes de cualquier reintento. |
| `BonitaOperacionRechazadaError` | Bonita procesó y rechazó la operación. | Corregir estado o contrato; repetir igual volverá a fallar. |
| `BonitaCredencialesError` | Bonita rechazó la cuenta técnica o la sesión renovada. | Revisar la configuración. |
| `BonitaProcesoNoDisponibleError` | La definición no existe, no está resuelta o no está habilitada. | Revisar versión y despliegue. |
| `BonitaRespuestaInvalidaError` | La respuesta no coincide con los modelos locales. | Revisar Runtime, `.bar` y contratos Pydantic. |

No se reintenta ciegamente `iniciar_instancia()` ni `ejecutar_tarea()` después
de `BonitaResultadoDesconocidoError`. Para una instanciación se consulta primero
`buscar_casos_por_emergencia()`. El índice ayuda a correlacionar, pero no
garantiza unicidad.

## Uso fuera de FastAPI

En una prueba E2E o herramienta controlada, quien crea el cliente administra su
ciclo de vida:

```python
from app.core.config import get_settings
from app.integrations.bonita.cliente import ClienteBonita, ConfiguracionBonita

with ClienteBonita(
    ConfiguracionBonita.desde_settings(get_settings())
) as cliente:
    proceso = cliente.obtener_proceso_habilitado()
```

Este patrón no se usa dentro de una ruta: allí corresponde `ClienteBonitaDep`.

## Pruebas automatizadas

Las pruebas unitarias y de integración HTTP usan RESPX, sin depender de un
Runtime real. Deben cubrir sesión, CSRF, renovación tras `401`, timeouts,
respuestas inválidas, contrato rechazado y resultado incierto.

En pruebas de rutas, la dependencia se reemplaza sin modificar producción:

```python
from app.api.dependencies import obtener_cliente_bonita

app.dependency_overrides[obtener_cliente_bonita] = lambda: cliente_doble
```

El override se elimina al terminar cada prueba para no contaminar otros casos.
El Runtime real se reserva para la [prueba E2E controlada](./pruebas-e2e.md).
