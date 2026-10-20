# Ofertas consolidadas con referencias nacionales (T34)

> Actualización 20/10/2026: [perfiles informativos](./perfiles-competencia.md) reemplaza las
> reglas de certificación, habilitación previa y clasificación por riesgo de este
> documento. Las referencias a esas reglas describen el comportamiento anterior.


La implementación amplía el GET local existente que consume Bonita 1.2 y la
captura que produce sus datos. Las ofertas permanecen en PostgreSQL local;
la API nacional conserva el inventario y posteriormente evaluará los aportes
transitoriamente mediante T31. Esta tarea no registra compromisos ni reservas.

Relacionado con [RescueSyncAPI #10](https://github.com/neftalito/RescueSyncAPI/issues/10).

## Configuración y transición

Aplicar las migraciones locales hasta `20261014_0010` antes de ejecutar el backend actualizado:

```bash
docker compose build backend migrate frontend
docker compose run --rm migrate
```

La migración conserva registros existentes y agrega referencias externas
nullable, participantes por versión y aportes por ítem. No inventa identidades
para ofertas históricas ni copia el mapping actual de una ONG a una versión
anterior. No crea claves foráneas a la base nacional.

| Variable nueva | Uso |
| --- | --- |
| `NACIONAL_SISTEMA_ORIGEN` | Código estable de esta instalación, acordado con el emisor nacional. Se congela al publicar la convocatoria. |
| `NACIONAL_CATALOGO_LOGIN` | Cuenta técnica nacional autorizada para leer capacidades desde coordinación. |
| `NACIONAL_CATALOGO_PASSWORD` | Secreto de esa cuenta, provisto por entorno; no se envía al navegador. |

El catálogo usa el cliente nacional compartido y verifica que la cuenta sea
INTEGRACION o ADMIN_NACIONAL. El administrador nacional existente puede
aprovisionarse con el CLI de bootstrap; una cuenta INTEGRACION debe ser
aprovisionada por la administración nacional. No reutilizar las credenciales
personales de una ONG como cuenta de todos los coordinadores.

Con `NACIONAL_SISTEMA_ORIGEN` configurado, nuevos lotes/convocatorias requieren
capacidades nacionales explícitas. Vacío conserva el recorrido local anterior,
cuyos consolidadores pueden indicar referencias incompletas. Ese modo de
compatibilidad no habilita adjudicaciones nacionales. Para el recorrido completo
hay que configurar emisor/catálogo y vincular las ONGs con sus UUID verificados.

## Captura en la aplicación

1. El formulario carga automáticamente el catálogo y el coordinador selecciona
   **Capacidad** en lugar de ingresar un tipo de necesidad libre. La unidad es
   de solo lectura; cantidad y descripción opcional se completan por separado.
   El backend valida existencia, unidad y admisión de fracciones contra el
   catálogo y guarda su nombre como `tipo_necesidad` (hasta 160 caracteres).
   Un borrador anterior sin vínculo requiere elegir una capacidad para volver
   a guardarlo; no se infiere el UUID a partir de su texto. Si falla el catálogo
   se puede reintentar, y si no hay capacidades activas se bloquea el guardado.
   El riesgo elegido o la gravedad de la emergencia se congelan al
   publicar, junto con capacidad, código, unidad, cantidad y emisor.
2. Cada ONG conecta su cuenta en **Mis recursos**. Al crear/editar una oferta
   para un lote asociado, elige recursos propios y desglosa las cantidades.
   El backend valida pertenencia, actividad, capacidad/unidad, fracciones y
   suma exacta antes de crear la versión presentada. No deduce recursos desde
   descripciones ni toma la ONG dueña de un campo enviado por el cliente.
3. Las ediciones crean versiones nuevas, con participantes y UUID congelados.
   La nueva versión se presenta al final de la misma transacción, después de
   insertar su desglose. No se modifica el contenido presentado anterior.

Las verificaciones HTTP terminan antes de tomar locks locales. Dentro de la
transacción se revalidan ventana, versión y mapping local. La consulta previa
del inventario no reserva stock ni demuestra competencia para el riesgo.

## Consorcios y consentimiento

Este corte forma un consorcio a partir de **ofertas individuales ya presentadas
en la misma convocatoria**, con recursos nacionales propios. Desde **Mis
ofertas**, la líder invita a otra ONG que tenga una oferta individual. La
propuesta congela las versiones de origen y suma sus aportes por lote sin
superar la cantidad publicada.

La versión conjunta queda BORRADOR hasta que todas las participantes confirmen.
Una invitación no autoriza el uso de recursos de otra ONG. El GET técnico
excluye la propuesta pendiente; la respuesta web no muestra los ítems de esa
propuesta mientras falten confirmaciones. La oferta individual de una invitada
permanece disponible hasta que el consorcio sea presentado.

Cada participante confirma con su sesión y CSRF vigentes la versión visible.
Si alguna oferta individual o vinculación cambió, se responde 409/422 y se debe
desarmar y renovar la propuesta. Al completar las confirmaciones se presenta
la versión conjunta y las ofertas de origen de las miembros se marcan fusionadas,
evitando sumarlas de nuevo. Una ONG que integra un consorcio activo no puede
presentar otra oferta independiente en esa ronda.

Cualquier participante puede rechazar/desarmar durante la ventana; se restauran
las ofertas individuales sin borrar la versión conjunta. Cancelar otra propuesta
pendiente no deshace una fusión confirmada con un consorcio diferente. Para editar
aportes de un consorcio presentado se desarma, se editan las ofertas individuales
y se crea otra propuesta con nuevas confirmaciones. La API admite hasta diez
invitadas; la pantalla permite elegir una por propuesta en este corte.

## Contratos locales de captura

| Ruta | Acceso/efecto |
| --- | --- |
| `GET /api/v1/emergencias/catalogos/capacidades-nacionales` | Coordinador vigente; catálogo mediante credenciales del servidor. |
| `POST /api/v1/emergencias/{id}/lotes` | Conserva el contrato local y agrega `capacidad_nacional_id`, `riesgo_requerido`. |
| `POST /api/v1/ofertas` y `PUT /api/v1/ofertas/{id}` | Agregan `items[].aportes[]` con `recurso_nacional_id` y cantidad; dueño derivado de sesión. |
| `GET /api/v1/ofertas/ongs-disponibles?convocatoria_id=...` | ONG vigente; sólo nombres e IDs locales para invitar, sin inventario ajeno. |
| `POST /api/v1/ofertas/{id}/consorcio` | Líder, CSRF, `version_bloqueo` y `ong_ids`. Crea una propuesta pendiente. |
| `POST /api/v1/ofertas/{id}/consorcio/confirmacion` | Participante, CSRF y `version_bloqueo`. Confirma sus propios aportes. |
| `DELETE /api/v1/ofertas/{id}/consorcio` | Participante, CSRF y `version_bloqueo` en JSON. Restaura ofertas individuales. |

La base protege sumas, pertenencia a ítem/participante de la misma versión,
un único líder, confirmaciones y referencias completas al presentar. Los
snapshots nacionales presentados y requerimientos publicados son inmutables.

## GET técnico compatible con Bonita 1.2

```http
GET /api/v1/emergencias/101/ofertas-consolidadas?intentoConvocatoria=2
Authorization: Bearer <BONITA_CALLBACK_TOKEN>
X-Bonita-Root-Process-Instance-Id: 9001
```

La query `intentoConvocatoria` es opcional para conservar el consumidor 1.2;
si se envía debe coincidir con la ronda más reciente. Esa ronda debe estar
CERRADA; una ronda nueva abierta/cancelada recibe 409 y no produce un fallback
a ofertas anteriores. Se usa sólo la versión actual presentada y se excluyen
borradores, retiradas y fusionadas.

La lectura usa una sesión REPEATABLE READ desde la primera consulta y carga
versiones, participantes y aportes en conjunto. No realiza HTTP nacional,
login, escrituras ni sincronizaciones durante el GET. Conserva autenticación
técnica, correlación del caso raíz, camelCase y `Cache-Control: no-store`.
El token de callback local no es un JWT nacional.

Los campos anteriores y sus tipos se conservan. `lotesCubiertos`/`cubierto`
indican cobertura numérica bruta, sin probar competencia ni disponibilidad.
Campos nuevos principales:

- Raíz: `contratoVersion: 2`, `sistemaOrigen`, `caseId` string, `gravedad`,
  `cerradaEn`, `referenciasNacionalesCompletas`, `motivosIntegracion`.
- Lote: `capacidadNacionalId`, `codigoCapacidad`, `riesgoRequerido`,
  `cantidadPublicadaExacta`, `cantidadOfrecidaExacta`.
- Oferta: `ongNacionalId`, `participantes` congeladas, indicador y motivos.
- Ítem: `itemId`, `cantidadOfrecidaExacta`, `aportes` con `aporteId`, ONG
  local/nacional dueña, recurso/capacidad nacional, cantidad y unidad.

Las cantidades nuevas son strings con tres decimales, obtenidas del Decimal
original. T31 debe consumirlas y evitar las cantidades numéricas legacy.
`contratoVersion` no es la versión de oferta ni la del proceso Bonita.

Las versiones anteriores sin referencias siguen en el resultado con nulls,
aportes vacíos y motivos tipados, por ejemplo `ONG_NACIONAL_NO_ASOCIADA`,
`PARTICIPANTES_NO_VERSIONADOS`, `DESGLOSE_NACIONAL_AUSENTE`,
`CAPACIDAD_NACIONAL_NO_ASOCIADA`, `SISTEMA_ORIGEN_NO_ASOCIADO` o
`RIESGO_PUBLICADO_AUSENTE`. Esos motivos describen integración faltante y no
una aprobación/rechazo de competencia. No ocultar ofertas históricas ni
completar sus identidades con mappings actuales.

## Verificación y tareas posteriores

Ejecutar en PostgreSQL de pruebas, con migraciones aplicadas:

```bash
docker compose run --rm backend ruff check .
docker compose run --rm backend ruff format --check .
docker compose run --rm backend pytest --cov=app --cov-report=term-missing
docker compose run --rm frontend npm run lint
docker compose run --rm frontend npm run typecheck
docker compose run --rm frontend npm test
docker compose run --rm frontend npm run build
```

Los tests cubren contrato 1.2, vigencia de ronda/versión, referencias faltantes,
consorcios, pertenencia, sumas, datos inmutables y una reapertura confirmada
desde otra conexión durante el GET. RESPX verifica la captura nacional;
Testing Library/MSW cubren selección de capacidad, recursos propios y aceptación.
Upgrade/downgrade/upgrade se comprueba exclusivamente en una base descartable;
el downgrade elimina los datos nuevos de snapshots.

T34 no cambia el `.bar` 1.2. T35/T36 deben ampliar el conector existente,
obtener JWT nacional, llamar T31 y guardar perfiles mediante callback local.
Esos cambios requieren fuente `.bos` o reconstrucción verificada, nueva versión
del pool, único `.bar`, configuración y E2E de Runtime. Compromiso/liberación
y adjudicación corresponden a T32/T33/T37.
