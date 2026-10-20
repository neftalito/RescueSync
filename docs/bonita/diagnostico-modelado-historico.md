# Diagnóstico histórico del modelado de Bonita

## Diagnóstico del modelo original y registro de decisiones

**Versión analizada:** Bonita Studio 10.4.0  
**Proceso:** `RescueSync`  
**Prioridad analizada:** Entrega 2 — integración inicial con Bonita

> **Estado actual (17/09/2026).** Este documento conserva el diagnóstico hecho
> sobre el `.bos` original, que ya se eliminó por estar desactualizado. La
> referencia vigente es [`docs/RescueSync-1.5.bar`](../RescueSync-1.5.bar). Esa versión incorpora el
> contrato validado (incluida la gravedad `CRITICA`), las variables, el índice
> `idEmergencia`, los actores funcionales, las compuertas evaluadas por script,
> el timer por fecha y los conectores autenticados hacia FastAPI. Se verificó
> contra el Runtime real. Este archivo conserva las decisiones y brechas del
> modelo anterior; no es la guía operativa vigente. Para trabajar con la versión
> actual, consultar [Proceso BPM](./proceso-bpm.md),
> [Cliente HTTPX](./cliente-httpx.md),
> [Despliegue y operación](./despliegue-y-operacion.md) y
> [Callbacks](./callbacks.md).

## 1. Objetivo y alcance

Este documento registra el diagnóstico inicial y la guía usada para integrar el
proceso de forma segura y trazable. El proyecto fuente `.bos` analizado no está
disponible en el repositorio actual.

El análisis se basa en:

- [`Trabajo integrador 2026.pdf`](<../Trabajo integrador 2026.pdf>).
- [`Grooming Etapa 2.pdf`](<../Grooming Etapa 2.pdf>).
- `rescuesync.bos` original, hoy reemplazado por [`RescueSync-1.5.bar`](../RescueSync-1.5.bar).
- [`Descripción textual del flujo BPM.pdf`](<../Descripción textual del flujo BPM.pdf>), como descripción complementaria del modelo existente.

La prioridad inmediata es la Entrega 2: registrar una emergencia en la base
local, iniciar una instancia de Bonita y enviar como mínimo
`idEmergencia`, `gravedad` y `zona`. La integración con el Sistema Nacional,
su JWT y el bloqueo o liberación de recursos corresponde a la Entrega 3 y se
identifica expresamente como trabajo posterior.

## 2. Conclusión del diagnóstico original

El `.bos` analizado inicialmente representaba correctamente el recorrido general del negocio,
pero todavía es principalmente un modelo visual. No está preparado para una
integración ejecutable porque carece de contratos, variables, condiciones,
conectores y configuración de actores.

El modelo contiene:

- Un pool llamado `RescueSync`.
- Las lanes Operador Municipal, Centro Coordinador Regional, ONG y Red Nacional.
- El ciclo general desde el registro hasta el cierre de la emergencia.
- Un timer de ofertas configurado con una duración de dos horas.
- Los caminos alternativos para reabrir la convocatoria, reformular lotes o
  continuar con cobertura parcial.

Sin embargo, se encontraron las siguientes brechas:

| Elemento                   | Estado actual                         | Consecuencia                                                                          |
| -------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------- |
| Contrato de inicio         | Vacío                                 | FastAPI no tiene un contrato definido para iniciar el proceso.                        |
| Variables de proceso       | No existen                            | Bonita no conserva `idEmergencia`, `gravedad` ni `zona`.                              |
| Contratos de tareas        | Vacíos                                | Las decisiones humanas no pueden enviar datos al proceso.                             |
| Compuertas                 | Condiciones vacías                    | Las rutas alternativas no pueden decidirse con datos reales.                          |
| Tareas de servicio         | Sin conectores                        | No realizan llamadas a FastAPI ni al Sistema Nacional.                                |
| Timer de ofertas           | Configurado, pero sin salida propia   | Su vencimiento no conduce automáticamente a la consolidación.                         |
| Actores                    | Solo `Employee actor` y grupo `/acme` | Las tareas no representan los roles reales del proyecto.                              |
| Formularios Bonita         | Referencias vacías                    | No hay interfaz Bonita para ejecutar tareas, aunque React será la interfaz principal. |
| Índices de búsqueda        | Vacíos                                | No existe correlación por `idEmergencia`.                                             |
| Configuración por ambiente | Vacía                                 | No hay URL, timeout ni mapeos específicos para Qualification o Production.            |

