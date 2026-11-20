# Monitoreo de procesos

El dashboard del auditor incorpora los seis ejemplos de la página 12 de
[`Monitoreo de procesos.pptx.pdf`](<./Monitoreo de procesos.pptx.pdf>) y el
seguimiento de actividades en curso. React consulta FastAPI, que combina
PostgreSQL con la API REST de Bonita. El monitoreo no ejecuta tareas ni timers.

## Alcance y fórmulas

`GET /api/v1/metricas` incorpora `indicadores_proceso`. Conserva permisos y
filtros existentes: las fechas seleccionan **altas de emergencias**, en horario
argentino, y se consideran sus hechos hasta la consulta. No representa eventos
ocurridos exclusivamente dentro del mes ni una reconstrucción histórica al
último día elegido. Pantalla y exportaciones incluyen estas definiciones.

| Indicador | Fuente y cálculo |
| --- | --- |
| Resolución por gravedad | Resueltas por estado local o cierre confirmado / emergencias de esa gravedad. Se informan cierres con evidencia y resueltas sin evidencia por separado. Tiempo medio: cierre menos alerta explícita. En término: cierres dentro del plazo / cierres con plazo informado, con su tiempo medio propio. |
| Reaperturas y reformulaciones | Decisiones confirmadas por emergencia y ronda, diferenciando `REABRIR` y `REFORMULAR`. `CONTINUAR_PARCIAL` se conserva sin incrementar esas dos categorías. |
| Ranking de ONG | Cantidades adjudicadas a cada ONG, por capacidad y unidad. Los miembros de un consorcio cuentan por sus aportes propios. Cumplimiento: aportes finalizados dentro del plazo / aportes finalizados con plazo. Se muestran finalizados y pendientes. |
| Cobertura del cierre | Total si se cumplieron todos los lotes de la ronda de cierre; parcial si existe un faltante. Proporciones sobre cierres con evidencia completa. |
| Demanda por rubro | Suma de necesidades publicadas por capacidad y unidad, incluyendo nuevas rondas. Los rubros se ordenan por cantidad dentro de cada unidad. |
| Alerta a adjudicación | Primera adjudicación confirmada menos alerta explícita; una muestra por emergencia. |

Las cantidades se conservan como `Decimal` y se exportan como strings.
Denominadores vacíos, plazos ausentes y duraciones sin evidencia se representan
con `null`/«Sin datos». Un cero observado conserva su significado. No se usa
`actualizada_en` como cierre ni se confunden ofrecimientos, adjudicaciones y
cantidades efectivamente cumplidas.

`GET /api/v1/metricas/tiempos` conserva los promedios históricos y agrega tareas
activas por emergencia/caso/tarea y resumen de carga por etapa/versión: cantidad,
antigüedad media, muestras con fecha, vencidas, sin plazo y fallidas. La edad
parte de la primera transición observable de esa ejecución y no se reinicia
al asignarla. Se usa `dueDate` para vencimiento, sin inventar un SLA.
La actividad tiene su propia cobertura y comparte con el historial el presupuesto
de 20 segundos. Una consulta incompleta no significa ausencia de tareas activas.
La integración pagina resultados y verifica el caso raíz.

## Registro de evidencia confirmada

La migración `20261015_0014` agrega `hecho_monitoreo` sin inventar historia previa:

```bash
docker compose exec backend alembic upgrade head
```

Callback técnico:

```text
POST /api/v1/emergencias/{id}/hechos-monitoreo
Authorization: Bearer <BONITA_CALLBACK_TOKEN>
X-Bonita-Root-Process-Instance-Id: <caso vinculado>
```

El cuerpo contiene `clave` y `datos`, exige fechas con zona y rechaza campos
desconocidos. Repetir clave/contenido devuelve el mismo registro. Otra clave
para el mismo hecho o contenido modificado devuelve 409. Un bloqueo transaccional
por emergencia y restricciones únicas evitan duplicaciones concurrentes. No hay
endpoints para modificar o eliminar estos hechos.

