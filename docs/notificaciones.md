# Detalles de las notificaciones

El ojo abre el evento concreto del aviso. Al pulsarlo se marca la novedad como
leída mediante el PATCH existente y se cierra el panel. Consultar el detalle por
GET conserva su estado de lectura.

| Destinatario | Aviso | Contenido |
| --- | --- | --- |
| Coordinador del centro responsable | Nueva oferta recibida | Emergencia, ronda, estado de la oferta, última versión presentada, ONGs y aportes. |
| Auditor activo | Tarea de Bonita con errores | Tarea y emergencia del incidente, estado observado y fecha del aviso. |
| ONG activa | Nueva convocatoria abierta | Convocatoria exacta, lotes publicados, plazo, estado actual y oferta propia si existe. |
| ONG activa | Convocatoria cerrada | La misma información histórica, o el mensaje «Tu ONG no participó en esta convocatoria». |

El cierre continúa notificándose a todas las ONGs activas. Una ronda nueva no
reemplaza el detalle de una convocatoria anterior. Las cantidades y unidades de
los lotes proceden del snapshot de esa convocatoria.

Las propuestas conjuntas pendientes de confirmación conservan sus aportes
ocultos. El coordinador consulta la última versión efectivamente presentada; la
ONG consulta la versión vigente que le corresponde, con sus aportes visibles
solo cuando están presentados.

El detalle de una tarea es una constancia del incidente observado. Sigue
disponible si el motor ya resolvió el problema y distingue expresamente el estado
observado del estado actual. Es una vista de consulta sin acciones de ejecución
o reintento y no depende de la disponibilidad del Runtime de Bonita.

## API y autorización

`GET /api/v1/notificaciones/{notificacion_id}/detalle` devuelve una unión
discriminada por `clase`: `OFERTA_RECIBIDA`, `CONVOCATORIA` o
`TAREA_BONITA_FALLIDA`. El frontend valida el contrato con Zod y presenta carga,
error con reintento y ausencia de participación.

El servidor filtra el aviso por su destinatario antes de resolver la entidad.
Luego revalida el rol, la organización activa y, para una oferta recibida, el
centro responsable de la emergencia. Para las ONGs devuelve exclusivamente su
oferta, incluida su participación en un consorcio. Un aviso ajeno o inexistente
devuelve 404; la pérdida de los permisos sobre un aviso propio devuelve 403.

## Migración de avisos existentes

Aplicar `alembic upgrade head`, incluida la revisión `20261020_0017`, antes de
ejecutar el backend actualizado. La migración conserva fechas y lecturas y cambia
los cuatro destinos afectados a `/notificaciones/{id}`. También conserva la
emergencia y el nombre observado de las tareas fallidas: para avisos anteriores
los recupera del formato conocido del mensaje y valida la emergencia existente.
Un incidente antiguo cuyo contexto no pueda recuperarse informa que el detalle
no está disponible, sin deducir una emergencia arbitraria.

Las notificaciones municipales, los avisos de emergencias pendientes y las
adjudicaciones mantienen sus destinos específicos de ejecución o lotes.
