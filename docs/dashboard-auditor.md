# Dashboard del auditor/directivo

El usuario con rol `AUDITOR_DIRECTIVO` ingresa a `/` y encuentra el panel global
de indicadores. Es de solo lectura y abarca todos los municipios. Los otros
roles, incluido `ADMINISTRADOR`, no pueden consultar sus endpoints. El seed local
incluye `auditor@rescuesync.org` / `auditor123`; el administrador también puede
crear cuentas auditoras sin organización.

## Alcance respecto del trabajo integrador

La página 3 de `Trabajo integrador 2026.pdf` pide combinar datos locales con
datos de la API de Bonita, gráficos interactivos y exportación estructurada.
Esta implementación incorpora esas capacidades sobre los registros disponibles.
Los ejemplos del PDF de **suministros movilizados** y **porcentaje de resolución
mediante consorcios** se muestran como no disponibles: necesitan completar el
registro local de adjudicación, ejecución y cierre. Las cantidades ofrecidas y
las ofertas conjuntas confirmadas son métricas distintas y se identifican así.

## Período y fórmulas

Las fechas `fecha_desde` y `fecha_hasta` son inclusivas, en
`America/Argentina/Buenos_Aires`. Por defecto se toma desde el primer día del mes
actual hasta hoy. Se filtra la **fecha de creación de la emergencia**, junto con
municipio, gravedad y estado actuales. Los lotes, convocatorias y ofertas
relacionados se agregan en su situación actual, aunque se hayan creado después
del período. No es una reconstrucción histórica al último día elegido.

| Indicador | Cálculo |
| --- | --- |
| Emergencias | Cantidad de emergencias seleccionadas, una vez cada una. |
| Activas | Total menos `RESUELTA` y `CANCELADA`. |
| Resueltas | Cantidad cuyo estado local es `RESUELTA`; cero es un resultado válido. |
| Convocatorias abiertas | Convocatorias de esas emergencias con estado local `ABIERTA`; el dashboard no ejecuta temporizadores. |
| Ofertas presentadas | Una por identidad, versión actual con `presentada_en`, excluyendo borradores, retiradas y fuentes fusionadas. Las propuestas conjuntas sin todas las confirmaciones no cuentan. |
| ONG participantes | ONG distintas de las versiones incluidas, más las ONG creadoras para conservar compatibilidad con ofertas anteriores al desglose nacional. |
| Ofertas conjuntas | Versiones incluidas con dos o más participantes y todos confirmados. |
| Cantidades ofrecidas | Suma de items de esas versiones, agrupada por código publicado de capacidad (o tipo de necesidad histórico sin código) y unidad normalizada. No se suman unidades diferentes. |
| Evolución mensual | Altas de emergencias por mes en horario argentino; incluye meses vacíos. |

Las cantidades conservan precisión decimal en PostgreSQL y se serializan como
strings. Los gráficos muestran evolución, estados, gravedad y participación
individual/conjunta. Cada gráfico incluye una tabla accesible.

## Tiempos de Bonita

FastAPI reutiliza `ClienteBonita` para consultar
`GET /API/bpm/archivedFlowNode?f=caseId={id}` de cada caso vinculado a una emergencia
seleccionada. Página de 100 filas, ordenada por `archivedDate ASC`, hasta 100
páginas; si se alcanza el límite se rechaza esa consulta en lugar de presentar
datos truncados. Solo se cuentan tareas humanas, automáticas y manuales con
nombre. La integración fue comprobada contra Bonita 10.4.0: `archivedActivity`
y `archivedTask` devuelven la última transición, mientras `archivedFlowNode`
incluye las transiciones intermedias necesarias para este cálculo.

Cada `sourceObjectId` identifica una ejecución. Se calcula el intervalo desde
la primera transición intermedia observable hasta `completed`, agrupando por
nombre BPM y versión de proceso local. Las repeticiones aportan muestras
separadas; las transiciones duplicadas no las multiplican. Se descartan tareas
sin inicio observable, con fechas inválidas o duración negativa. Tareas aún
abiertas, canceladas o abortadas no contribuyen al promedio. No se usa
`actualizada_en` como fecha de finalización.