También existen dos problemas de diseño:

1. La emergencia se registraría dos veces. El grooming establece que FastAPI
   persiste la emergencia y luego inicia Bonita, pero el primer nodo actual
   vuelve a pedir `Registrar Emergencia`.
2. El orden de integración de ofertas está invertido. El modelo ejecuta
   `Validar Oferta` antes de `Solicitar ofertas consolidadas`, aunque el trabajo
   exige primero recuperar las ofertas de PostgreSQL y luego enviarlas al
   Sistema Nacional.

## 3. Responsabilidades de cada componente

Para evitar datos duplicados o responsabilidades ambiguas se debe conservar
esta separación:

- **React:** presenta formularios y estados al usuario. Nunca llama directamente
  a Bonita.
- **FastAPI:** autentica y autoriza, persiste el dominio en PostgreSQL y actúa
  como adaptador de la API REST de Bonita.
- **PostgreSQL local:** es la fuente de verdad de emergencias, lotes, ofertas,
  borradores y versiones.
- **Bonita:** administra el estado del proceso, las esperas, el timer y los
  caminos alternativos.
- **Sistema Nacional:** valida capacidades y bloquea o libera recursos desde la
  Entrega 3. No recibe borradores de ofertas.

No se recomienda crear en Bonita un Business Data Model que duplique
emergencias, lotes y ofertas. Bonita solo necesita identificadores, variables de
orquestación y resultados mínimos para decidir el recorrido.

## 4. Flujo objetivo recomendado

```text
FastAPI registra la emergencia en PostgreSQL
        │
        └── Inicia una instancia RescueSync en Bonita
                │
Inicio
  → Recibir alerta
  → Esperar que el Coordinador prepare y publique los lotes
  → Notificar apertura de convocatoria
  → Esperar el vencimiento del timer
  → Cerrar convocatoria y obtener ofertas consolidadas desde FastAPI
  → Validar ofertas en el Sistema Nacional                 [Entrega 3]
  → Persistir resultados de validación en FastAPI          [Entrega 3]
  → ¿Lotes cubiertos?
      ├── Sí → Seleccionar ofertas validadas
      └── No → Evaluar situación
                 ├── Reabrir convocatoria
                 ├── Reformular lotes
                 └── Continuar con cobertura parcial
  → Notificar adjudicación
  → Comprometer recursos en el Sistema Nacional            [Entrega 3]
  → Esperar finalización de actividades
  → Liberar recursos                                       [Entrega 3]
  → Marcar emergencia resuelta
  → Fin
```

## 5. Implementación paso a paso en Bonita Studio

### Paso 1. Crear una nueva versión del proceso

Abrir el proyecto con Bonita Studio 10.4.0 y crear una nueva versión del pool:

- Nombre: `RescueSync`.
- Versión vigente: `1.2`.
- Descripción: indicar que incorpora el contrato de integración inicial.

No se debe reemplazar una versión que pueda tener instancias activas. Durante
las pruebas conviene mantener una sola versión habilitada para evitar que el
backend inicie accidentalmente una definición anterior.

### Paso 2. Definir el contrato de instanciación

Seleccionar el pool y abrir:

```text
Execution → Contract → Inputs
```

Agregar:

