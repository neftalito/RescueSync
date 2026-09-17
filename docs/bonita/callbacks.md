# Callbacks de Bonita hacia FastAPI

Los conectores REST del proceso invocan endpoints internos de FastAPI. El
frontend no consume estas rutas.

| Tarea de Bonita | Endpoint | Efecto local |
| --- | --- | --- |
| `Enviar notificacion a ONGs de convocatoria` | `POST /api/v1/emergencias/{id}/notificar-apertura` | Alinea `convocatoria.cierra_en` con la fecha del timer. |
| `Cerrar convocatoria local` | `POST /api/v1/emergencias/{id}/cerrar-convocatoria` | Pasa la convocatoria a `CERRADA` de forma idempotente. |
| `Solicitar ofertas consolidadas` | `GET /api/v1/emergencias/{id}/ofertas-consolidadas` | Devuelve el indicador `lotesCubiertos`. |

`POST /api/v1/emergencias/{id}/resolver` pertenece al cierre del proyecto de la
Entrega 3 y todavía no está implementado.

## Autenticación

Todas las rutas dependen de `validar_callback_bonita` y exigen:

```http
Authorization: Bearer <BONITA_CALLBACK_TOKEN>
```

El backend compara el token en tiempo constante. Responde `401` cuando no
coincide y `503` cuando la integración no está configurada. En producción se usa
un secreto propio de al menos 32 caracteres; no se versionan tokens reales.

Compose utiliza en desarrollo
`dev-only-rescuesync-bonita-callback-token`. Cambiar el token después de instalar
el proceso exige reinstalar sus parámetros, como explica la
[guía de operación](./despliegue-y-operacion.md#reinstalar-parámetros).

## Correlación del caso

Los conectores agregan:

```http
X-Bonita-Root-Process-Instance-Id: <caseId>
```

FastAPI verifica que ese identificador coincida con
`emergencia.bonita_process_instance_id`. Un caso ajeno recibe `409`; no alcanza
con que el cuerpo mencione el mismo `idEmergencia`.

`intentoConvocatoria` del proceso corresponde a `convocatoria.numero`. La
convocatoria local debe existir antes de que FastAPI complete la tarea
`Generar lotes de necesidades`.

## Idempotencia y consolidación

Los callbacks de escritura son idempotentes porque los conectores pueden
reintentarlos. La consolidación se realiza solamente sobre la última convocatoria
cerrada y utiliza la versión vigente de las ofertas presentadas. Excluye
borradores y ofertas retiradas.

Un aporte cuenta para la cobertura cuando utiliza la unidad publicada por el
lote. El detalle de emergencias, lotes y ofertas permanece en PostgreSQL local;
Bonita recibe solo el resultado necesario para decidir el recorrido.

## Tratamiento de respuestas

- Un `2xx` confirma el callback.
- Un `4xx` representa un error definitivo de contrato, autenticación,
  correlación o estado y deja fallida la tarea en Bonita.
- Los conectores pueden reintentar fallos `5xx`. El GET del consolidado usa
  espera creciente y hasta diez intentos.

Las respuestas no deben incluir SQL, secretos, credenciales ni detalles
internos del Runtime.