`BONITA_TIMEZONE=UTC` configura la zona de las fechas sin offset del Runtime.
Si Bonita corre en otra zona, debe usarse su identificador IANA. El Compose de
desarrollo corre en UTC. Las fechas con offset se normalizan a UTC.

El endpoint informa estado `DISPONIBLE`, `PARCIAL`, `SIN_DATOS` o `NO_DISPONIBLE`,
casos seleccionados/vinculados/consultados, casos con muestras, casos sin
historial suficiente, consultas incompletas y muestras descartadas. Se interrumpe
el recorrido al detectar un fallo de conexión/credenciales, o antes de iniciar
otro caso si ya transcurrieron 20 segundos; se conserva lo obtenido y se informa
lo pendiente como consultas incompletas. Una petición en curso conserva los
timeouts del cliente. Los indicadores locales se consultan por separado y
siguen disponibles durante un fallo del motor.

## API y exportación

| Método y ruta | Respuesta |
| --- | --- |
| `GET /api/v1/metricas` | Resumen, distribuciones, evolución mensual, cantidades y municipios para los filtros. |
| `GET /api/v1/metricas/tiempos` | Promedios en segundos, número de muestras y cobertura de Bonita. |

Ambos aceptan `fecha_desde`, `fecha_hasta` (ISO `YYYY-MM-DD`), `municipio_id`
(positivo), `gravedad` y `estado` (enums existentes). Un período invertido o un
filtro inválido devuelve 422; sin sesión, 401; otro rol, 403. El contrato completo
está en `/docs`. Las alertas requieren la migración indicada más abajo;
no hay cambios de BPM ni de la API Nacional.

TanStack Query mantiene los resultados separados por filtros. **Actualizar
métricas** vuelve a consultar ambas fuentes. El menú **Exportar** ofrece JSON,
CSV y PDF del resultado visible, sin volver a consultar Bonita. Se deshabilita
mientras se está consultando o cuando falla el resumen local. Un fallo de Bonita
permite exportar el resumen indicando la fuente como no disponible.

JSON incluye filtros, fecha de generación, zona horaria, fuentes, agregados,
tiempos y motivos de indicadores pendientes con valor `null`. CSV usa UTF-8 con
BOM y columnas `seccion,indicador,categoria,valor,unidad`; incluye metadatos,
filtros y cobertura. Escapa comillas, separadores y campos que puedan interpretarse
como fórmulas al abrirlos en una planilla.

Se agregó Recharts como dependencia de producción para los gráficos interactivos
y `react-is` compatible con React 19. El dashboard se carga de forma diferida
para evitar descargar la librería de gráficos en los otros perfiles.

PDF usa jsPDF y AutoTable, cargados al elegir ese formato. Incluye filtros,
fuentes, indicadores, todas las filas de las tablas (aunque estén dentro de un
scroll), cobertura y muestras de Bonita, limitaciones y los gráficos visibles.
Las tablas se paginan automáticamente. Si una imagen no se puede incorporar,
el PDF lo indica y mantiene su tabla de datos.

Los colores son estables por categoría: gravedad baja verde, media amarilla,
alta naranja y crítica roja; resueltas verdes y canceladas rojas. Las categorías
conservan sus etiquetas para que la lectura no dependa exclusivamente del color.
Las tablas de los acordeones y cantidades ofrecidas tienen altura máxima,
scroll en ambos ejes cuando se necesita y acceso por teclado.

## Demo ampliada

```bash
docker compose exec backend python -m app.scripts.seed
```

El seed conserva los dos escenarios originales y agrega diecisiete emergencias
etiquetadas `Demo auditoría`, distribuidas en el mes actual y los cinco anteriores,
con tres municipios, siete estados y cuatro gravedades. Incluye convocatorias
abiertas/cerradas, ofertas individuales, consorcios confirmados y pendientes,
ofertas retiradas, versiones anteriores y dieciséis capacidades con distintas
unidades. Reejecutarlo actualiza sus escenarios sin duplicar identidades.