| Entrada        | Tipo Bonita     | Obligatoria | Etapa     |
| -------------- | --------------- | ----------: | --------- |
| `idEmergencia` | `LONG` o `TEXT` |          Sí | Entrega 2 |
| `gravedad`     | `TEXT`          |          Sí | Entrega 2 |
| `zona`         | `TEXT`          |          Sí | Entrega 2 |
| `descripcion`  | `TEXT`          | Recomendado | Entrega 2 |
| `municipioId`  | `LONG` o `TEXT` | Recomendado | Entrega 2 |

El tipo de cada identificador debe coincidir con PostgreSQL. Si la clave local
es `bigint`, se debe usar `LONG`; si es UUID, se debe usar `TEXT`.

Agregar restricciones para comprobar:

- Que `idEmergencia` sea válido.
- Que `gravedad` pertenezca al enum acordado con FastAPI.
- Que `zona` no sea nula ni vacía.
- Que las longitudes máximas coincidan con Pydantic y PostgreSQL.
- Que `municipioId` sea válido cuando forme parte del contrato.

Los nombres y tipos del contrato deben quedar acordados antes de implementar el
cliente HTTPX. Un cambio posterior obliga a generar externamente un `.bar`
nuevo y modificar FastAPI, los mocks RESPX y las pruebas E2E.

### Paso 3. Crear las variables del pool

En:

```text
Data → Pool variables
```

Crear las variables persistentes:

```text
idEmergencia
gravedad
zona
descripcion
municipioId
```

Inicializar cada variable con su entrada correspondiente del contrato. El
contrato valida los datos de entrada; las variables permiten utilizarlos durante
el resto de la instancia.

Agregar también las variables de control del flujo:

| Variable              | Tipo    | Uso                                            |
| --------------------- | ------- | ---------------------------------------------- |
| `lotesCubiertos`      | Boolean | Resultado del cálculo de cobertura.            |
| `accionCoordinador`   | Text    | `REABRIR`, `REFORMULAR` o `CONTINUAR_PARCIAL`. |
| `ejecucionTerminada`  | Boolean | Decide el cierre de la ejecución.              |
| `fechaCierreOfertas`  | Date    | Momento en que debe cerrar la convocatoria.    |
| `intentoConvocatoria` | Integer | Trazabilidad de reaperturas.                   |

Variables previstas para etapas posteriores:

```text
ofertasConsolidadasJson
resultadosValidacionJson
ofertasSeleccionadasJson
proyectoNacionalId
ultimoErrorIntegracion
```

No se deben guardar contraseñas, JWT ni secretos dentro de variables de proceso.

### Paso 4. Configurar correlación por emergencia

Completar uno de los índices de búsqueda del pool:

```text
Nombre: idEmergencia
Valor:  idEmergencia
```

Esto permitirá localizar una instancia usando el identificador local. Es
especialmente importante cuando FastAPI recibe un timeout durante la
instanciación: Bonita podría haber creado el caso aunque el backend no haya
recibido la respuesta.

El índice facilita la reconciliación, pero no garantiza unicidad. FastAPI debe
seguir evitando inicios duplicados mediante el estado de sincronización local.

### Paso 5. Corregir el inicio del proceso

La opción recomendada es eliminar `Registrar Emergencia` como tarea humana:

```text
Inicio → Recibir Alerta → Generar lotes de necesidades
```

La emergencia ya fue registrada cuando FastAPI inició la instancia. El contrato
de instanciación representa la entrada de esa emergencia al proceso.

Si se conserva el nodo por claridad visual, debe convertirse en una actividad
automática denominada, por ejemplo, `Inicializar caso de emergencia`, sin pedir
datos nuevamente al usuario.

### Paso 6. Vincular la publicación local con la tarea de Bonita

`Generar lotes de necesidades` puede seguir siendo una tarea humana que
representa la espera del proceso mientras el Coordinador trabaja en React.

La secuencia debe ser:

1. El Coordinador crea o edita lotes en PostgreSQL.
2. `POST /api/v1/emergencias/{id}/publicar` verifica que exista al menos un lote
   válido y publica la convocatoria en una transacción local.
