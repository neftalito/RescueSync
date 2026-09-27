# Proceso BPM vigente

La fuente de verdad desplegable es [`RescueSync-1.2.bar`](../RescueSync-1.2.bar),
construido con Bonita Studio 2025.2 para Runtime 10.4. El proyecto fuente `.bos`
no forma parte del repositorio.

Esta versión cubre la integración inicial de la Entrega 2: alta y correlación de
la emergencia, espera de publicación de lotes, ventana de ofertas administrada
por Bonita y consulta del consolidado local. La validación con la API Nacional
pertenece a la Entrega 3.

## Responsabilidades

- React consume solamente FastAPI.
- FastAPI autentica, autoriza, persiste el dominio en PostgreSQL y adapta la API
  REST de Bonita.
- PostgreSQL local conserva emergencias, lotes, convocatorias, ofertas y sus
  versiones.
- Bonita administra el recorrido BPM, las tareas humanas y los temporizadores.
- La futura API Nacional valida capacidades y bloquea o libera recursos; no
  recibe borradores de ofertas.

## Contrato de inicio 1.2

| Entrada | Tipo Bonita | Validación principal |
| --- | --- | --- |
| `idEmergencia` | `LONG` | Entero positivo. |
| `gravedad` | `TEXT` | `BAJA`, `MEDIA`, `ALTA` o `CRITICA`. |
| `zona` | `TEXT` | No vacía, máximo 255 caracteres. |
| `descripcion` | `TEXT` | No vacía. |
| `municipioId` | `LONG` | Entero positivo. |

Bonita guarda cada entrada en una variable persistente del mismo nombre. El
índice de búsqueda 1 usa la etiqueta `idEmergencia` y permite reconciliar una
instanciación cuyo resultado HTTP fue incierto. El índice no garantiza unicidad;
FastAPI también debe controlar el estado de sincronización local.

El contrato tipado de FastAPI vive en
`backend/app/integrations/bonita/contratos.py` y debe permanecer alineado con el
`.bar`.

## Recorrido implementado

```text
Inicio → Generar lotes de necesidades (Coordinador; FastAPI la completa al publicar)
  → Publicar convocatoria: intentoConvocatoria + 1 y fechaCierreOfertas = ahora + ventana
  → notificar-apertura → timer EsperarOfertas (fecha fechaCierreOfertas)
  → cerrar-convocatoria → ofertas-consolidadas → ¿lotesCubiertos?
       ├── sí → Seleccionar ofertas validadas
       └── no → Evalua situacion: REABRIR (nueva convocatoria),
                REFORMULAR (Generar lotes) o CONTINUAR_PARCIAL (Seleccionar)
```

`Generar lotes de necesidades` pertenece al actor Coordinador Regional y su
contrato está vacío. FastAPI la localiza por nombre, la asigna al usuario
`coordinador.regional` y la completa cuando la publicación local ya es coherente.

`POST /api/v1/emergencias/{id}/publicar` confirma primero la convocatoria en
PostgreSQL y recién después completa esa tarea
(`app/services/publicacion_bonita.py::completar_generacion_lotes`), en una
llamada separada que nunca hace fallar la respuesta local. El resultado
queda en `Convocatoria.bonita_generar_lotes_estado`
(`PENDIENTE`/`COMPLETADA`/`ERROR`/`RESULTADO_DESCONOCIDO`) y
`bonita_generar_lotes_ultimo_error`. Si la sincronización falla, volver a
llamar al mismo endpoint reintenta solo ese paso: no crea una convocatoria
nueva mientras la anterior siga `ABIERTA`, y antes de reejecutar la tarea
vuelve a preguntarle a Bonita si sigue lista. Cada intento toma primero un
claim persistido y lo confirma en una transacción corta. Las llamadas HTTP a
Bonita ocurren sin una transacción PostgreSQL abierta; al terminar, otra
transacción guarda el resultado solamente si el intento todavía conserva el
claim. Un reintento concurrente observa el claim vigente y no duplica la
ejecución de la tarea. Los claims abandonados vencen después de una ventana
superior a los timeouts HTTP configurados y pueden ser reconciliados.

`Validar Oferta` no tiene conector en esta versión. La validación, el bloqueo y
la liberación de recursos del Sistema Nacional quedan fuera de la Entrega 2.

## Cambiar la versión

Un cambio del proceso se integra en un único pull request:

1. Crear una versión nueva del pool en Bonita Studio y generar el `.bar`.
2. Reemplazar el artefacto de `docs/`, dejando un único `.bar`.
3. Actualizar `BONITA_PROCESS_VERSION`.
4. Alinear contratos, callbacks y pruebas RESPX.
5. Ejecutar la prueba del artefacto y la E2E controlada contra el Runtime.

No se configura manualmente el ID numérico de la definición: cada Runtime
asigna uno propio y el backend resuelve por nombre y versión.

Las decisiones anteriores al artefacto 1.2 se conservan en el
[diagnóstico histórico](./diagnostico-modelado-historico.md).