Se agregan los operadores `municipio-rio@rescuesync.org` y
`municipio-sierra@rescuesync.org`, con sus contraseñas públicas de desarrollo
`municipio-rio123` y `municipio-sierra123`. Las ONG y el auditor mantienen sus
cuentas de desarrollo. El seed sigue bloqueado en producción.

El mes actual permite demostrar todos los estados. Para ver la evolución
completa, elegir como fecha desde el primer día de hace cinco meses.
El seed no inventa IDs, fallos ni tiempos de Bonita: el gráfico de tiempos y las
alertas corresponden exclusivamente a casos reales vinculados al Runtime.
`seed_development_data(..., incluir_dashboard=False)` conserva el escenario
original mínimo para pruebas unitarias que necesitan cantidades exactas.

## Notificaciones y actualización en tiempo real

El backend observa `GET /API/bpm/flowNode?f=state=failed` al iniciar y después
cada `BONITA_MONITOR_INTERVAL_SECONDS` (30 segundos por defecto). No ejecuta
tareas ni temporizadores BPM. Correlaciona `rootCaseId` con emergencias locales
y persiste `TAREA_BONITA_FALLIDA` para cada auditor activo, sin organización.
Una restricción única impide repetir la alerta del mismo nodo por usuario entre
sondeos o workers. Una falla de conexión al motor no se presenta como una tarea
fallida. Los errores o trazas de conectores no se copian al mensaje.

La migración `20261015_0013` agrega ese tipo de notificación. Su downgrade
conserva las alertas como novedades de estado de la emergencia. Aplicar
`alembic upgrade head` antes de arrancar el backend actualizado.

`BONITA_MONITOR_ENABLED=false` desactiva el sondeo. En `APP_ENV=test` el monitor
está apagado: las pruebas usan RESPX y sesiones aisladas. El apagado de FastAPI
espera a que termine la consulta en curso antes de cerrar el cliente HTTP.

Se reutiliza `/api/v1/notificaciones/ws`, autenticado con sesión y origen CORS.
Las conexiones auditoras reciben `metricas.actualizadas`, sin datos privados,
después de confirmar altas, lotes, publicación, cierre y cambios de ofertas o
consorcios. El monitor también publica esa señal en cada sondeo exitoso para
refrescar los tiempos del motor y detectar datos cargados desde el seed.
La recepción y la reconexión invalidan las consultas de métricas y el buzón;
conservan los filtros del formulario y solo vuelven a consultar la selección
aplicada. Los otros perfiles mantienen su canal de notificaciones propio.

## Verificación

Con una base PostgreSQL destinada a pruebas y migrada:

```bash
docker compose exec -e APP_ENV=test -e POSTGRES_DB=rescuesync_dashboard_test backend pytest tests/test_metricas.py tests/test_metricas_bonita.py tests/integrations/bonita/test_cliente.py
cd frontend
npm test
npm run lint
npm run build
npm run test:e2e
```

La prueba controlada siguiente crea y elimina su propio caso en el Runtime; no
modifica emergencias de la aplicación:

```bash
docker compose exec -e RUN_BONITA_E2E=1 backend pytest tests/e2e/test_metricas_runtime.py
```

Las pruebas Playwright levantan Vite en el puerto 5184 y simulan la API para
verificar gráficos, filtros, descargas reales y ausencia de desbordamiento a
320 y 1280 px. No modifican datos de la aplicación. Requieren Chromium instalado
mediante `npx playwright install chromium`.

Para revisar la interfaz, ingresar como auditor, aplicar un período vacío y otro
con datos, combinar filtros, abrir las tablas de gráficos, actualizar y exportar
ambos formatos. Verificar a 320 px y escritorio, y comprobar que un administrador
reciba 403 al intentar consultar la API de métricas.
