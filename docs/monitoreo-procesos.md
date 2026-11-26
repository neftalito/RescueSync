# Monitoreo de procesos

El dashboard del auditor incorpora indicadores de
[`Monitoreo de procesos.pptx.pdf`](<./Monitoreo de procesos.pptx.pdf>),
suministros movilizados, resolución mediante consorcios y seguimiento de
actividades en curso. React consulta FastAPI, que combina
PostgreSQL con la API REST de Bonita. El monitoreo no ejecuta tareas ni timers.

## Alcance y fórmulas

`GET /api/v1/metricas` incorpora `indicadores_proceso`. Conserva permisos y
filtros existentes: las fechas seleccionan **altas de emergencias**, en horario
argentino, y se consideran sus hechos hasta la consulta. No representa eventos
ocurridos exclusivamente dentro del mes ni una reconstrucción histórica al
último día elegido. Pantalla y exportaciones incluyen estas definiciones.

| Indicador | Fuente y cálculo |
| --- | --- |
| Resolución por gravedad | Resueltas por estado local o cierre confirmado sobre emergencias de esa gravedad. El tiempo se mide desde el alta municipal o la alerta explícita hasta el cierre confirmado. La tasa en término usa los cierres con plazo informado. |
| Reaperturas y reformulaciones | Decisiones `REABRIR` y `REFORMULAR` por emergencia y ronda, una vez completado el despacho en Bonita. |
| Ranking de ONG | Cantidades confirmadas por ONG, capacidad y unidad. Los miembros de consorcios cuentan por sus aportes propios. Se mide un aporte por ONG y lote en cada adjudicación. Una vez confirmada la liberación, se compara la fecha en que la ONG informó la finalización con el plazo establecido para los aportes. |
| Cobertura del cierre | Total cuando las cantidades cumplidas cubren todos los lotes de la ronda de cierre. Parcial cuando hay un faltante. El porcentaje usa cierres con cantidades verificables. |
| Demanda por rubro | Suma de necesidades publicadas por capacidad y unidad, incluyendo nuevas rondas. Los rubros se ordenan por cantidad dentro de cada unidad. |
| Alerta a adjudicación | Primera adjudicación nacional confirmada menos la fecha de alta municipal o la alerta explícita. Una muestra por emergencia. |
| Suministros movilizados | Cantidades movilizadas declaradas por cada ONG al finalizar, una vez confirmada su liberación. Se agrupan por capacidad y unidad para las emergencias seleccionadas y se informa cuántas participaciones liberadas tienen cantidades registradas. |
| Resolución mediante consorcios | Cierres con al menos dos integrantes adjudicados de una misma oferta conjunta confirmada, aunque el caso también haya tenido adjudicaciones individuales. El porcentaje usa cierres con adjudicación verificable. |

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

## Registro durante la ejecución

El municipio puede indicar un plazo para los aportes seleccionados y otro
para resolver la emergencia en **Solicitar adjudicación**. Los plazos quedan
asociados a esa selección. Cada ONG registra sus cantidades reales por lote
en **Informar finalización**. Puede declarar cero. La cantidad cumplida puede
ser como máximo la movilizada, y esta, como máximo la adjudicada.

Se aplica la migración `20261126_0019` con `alembic upgrade head`. Los casos
históricos aportan sus confirmaciones existentes. Para finalizaciones previas
a la migración o enviadas sin cuerpo, las cantidades permanecen desconocidas.
Un cierre con evidencia parcial de cantidades queda fuera de las proporciones
de cobertura total y parcial.

## Callback de evidencia histórica

La migración `20261015_0014` agregó `hecho_monitoreo`. El dashboard conserva
esa evidencia para los casos históricos. Si existe una adjudicación operativa
confirmada en la misma ronda, se cuenta esa adjudicación una sola vez. Una
adjudicación histórica equivalente puede aportar plazos. Los cierres
históricos aportan cobertura cuando faltan las cantidades operativas.

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

En Bonita 1.5, el cálculo toma las confirmaciones de los callbacks operativos
de [T36–T37](./bonita/contratos-t36-t37.md). El callback de evidencia histórica
sigue disponible para emisores que registren hechos explícitos.

## Verificación

Las pruebas cubren PostgreSQL aislado, autenticación, reintentos/conflictos,
cantidades imposibles, cierres prematuros, consorcios, cobertura parcial y falta
de plazos. La prueba Runtime crea y elimina solo su caso temporal. Vitest cubre
los indicadores y exportaciones. Playwright verifica escritorio y 320 px.

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