3. Después del commit, FastAPI localiza la tarea Bonita del caso.
4. FastAPI ejecuta esa tarea mediante la API REST de Bonita.
5. Bonita continúa hacia la apertura de la ventana de ofertas.

El contrato de la tarea puede permanecer vacío si completar la tarea solo
representa la confirmación. Si Bonita necesita datos para el timer, se pueden
agregar:

```text
fechaPublicacion
fechaCierreOfertas
cantidadLotes
```

Bonita no necesita recibir el detalle completo de los lotes porque ese detalle
permanece en PostgreSQL.

### Paso 7. Rehacer la ventana de ofertas

El timer actual está unido a una única tarea `Generar ofertas`. Esa estructura
no representa correctamente a varias ONGs registrando ofertas independientes y,
además, el timer no tiene una salida de excepción.

La alternativa más simple es reemplazar esa sección por:

```text
Enviar notificación a ONGs
  → Timer intermedio de espera
  → Cerrar y consolidar ofertas
```

El timer debe:

- Comenzar cuando la convocatoria queda publicada.
- Usar dos horas como valor inicial del negocio.
- Poder usar una duración menor en Qualification para pruebas.
- Avanzar automáticamente al vencerse.
- Ser administrado exclusivamente por Bonita.

También se recomienda eliminar la combinación actual de la compuerta inclusiva
`notificarYEsperar` con la compuerta paralela `ofertasListas`. Una compuerta
inclusiva puede abrir solo una rama, mientras que una paralela espera todas las
ramas y puede dejar la instancia bloqueada. Una secuencia simple es suficiente;
si realmente se necesitan ramas paralelas, se debe usar una compuerta paralela
tanto para dividir como para unir.

### Paso 8. Reordenar consolidación y validación

Al vencer el timer debe ocurrir:

```text
Timer vencido
  → Cerrar convocatoria local
  → Solicitar ofertas consolidadas a FastAPI
  → Validar ofertas consolidadas en el Sistema Nacional
  → Guardar resultados de validación en FastAPI
  → Calcular cobertura
  → ¿Lotes cubiertos?
```

Para evitar que una oferta ingrese entre el cierre y la consulta, el backend
debería cerrar la convocatoria y construir el consolidado dentro de una
transacción. Puede exponerse una operación interna idempotente para Bonita.

La consulta debe devolver únicamente ofertas presentadas y sus versiones
vigentes. No debe incluir borradores.

El conector al Sistema Nacional, su JWT y el bloqueo de recursos quedan para la
Entrega 3. En la Entrega 2 alcanza con dejar clara su ubicación en el proceso.

### Paso 9. Completar las condiciones de las compuertas

#### `Lotes cubiertos?`

```text
lotesCubiertos == true  → Seleccionar ofertas validadas
default                 → Evaluar situación
```

#### `accionCoordinador`

```text
accionCoordinador == "REABRIR"     → Reabrir/publicar convocatoria
accionCoordinador == "REFORMULAR"  → Generar lotes
default: "CONTINUAR_PARCIAL"       → Seleccionar ofertas validadas
```

La tarea `Evalúa situación` debe recibir `accionCoordinador` mediante un
contrato que solo permita esos tres valores.

#### `termino?`

```text
ejecucionTerminada == true → Marcar proyecto terminado
default                     → Continuar monitoreo
```

Ninguna salida de una compuerta debe quedar con una condición vacía salvo la
ruta marcada explícitamente como predeterminada.

### Paso 10. Configurar actores

Reemplazar `Employee actor` y el grupo de ejemplo `/acme` por actores
funcionales:

```text
Iniciador API
Operador Municipal
Coordinador Regional
Representante ONG
```

La cuenta técnica utilizada por FastAPI debe pertenecer al actor iniciador y
tener permisos para iniciar el proceso y operar las tareas que la aplicación
complete mediante REST.

El RBAC local no debe delegarse en Bonita. FastAPI debe volver a autenticar y
autorizar cada operación. El rol Auditor/Directivo puede quedar preparado en la
aplicación sin agregar una tarea BPM durante la Entrega 2.

