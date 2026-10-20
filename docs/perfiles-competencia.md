# Perfil de competencia de la ONG

Desde el cambio solicitado del 20/10/2026 no se requieren certificaciones ni
aprobación institucional. La ONG puede registrar recursos y ofertar desde su alta.
El PDF original conserva su contenido; esta decisión sustituye sus requisitos de
certificación y clasificación por niveles de habilitación.

En **Mis recursos → Perfil de competencia** se consultan capacidades declaradas
y cantidades totales, comprometidas y disponibles. El perfil se deriva del
inventario activo; no asigna permisos, roles principal/apoyo ni límites por riesgo.
Las capacidades con stock agotado permanecen visibles. Sin recursos se muestra
un perfil vacío. La antigua URL `/mis-recursos/certificaciones` redirige al perfil.

El navegador consulta `GET /api/v1/mi-ong/perfil-competencia`. FastAPI obtiene la
ONG del usuario autenticado y llama a la API nacional; valida contrato e identidad.
El JWT permanece en el servidor. Se conservan renovación, aislamiento por ONG,
limpieza de caché al perder acceso, estados de carga/error/vacío y actualización.

Tras cerrar la convocatoria, Bonita sigue invocando la evaluación nacional. La
respuesta contrato 3 contiene perfiles informativos y motivos de consistencia.
Municipio y coordinador pueden consultar esos perfiles; el municipio selecciona
cantidades entre aportes compatibles. La ausencia de perfil informativo no
impide seleccionar un aporte cuya identidad, referencias y stock sean válidos.
Se conservan compatibilidad con el lote, unidades, fracciones y cobertura sin
sumar dos veces el mismo recurso. El compromiso nacional vuelve a comprobar
stock bajo locks para evitar sobreasignaciones.

Los resultados históricos contrato 2 se leen como historia y aparecen sin vigencia
para adjudicar. Las operaciones confirmadas siguen su ciclo de finalización,
liberación y cierre. Los casos pendientes con evaluaciones antiguas requieren otra
evaluación mediante Bonita antes de seleccionar; no se modifica su JSON histórico.

Aplicar primero la migración nacional `20261020_0006` y coordinar el despliegue de
ambas APIs por el cambio de contrato. Bonita conserva su proceso 1.5, sus rutas y
contratos de tareas: transporta el resultado JSON íntegro y recibe los mismos
booleanos de vigencia y cobertura. No se cambia el timer ni la orquestación.

Ver [contrato y migración nacionales](../../RescueSyncAPI/docs/perfiles-competencia.md)
y [contratos de Bonita](./bonita/contratos-t36-t37.md).

## Verificación del 20/10/2026

577 pruebas del backend y 198 del frontend; lint, formato, typecheck y build.
Tras los últimos ajustes de compatibilidad histórica se repitieron las 70 pruebas
de las áreas afectadas. También se validaron contratos serializados entre ambas APIs
y el transporte íntegro del resultado en el BAR 1.5.

La E2E completa con Runtime no se ejecutó: Bonita 1.5 estaba habilitado, pero
la API nacional no estaba sirviendo HTTP en la URL configurada para el proceso.
Las pruebas con PostgreSQL y las comprobaciones del BAR no sustituyen esa E2E.
