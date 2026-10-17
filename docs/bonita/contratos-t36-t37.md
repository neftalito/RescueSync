# API y frontend de T36/T37 preparados para Studio

Implementación local de [T36](https://github.com/neftalito/RescueSyncAPI/issues/15)
y [T37](https://github.com/neftalito/RescueSyncAPI/issues/16), previa a la
adaptación del proceso en [T35](https://github.com/neftalito/RescueSyncAPI/issues/14).
Se analizaron el enunciado, `PLAN_IMPLEMENTACION_T35_T36_T37.md`,
`PLAN_CAMBIOS_BOS_1.5.md` y `REVISION_PLAN_CAMBIOS_BOS_1.5.md` del workspace.
Este documento fija el contrato implementado; las rutas y tablas de aquellos
planes eran propuestas. No se modificó el proceso ni se exportó un BAR nuevo.

## Artefactos y alcance verificado

`docs/RescueSync-1.4.bar` fue **reexportado desde Studio** con el proceso adaptado
a estos contratos (ver [proceso 1.4 adaptado](#proceso-14-adaptado-mínimo-entregable)).
Conserva el nombre y la versión `RescueSync 1.4`, por lo que no cambian
`BONITA_PROCESS_VERSION` ni el deploy. El `.bos` versionado es el fuente
**anterior** a la adaptación. El BAR 1.2 se retira del directorio de instalación
para que el instalador encuentre un único archivo.

| Artefacto | SHA-256 |
| --- | --- |
| BAR 1.4 adaptado | `17c40ad951efe942cd8837023746d9a67b771254697e10d7088c2f62f95884d9` |
| BOS original (previo a la adaptación) | `4bac9a49651f67f0d9dbf3a76cc367f0819969ecacdb0775582399c5453c17de` |

La API expone las once rutas técnicas y los comandos/pantallas de aplicación.
Bonita sigue siendo quien consulta ofertas, autentica nacionalmente y realiza
validación, compromiso, liberación y cierre. FastAPI no hace esas escrituras
nacionales. La API nacional existente no requiere cambios.

La comprobación de lectura del Runtime local del 16/10/2026 encontró conexión y
autenticación correctas, con `RescueSync 1.2` habilitado/resuelto. No encontró
una definición 1.4. No se instalaron procesos, modificaron casos ni migraron los
datos habituales como parte de esa comprobación. Las pruebas HTTP usan RESPX.

## Proceso 1.4 adaptado (mínimo entregable)

El 17/10/2026 se adaptó el diagrama en Studio y se verificó una E2E manual contra
el Runtime 10.4 y la API nacional local, ambos con Docker. El recorrido fue:

1. Alta de la emergencia y publicación de un lote PARAMEDICOS.
2. Oferta de una ONG habilitada.
3. Timer de 2 minutos.
4. Cierre, consolidado, `solicitudes-validacion`, validación nacional y perfiles (`vigente` y cubiertos).
5. Selección municipal.
6. Compromiso nacional y consulta de cada compromiso (bucle).
7. Confirmación y notificación.
8. Finalización de la ONG, liberación nacional y confirmación local.
9. Solicitud de cierre, cierre nacional y `/resolver`.

Resultado: emergencia `RESUELTA`, proyecto nacional `TERMINADO`, compromiso
`LIBERADO` y caso Bonita *completed* sin nodos fallidos.

Cambios del diagrama respecto del 1.4 original:

- Contratos con UUID en TEXT, según `contratos.py`; se agregan `operacionCompromisoId` y `participacionId`.
- `Validar Oferta` prepara la evaluación (`solicitudes-validacion`) antes de la validación nacional. `Guardar perfiles` envía la preparación completa y habilita la selección solo si `vigente` y `lotesCompatiblesCubiertos`.
- Nueva tarea `Consultar compromisos nacionales` (bucle estándar sobre `compromisoIds`) para enviar los detalles en `compromisos/confirmacion`.
- `Marcar como finalizada la tarea` es multi-instancia paralela sobre `participacionesIds`, con el iterador `participacionIdEsperada`. Libera la operación preparada por `GET /finalizaciones/{id}/liberaciones`.
- `Cerrar proyecto nacional` usa `GET /solicitudes-cierre/{id}` (clave, request y `operacionCierreId`).
- Todos los conectores hacia FastAPI envían las cabeceras de contexto de Bonita. Los scripts declaran `idEmergencia` como variable, no como índice de búsqueda. Las variables locales son persistentes, no transitorias.

Fuera del MVP: no se modelan tareas `Atender incidente de …` ni reintentos BPM.
Si un conector falla, la tarea queda *failed* (visible en el monitor) y la
recuperación por `/operaciones-nacionales/{id}/recuperacion` no encuentra
actividad. La liberación procesa `operaciones[0]`, ya que la API nacional crea un
compromiso por ONG y adjudicación. `tests/e2e/test_bonita_runtime.py` todavía
espera el camino 1.2 (`lotesCubiertos` → selección).

Para probarlo localmente:
- La cuenta `INTEGRACION` nacional se configura en `BONITA_NATIONAL_API_LOGIN`/`PASSWORD`.
- `NACIONAL_SISTEMA_ORIGEN` debe ser igual al sistema de esa cuenta.
- `BONITA_OFFER_WINDOW_MS=120000` acorta la ventana de ofertas.
- Las emergencias locales no deben reutilizar un `idEmergencia` que ya tenga proyecto nacional con otro caso.

## Contratos técnicos

Todas estas rutas usan el prefijo `/api/v1/emergencias/{idEmergencia}`. Exigen
`Authorization: Bearer <BONITA_CALLBACK_TOKEN>` y
`X-Bonita-Root-Process-Instance-Id: <caso raíz vinculado>`. Son credenciales
distintas del JWT nacional. Los cuerpos y respuestas usan camelCase.
Los GET técnicos y las consultas de usuario responden `Cache-Control: no-store`.
OpenAPI en `/docs` describe todos los campos y valida formatos, fechas con zona,
UUIDs y cantidades exactas de hasta tres decimales.

| Método y sufijo | Contrato y garantía |
| --- | --- |
| POST `/solicitudes-validacion` | `validacionId`, `convocatoriaId`, `intentoConvocatoria`. Devuelve `revision` y `huellaSnapshot`. Sólo la última ronda cerrada en evaluación; replay recupera la misma revisión. |
| POST `/perfiles-validacion` | Preparación anterior completa más `validacion`, respuesta íntegra T31. Devuelve `evaluadoEn`, **`vigente`**, `lotesCompatiblesCubiertos` y `cobertura`. |
| GET `/decisiones-evaluacion/{decisionId}` | Devuelve acción, motivo, evaluación/revisión/caso/ronda y, para REABRIR, `convocatoriaPreparada`. |
| GET `/adjudicaciones/{adjudicacionId}?version=1` | Devuelve `operacionCompromisoId`, `idempotencyKey`, `huellaRequest` y `compromiso`, cuerpo canónico de T32. |
| POST `/compromisos/confirmacion` | `adjudicacionId`, `adjudicacionVersion`, `operacionCompromisoId`, `huellaRequest`, `confirmacion` T32 y `compromisos`: lista de **respuestas completas** de GET nacional `/compromisos/{id}`. |
| POST `/notificar-adjudicacion` | `adjudicacionId`, `adjudicacionVersion`. Sólo entrega eventos que ya quedaron persistidos al confirmar. |
| POST `/operaciones-nacionales/{operacionId}/resultado` | `tipo`, `estadoIntegracion`, `httpStatus`, `codigoError`, `idempotencyKey` y `etapa` opcional. Sólo códigos seguros, sin cuerpos de error ni tokens. |
| GET `/finalizaciones/{finalizacionId}/liberaciones` | Devuelve `participacionId` y el conjunto completo de `operaciones`, cada una con `operacionId`, `compromisoId`, `idempotencyKey`, `request`. |
| POST `/compromisos/{compromisoId}/liberacion-confirmada` | `finalizacionId`, `participacionId`, `operacionId` local y `confirmacion` nacional completa. Sólo libera esa participante después de confirmar todos sus compromisos. |
| GET `/solicitudes-cierre/{solicitudId}` | Devuelve proyecto, caso, `operacionCierreId`, clave, request y los **booleanos** `liberacionesConfirmadas`/`operacionesInciertas`. |
| POST `/resolver` | `idEmergencia`, `estado: RESUELTA`, `proyectoNacionalId`, `solicitudCierreId`, `operacionCierreId`, `cierre` nacional completo. Conserva la primera fecha en replays. |

`operacionId` de las confirmaciones nacionales pertenece a la API nacional:
**no tiene por qué coincidir** con `operacionCompromisoId`, `operacionCierreId`
o la operación local de liberación. La correlación local usa además proyecto,
caso, emisor, adjudicación y el conjunto exacto de ítems y compromisos. No se
asocian ONGs por posición de una lista. En los detalles nacionales el ID del
compromiso se llama `id`, tal como devuelve su GET, no `compromisoId`.

Los errores son `401` (token), `403` (rol/organización/CSRF), `404` (referencia),
`409` (estado, correlación o contenido conflictivo), `422` (formato).
Un replay idéntico confirma el resultado anterior. Un resultado ya guardado no
puede cambiar de fecha/contenido bajo la misma identidad. Un replay histórico
puede devolver `vigente=false`: no habilita selección ni la compuerta BPM.

## Reglas de evaluación y selección

La revisión la asigna **FastAPI bajo lock**, no Bonita. Una nueva preparación
reemplaza la aplicabilidad de las anteriores, aunque llegue primero una
respuesta vieja. La huella SHA-256 utiliza JSON UTF-8 canónico, claves ordenadas,
separadores compactos, cantidades de tres decimales y todo el snapshot salvo
`ofertas[].estado`, que es una proyección mutable. El snapshot preparado queda
congelado localmente. No se completan asociaciones históricas con mappings actuales.

La recepción verifica exactamente ofertas/versiones/ítems/aportes y referencias
nacionales. Conserva diagnósticos legacy con aporte/recurso null y motivos
desconocidos, sin habilitarlos. PRINCIPAL/APOYO requieren capacidad, riesgo y
unidad publicados compatibles. `DISPONIBILIDAD_INSUFICIENTE` limita cantidad;
cualquier otro motivo impide seleccionar el aporte. Disponibilidad ausente no
prueba stock utilizable. Repeticiones contradictorias del stock se rechazan.

La cobertura calcula flujo máximo `origen → recurso → aporte → lote → destino`
en enteros de milésimas; comparte el presupuesto de cada recurso y admite
reasignaciones residuales para no producir falsos faltantes por un algoritmo
greedy. Las capacidades discretas sólo admiten cantidades enteras. Cada resultado
por lote pertenece al mismo plan global; la propuesta no es una reserva ni una
adjudicación automática. Límite: 1000 ofertas y 5000 aportes por evaluación.
El flujo bloqueante de Dinic usa recorridos iterativos; una medición local con
5000 recursos/aportes unitarios hacia un lote tomó 0,105 s (sólo el cálculo,
sin consultas ni HTTP). También se contrasta con búsqueda exhaustiva en redes
pequeñas para verificar optimalidad.

La selección manual también vuelve a comprobar máximos por aporte, recurso y
lote. Para cualquier selección incompleta se exige decisión
CONTINUAR_PARCIAL del centro asignado, sincronizada con su actividad BPM.
REABRIR copia los requerimientos a una nueva ronda; REFORMULAR crea lotes nuevos
en borrador. Ambas conservan la historia; el timer sigue a cargo de Bonita.

## Comandos y pantallas de aplicación

Las escrituras exigen sesión vigente, rol, organización activa y `X-CSRF-Token`.
El administrador no obtiene permisos de negocio por ser administrador.

| Ruta bajo la emergencia | Permiso y efecto |
| --- | --- |
| GET `/ofertas-validadas` | Municipio propietario o coordinador asignado; sólo el coordinador recibe diagnósticos no habilitados. |
| POST `/decision-evaluacion` | Coordinador: `decisionId`, `validacionId`, `revision`, `convocatoriaId`, `accion`, `motivo`. |
| POST `/adjudicaciones` | Municipio: `adjudicacionId`, `validacionId`, `revision`, `aportes: [{aporteId, cantidad}]`. UUID y contenido se conservan en un reintento. |
| GET `/adjudicaciones` | Seguimiento municipal/coordinador; ONG sólo ve sus participaciones confirmadas. |
| POST `/participaciones/{id}/finalizacion` | Representante de esa ONG; cuerpo vacío, devuelve la primera finalización. La líder de un consorcio no finaliza a otras miembros. |
| POST `/solicitudes-cierre` | Coordinador; cuerpo vacío. Exige todas las liberaciones confirmadas. |
| GET `/comandos-bonita` | Estado de despachos; ONG sólo consulta intenciones propias. |
| POST `/comandos-bonita/{id}/reintentar` | Reconciliar el despacho original con los permisos del rol que lo creó. |
| POST `/operaciones-nacionales/{id}/recuperacion` | Coordinador: `recuperacionId`, `accion` = REINTENTAR_MISMA_OPERACION o VOLVER_A_SELECCION. Esta última exige rechazo definitivo de compromiso. |

La pantalla `/emergencias/{id}/ejecucion` se abre desde las bandejas municipales
y coordinadoras o desde una oferta adjudicada/notificación de la ONG. Muestra
carga, vacíos, fallos, cantidades, competencia, faltantes, solicitudes pendientes,
finalización informada, liberación y cierre. Una respuesta HTTP exitosa al comando
significa **intención guardada**; sólo los callbacks nacionales confirman negocio.

Cada despacho persiste un claim de dos minutos y el ID exacto de actividad antes
del POST. No mantiene locks PostgreSQL durante HTTP. Un timeout consulta el
historial por ese ID fuente; no toma otra tarea del mismo nombre como evidencia.
La ausencia de una actividad correlacionada deja ERROR recuperable sin borrar la
intención. Compromisos inciertos bloquean otra selección; un rechazo definitivo
HTTP 409 sin incertidumbre previa permite revisar la selección con otra identidad.

## Cambios obligatorios en Studio antes de ejecutar el recorrido completo

1. Partir del BOS conservado y exportar una versión nueva, después de corregir
   los hallazgos de `REVISION_PLAN_CAMBIOS_BOS_1.5.md`. No editar el BAR como ZIP.
2. **Identidades nuevas locales:** evaluaciones, decisiones, adjudicaciones,
   participaciones, finalizaciones, solicitudes y operaciones usan UUID. Los IDs
   existentes de emergencia/ronda/oferta/ítem/aporte/ONG siguen siendo enteros.
   Esta decisión evita colisiones en reintentos; reemplaza los INTEGER propuestos
   para entidades nuevas por TEXT con formato UUID en contratos/variables Studio.
3. `Evalua situacion`: `accionSeleccionada` TEXT y `decisionCoordinadorId` TEXT.
   `Seleccionar ofertas validadas`: `adjudicacionId` TEXT,
   `adjudicacionVersion` INTEGER, `convocatoriaId` INTEGER,
   `operacionCompromisoId` TEXT. Finalización: `participacionId`/`finalizacionId`
   TEXT. Cierre: `solicitudCierreId` TEXT. Los modelos tipados están en
   `backend/app/integrations/bonita/contratos.py`.
4. La correlación de decisiones/selecciones consulta el escalar de caso
   `intentoConvocatoria`. Cada instancia de finalización debe exponer el escalar
   **local** `participacionIdEsperada` TEXT, inicializado por el proceso antes de
   recibir el contrato. El backend consulta `/API/bpm/activityVariable/{id}/participacionIdEsperada`;
   no usa un Map Java ni una afirmación del navegador como prueba de identidad.
5. Incidentes: nombres `Atender incidente de compromiso`,
   `Atender incidente de liberación`, `Atender incidente de cierre`; variable
   local TEXT `operacionIdEsperada`, contrato `accionIncidente`/`operacionId` TEXT.
   Guardar `etapa` y retomar el paso exacto: COMPROMISO_NACIONAL,
   CONSULTA_COMPROMISOS, CONFIRMACION_LOCAL, NOTIFICACION, LIBERACION_NACIONAL,
   CONFIRMACION_LIBERACION, CIERRE_NACIONAL o RESOLVER. Conservar body, claves,
   resultado nacional y detalles ya obtenidos. No volver al POST nacional para
   recuperar un callback local. Para errores previos a preparar una operación
   (cierre/snapshot/preparación/validación/perfiles/decisión), mantener el incidente
   de integración del plan con sus destinos PREPARACION y DECISION incluidos.
6. La preparación toma la revisión devuelta por FastAPI. Exigir `vigente == true`
   y correlación completa después de `/perfiles-validacion` antes de publicar
   `lotesCompatiblesCubiertos`. `operacionesInciertas` es booleano: comparar con
   `false`, no con `0`. Conservar conjunto completo de liberaciones por ONG.
7. Separar preparación, llamada nacional y confirmación local en estados
   persistentes recuperables. No confiar en IGNORE para convertir una excepción
   de transporte en éxito. Limpiar estados/salidas antes de llamar y configurar
   los fallos HTTP que el BPM clasifica para que produzcan salidas normales.
8. Resolver la recuperación por participante y la serialización de la
   multiinstancia señaladas en la revisión; no dar una participante por terminada
   cuando falta una liberación o callback. Mantener el resultado nacional para
   recuperar sólo el callback después de un reinicio.
9. La tarea inicial `Generar lotes de necesidades` conserva contrato vacío en
   1.4. Si el nuevo export agrega ronda/número como propone el plan, adaptar
   `publicacion_bonita.py` en ese mismo cambio. Los casos 1.2/1.4 no adquieren los
   contratos nuevos al instalar otra versión.

Los endpoints de actividad/contrato están documentados por el proveedor:
[interacción con tareas](https://documentation.bonitasoft.com/bonita/next/applications/ui-builder/common-apis-to-use)
y [contratos y contexto](https://documentation.bonitasoft.com/bonita/2024.3/data/contracts-and-contexts).

## Configuración, migración y pruebas

`BONITA_PROCESS_VERSION` apunta por defecto al artefacto conservado 1.4. El deploy
inyecta sus nueve parámetros, incluidos `nationalApiUser`, `nationalApiPassword`
y `maxReintentosIntegracion`. Completar en el entorno
`BONITA_NATIONAL_API_LOGIN`/`BONITA_NATIONAL_API_PASSWORD` con la cuenta técnica de
integración del emisor. Ambos valores se ocultan en errores/logs de comparación;
no reutilizar el callback token ni credenciales de una ONG. El despliegue modifica
los parámetros sólo en memoria, sin reescribir el BAR fuente.
`BONITA_NATIONAL_API_BASE_URL=http://host.docker.internal:8001` no lleva `/api/v1`;
el servicio bonita tiene `host-gateway`. Las bases permanecen separadas.

Aplicar `alembic upgrade head` antes de usar las rutas nuevas. La revisión
`20261016_0015` agrega nueve tablas locales: evaluación, comando, decisión,
operación, adjudicación, participación, compromiso, finalización y cierre.
Los perfiles/cobertura/selecciones se guardan como JSONB tipado validado, con FKs
a sus agregados y triggers de inmutabilidad. No se modifica el esquema nacional.
Las cantidades adjudicadas están en el request nacional canónico como strings
exactos; no se usa aritmética float para cobertura o selección.

Preparación de la base descartable y pruebas rápidas:

```bash
docker compose exec db createdb -U rescuesync rescuesync_t36_t37_test
docker compose exec -e APP_ENV=test -e POSTGRES_DB=rescuesync_t36_t37_test backend alembic upgrade head

docker compose exec -e APP_ENV=test -e POSTGRES_DB=rescuesync_t36_t37_test backend \
  pytest tests/test_ejecucion_nacional.py tests/test_evaluacion_concurrencia.py \
  tests/test_despacho_ejecucion.py tests/test_cobertura_validada.py

docker compose exec frontend npm test -- --run src/pages/EjecucionPage.test.tsx
```

También se verifican la suite completa, Ruff, lint/typecheck/build frontend y el
contrato del BAR. Las pruebas de concurrencia usan conexiones/transacciones
independientes, no SQLite. La E2E Runtime de T35 debe ejecutar timer corto real,
las dos APIs y al menos dos ONGs después de adaptar/exportar Studio, incluyendo
stock tomado por otra emergencia, timeout posterior al commit, callback perdido,
reinicio entre liberación y confirmación y cierre prematuro. No cerrar los issues
T35/T36/T37 como E2E completa basándose sólo en estas pruebas locales.