### Paso 11. Agregar conectores gradualmente

Las tareas de servicio actuales no tienen implementación. Se deben configurar
de acuerdo con esta secuencia:

| Actividad                       | Destino                  | Etapa                                  |
| ------------------------------- | ------------------------ | -------------------------------------- |
| Solicitar ofertas consolidadas  | FastAPI local            | Integración posterior al inicio básico |
| Notificar apertura/adjudicación | Backend o servicio local | Posterior                              |
| Validar ofertas                 | Sistema Nacional con JWT | Entrega 3                              |
| Comprometer o bloquear recursos | Sistema Nacional         | Entrega 3                              |
| Informar finalización           | Sistema Nacional         | Entrega 3                              |
| Liberar recursos                | Sistema Nacional         | Entrega 3                              |
| Marcar emergencia resuelta      | FastAPI local            | Cierre del flujo                       |

Cada conector debe tener:

- URL formada a partir de parámetros de ambiente.
- Timeout de conexión y lectura explícitos.
- `Content-Type: application/json`.
- Validación del código HTTP.
- Validación de la estructura de la respuesta.
- Mapeo explícito de salidas hacia variables de proceso.
- Manejo de fallos sin exponer credenciales ni respuestas sensibles.

### Paso 12. Configurar ambientes y secretos

Agregar parámetros no sensibles como:

```text
backendBaseUrl
connectTimeoutMs
readTimeoutMs
ventanaOfertasMs
nationalApiBaseUrl        [Entrega 3]
```

Qualification y Production deben proporcionar valores propios. Por ejemplo,
la URL desde Bonita hacia FastAPI depende de dónde se ejecute el Runtime:

- Bonita Studio en el host: normalmente `http://localhost:8000`.
- Bonita en Compose: `http://backend:8000`.

Las credenciales, claves internas y JWT no deben guardarse en el proyecto de
Studio ni en Git. Deben configurarse como secretos del ambiente o directamente
en el Runtime.

### Paso 13. Incorporar manejo de errores

Para cada borde externo se debe definir:

- Qué errores son reintentables.
- Qué errores requieren intervención manual.
- Cómo se registra un mensaje seguro para diagnóstico.
- Cómo se evita repetir operaciones con efectos externos.
- Qué ruta toma el proceso cuando la integración no está disponible.

Los GET idempotentes pueden reintentarse de forma controlada. Los POST que
inician procesos, bloquean recursos o generan compromisos no deben reintentarse
ciegamente: necesitan una clave idempotente o una consulta de reconciliación.

### Paso 14. Construir y desplegar

Una vez configurado el proceso:

1. Ejecutar la validación del diagrama en Bonita Studio.
2. Corregir todos los errores de contratos, actores, expresiones y conectores.
3. Probar el proceso con formularios autogenerados.
4. Construir el artefacto `.bar`.
5. Instalarlo en el Runtime.
6. Configurar mapeos de actores y parámetros.
7. Habilitar la definición del proceso.
8. Verificar que el nombre y la versión coincidan con
   `BONITA_PROCESS_NAME` y `BONITA_PROCESS_VERSION` del ambiente.

El Runtime no importa directamente proyectos `.bos`: requiere el `.bar`
desplegable. El proyecto fuente utilizado para 1.2 no está versionado aquí.

## 6. Integración desde FastAPI

FastAPI debe concentrar toda la comunicación con Bonita:

1. Iniciar sesión contra Bonita.
2. Mantener las cookies de sesión.
3. Obtener el token `X-Bonita-API-Token`.
4. Enviar ese token como header en las operaciones que modifican estado.
5. Localizar la definición habilitada de `RescueSync`.
6. Iniciar la instancia mediante:

```text
POST /bonita/API/bpm/process/{processDefinitionId}/instantiation
```

7. Enviar un payload compatible con el contrato:

```json
{
  "idEmergencia": 123,
  "gravedad": "ALTA",
  "zona": "Zona norte",
  "descripcion": "Inundación con familias evacuadas",
  "municipioId": 7
}
```