Ejemplo, **después de confirmar la reserva nacional**, reemplazando referencias
por las reales del caso:

```json
{
  "clave": "adjudicacion:reserva-123",
  "datos": {
    "tipo": "ADJUDICACION_CONFIRMADA",
    "ocurrido_en": "2026-10-14T11:00:00Z",
    "convocatoria_numero": 1,
    "adjudicacion_ref": "reserva-123",
    "alerta_en": "2026-10-14T08:00:00Z",
    "aportes": [
      {"ong_id": 7, "lote_id": 18, "cantidad": "100.125", "plazo_en": "2026-10-15T11:00:00Z"}
    ]
  }
}
```

Los contratos completos de los cinco tipos están en `/docs`:

| Tipo | Campos específicos | Momento de emisión |
| --- | --- | --- |
| `DECISION_CONVOCATORIA` | `decision`, `motivo` | Después de confirmar la decisión del coordinador sobre una ronda cerrada. |
| `VALIDACION_NACIONAL` | `validacion_ref`, `resultados`: ONG, lote, `habilitada`, motivos | Después del resultado nacional. Una fila por ONG/lote; una repetición técnica conserva referencia y clave. |
| `ADJUDICACION_CONFIRMADA` | `adjudicacion_ref`, `alerta_en`, `aportes`: ONG, lote, cantidad y plazo opcional | Después de confirmar o reconciliar exitosamente la reserva nacional. |
| `FINALIZACION_ONG` | `adjudicacion_ref`, `ong_id` | Después de confirmar la finalización de la participación de esa ONG. |
| `RESOLUCION_EMERGENCIA` | `alerta_en`, plazo opcional, `cobertura`: lote y cantidad cumplida | Al confirmar la resolución, después de todas las finalizaciones. |

Todos incluyen `tipo`, `ocurrido_en` y `convocatoria_numero`. El backend exige
que la ronda pertenezca al caso y ya estuviera cerrada en la fecha del hecho;
verifica lotes/ONG participantes, cantidades máximas adjudicadas, antecedentes
de finalización y cobertura de todos los lotes de la última ronda. La alerta
debe coincidir entre adjudicaciones y cierre. Tras el cierre solo admite
repeticiones idénticas de hechos ya registrados.

El emisor técnico sigue siendo responsable de confirmar el resultado nacional.
Este callback registra evidencia; **no reserva/libera recursos ni cambia estados
operativos**. Los conectores deben conservar cuerpo y clave para reintentar un
registro cuya respuesta se perdió, sin repetir la operación de negocio con otra
identidad. Un hecho confirmado invalida las consultas del panel por WebSocket.

## Integración pendiente del proceso

El BAR **1.2 no emite estos nuevos hechos**. La actividad en curso y los tiempos
históricos funcionan con ese BAR; la demanda usa lotes locales existentes.
Los indicadores de resultado se pueblan al recibir evidencia. Hasta entonces
la interfaz muestra cobertura y ausencias, sin simular resultados reales.

Al implementar T35–T37, incorporar las emisiones de la tabla a los conectores
que confirman esas operaciones y exportar una nueva versión según `AGENTS.md`.
Este cambio no modifica el BAR ni implementa esos casos de uso. La presentación
tampoco fija SLA concretos: los plazos deben venir de la política del negocio,
no de la ventana de recepción de ofertas.

## Verificación

Las pruebas cubren PostgreSQL aislado, autenticación, reintentos/conflictos,
cantidades imposibles, cierres prematuros, consorcios, cobertura parcial y falta
de plazos. La prueba Runtime crea y elimina solo su caso temporal. Vitest cubre
los seis indicadores y exportaciones; Playwright verifica escritorio y 320 px.

```bash
docker compose exec -e APP_ENV=test -e BONITA_MONITOR_ENABLED=false \
  -e POSTGRES_DB=rescuesync_monitor_test backend pytest
docker compose exec -e RUN_BONITA_E2E=1 backend pytest tests/e2e/test_metricas_runtime.py
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```