8. Guardar el identificador de instancia devuelto en la emergencia local.

La emergencia debe persistirse antes de depender de la disponibilidad de
Bonita. El modelo local debería distinguir:

```text
PENDIENTE
VINCULADA
ERROR
RESULTADO_DESCONOCIDO
```

Secuencia recomendada:

1. Crear la emergencia con estado de sincronización `PENDIENTE`.
2. Confirmar la transacción local.
3. Intentar iniciar Bonita.
4. Si responde correctamente, guardar el ID y pasar a `VINCULADA`.
5. Si hay un rechazo definitivo del contrato, guardar `ERROR` y un mensaje
   seguro.
6. Si ocurre un timeout después de enviar el POST, usar
   `RESULTADO_DESCONOCIDO` y buscar por `idEmergencia` antes de reintentar.

## 7. Pruebas necesarias

### Pruebas mínimas de la Entrega 2

- El `.bar` se construye sin errores.
- La definición se instala y queda habilitada.
- Un payload válido inicia una única instancia.
- La respuesta permite guardar `caseId` o `processInstanceId`.
- Las variables de la instancia contienen los valores enviados.
- La instancia llega a la tarea esperada del Coordinador.
- Un contrato incompleto devuelve un error controlado.
- Un fallo de autenticación no filtra credenciales.
- Un timeout conserva la emergencia local y no provoca un reintento ciego.
- La reconciliación por `idEmergencia` evita duplicados.

### Pruebas posteriores del flujo BPM

- El timer avanza automáticamente al vencerse.
- No se aceptan ofertas después del cierre.
- Con cobertura completa se llega a selección.
- Sin cobertura se llega a `Evalúa situación`.
- Cada acción del Coordinador toma su ruta correspondiente.
- Un fallo del conector queda visible y recuperable.
- La liberación de recursos solo ocurre al finalizar el proyecto.

Las pruebas automatizadas de FastAPI deben simular Bonita con RESPX. El Runtime
real se reserva para pruebas manuales o E2E controladas.

## 8. Mínimo indispensable para comenzar la Entrega 2

Antes de implementar el cliente Bonita en FastAPI debe quedar terminado:

- [ ] Nueva versión del proceso `RescueSync`.
- [ ] Contrato de instanciación estable.
- [ ] Variables `idEmergencia`, `gravedad` y `zona`.
- [ ] Mapeo de entradas del contrato hacia variables.
- [ ] Índice de búsqueda por `idEmergencia`.
- [ ] Eliminación o automatización de `Registrar Emergencia`.
- [ ] Actor iniciador y actor Coordinador configurados.
- [ ] Primera tarea alcanzable después de iniciar la instancia.
- [ ] Condiciones de compuertas definidas.
- [ ] Timer con una salida ejecutable y verificable.
- [ ] Diagrama validado y `.bar` desplegable.
- [ ] Definición habilitada y localizable por nombre y versión.
- [ ] Prueba manual de instanciación con el payload acordado.

No son bloqueantes para comenzar la Entrega 2:

- Formularios personalizados de Bonita, porque React es la interfaz principal.
- Integración JWT con el Sistema Nacional.
- Validación nacional de competencias.
- Bloqueo y liberación nacional de recursos.
- Dashboard de Auditor/Directivo.

## 9. Referencias técnicas

- [Contratos y contextos de Bonita](https://documentation.bonitasoft.com/bonita/2024.3/data/contracts-and-contexts).
- [Eventos y temporizadores](https://documentation.bonitasoft.com/bonita/2025.1/process/events).
- [Conectores REST](https://documentation.bonitasoft.com/bonita/2024.1/process/rest-connector).
- [Endpoints comunes de procesos](https://documentation.bonitasoft.com/bonita/next/applications/ui-builder/common-apis-to-use).
- [Protección CSRF de la API REST](https://documentation.bonitasoft.com/bonita/2024.2/security/csrf-security).
