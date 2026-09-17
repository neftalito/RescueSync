# División de tareas — Entrega 2

> Propuesta elaborada el 14 de septiembre de 2026 a partir de
> `docs/Grooming Etapa 2.pdf`, `docs/Trabajo integrador 2026.pdf`,
> el `.bos` histórico hoy no disponible y los 21 issues del milestone
> **Entrega 2** incluidos en GitHub Project #6. Al momento del relevamiento,
> todos los issues estaban en estado `Backlog` y la fecha objetivo del milestone
> era el 2 de octubre de 2026. La referencia BPM vigente es
> `docs/RescueSync-1.2.bar`.

## Criterio de reparto

- Se reparten los 21 issues completos: cada uno tiene una única persona
  responsable y debe implementarse en su propia rama y pull request.
- La estimación oficial suma **46 horas**, por lo que el promedio teórico es de
  **9,2 horas por integrante**.
- El reparto queda entre **8,5 y 10 horas**. La desviación máxima respecto del
  promedio es de 0,8 horas.
- No se igualaron solamente las horas. Quienes concentran trabajo fundacional,
  seguridad o integración con Bonita reciben menos horas nominales porque esas
  tareas tienen mayor incertidumbre, impacto transversal y costo de revisión.
- Se favorecen bloques funcionales completos: base, seguridad, emergencia con
  Bonita, lotes y ofertas. Los pocos cruces inevitables se resuelven con
  contratos tempranos, datos de prueba y mocks.
- La dificultad indicada es cualitativa: considera cantidad de capas afectadas,
  reglas transaccionales, seguridad, integración externa y alcance de las
  pruebas. No reemplaza la estimación de GitHub.
- Queda fuera de esta división la API Nacional de la Entrega 3: JWT del sistema
  nacional, despliegue cloud, certificaciones y compromiso o liberación de
  recursos.

## Resumen de carga

| Integrante | Enfoque principal | Issues | Horas | Desviación | Perfil de dificultad |
| --- | --- | --- | ---: | ---: | --- |
| 1 | Fundaciones y material de entrega | T1, T2, T3, T21 | **8,5 h** | −0,7 h | Alta por impacto estructural |
| 2 | Autenticación, RBAC y consulta | T7, T8, T10, T19 | **9,0 h** | −0,2 h | Alta por seguridad transversal |
| 3 | Emergencias e integración Bonita | T4, T15, T16, T17 | **8,5 h** | −0,7 h | Muy alta por sistema externo e idempotencia |
| 4 | Flujo de lotes e interfaces operativas | T5, T9, T11, T12 | **10,0 h** | +0,8 h | Alta, mayormente predecible y testeable con mocks |
| 5 | Flujo de ofertas, E2E y seguimiento | T6, T13, T14, T18, T20 | **10,0 h** | +0,8 h | Alta por reglas de negocio e integración final |
| **Total** |  | **T1–T21** | **46,0 h** |  |  |

La diferencia de horas es deliberada: los integrantes 1 y 3 tienen menos carga
nominal porque concentran los dos mayores riesgos técnicos —el modelo persistente
y Bonita—, mientras que los integrantes 4 y 5 reciben más horas de funcionalidad
vertical que puede avanzar con contratos y respuestas simuladas.

## Integrante 1 — Fundaciones y material de entrega

| Orden | Issue | Semana del Project | Horas | Dificultad | Responsabilidad principal |
| ---: | --- | --- | ---: | --- | --- |
| 1 | [T2 — Configurar entorno del proyecto](https://github.com/neftalito/RescueSync/issues/2) | 14–18 sep. | 2,5 | Media | Dejar ejecutables y documentados FastAPI, React/TypeScript, Docker Compose, PostgreSQL y los controles base. Debe ser el primer PR de infraestructura. |
| 2 | [T1 — Definir esquema de base de datos](https://github.com/neftalito/RescueSync/issues/1) | 14–18 sep. | 3,0 | Muy alta | Definir organizaciones, usuarios, roles, emergencias, lotes, ofertas, relación Oferta–Lote, enums, timestamps UTC, restricciones y trazabilidad de Bonita. |
| 3 | [T3 — Crear migraciones iniciales](https://github.com/neftalito/RescueSync/issues/3) | 14–18 sep. | 1,5 | Alta | Materializar T1 con Alembic, `upgrade()`/`downgrade()` viables y validación sobre PostgreSQL. |
| 4 | [T21 — Preparar material de la entrega](https://github.com/neftalito/RescueSync/issues/21) | 28 sep.–2 oct. | 1,5 | Media | Consolidar README, comandos y evidencias aportadas por todo el equipo, incluyendo la vinculación con Bonita. |
|  | **Total** |  | **8,5 h** |  |  |

Esta persona es dueña del contrato persistente, pero no de todos los cambios de
base de datos posteriores. Cada responsable funcional debe agregar sus pruebas y,
si modifica el esquema aprobado, su propia migración correctiva sin reescribir
T3. Para T21, cada integrante entrega sus capturas y resultados; el integrante 1
solo los consolida y verifica.

## Integrante 2 — Autenticación, RBAC y consulta

| Orden | Issue | Semana del Project | Horas | Dificultad | Responsabilidad principal |
| ---: | --- | --- | ---: | --- | --- |
| 1 | [T7 — Implementar autenticación básica](https://github.com/neftalito/RescueSync/issues/7) | 14–18 sep. | 3,0 | Muy alta | Implementar credenciales con Argon2/pwdlib, sesión mínima, cookies seguras y recarga de usuario, organización y rol desde PostgreSQL. |
| 2 | [T8 — Implementar control de acceso por rol](https://github.com/neftalito/RescueSync/issues/8) | 21–25 sep. | 2,0 | Muy alta | Proveer dependencias reutilizables de autorización y la matriz Municipio/Coordinador/ONG/Auditor, con casos permitidos y denegados. |
| 3 | [T10 — Implementar bandeja y estado de emergencias](https://github.com/neftalito/RescueSync/issues/10) | 28 sep.–2 oct. | 2,0 | Alta | Implementar consulta y pantalla con filtros reales por organización, rol y estado, más carga, vacío, error y éxito. |
| 4 | [T19 — Ejecutar pruebas manuales de formularios](https://github.com/neftalito/RescueSync/issues/19) | 28 sep.–2 oct. | 2,0 | Media | Ejecutar y registrar la matriz manual de validaciones, permisos y fallos controlados de Bonita. |
|  | **Total** |  | **9,0 h** |  |  |

T8 no debe convertirse en un PR gigante que edite todas las funcionalidades al
final. El integrante 2 entrega primero las dependencias y la matriz de permisos;
cada dueño de endpoint las aplica en su propio issue. Antes de cerrar T8, el
integrante 2 revisa que ninguna ruta dependa únicamente de ocultar controles en
el frontend.

## Integrante 3 — Emergencias e integración Bonita

| Orden | Issue | Semana del Project | Horas | Dificultad | Responsabilidad principal |
| ---: | --- | --- | ---: | --- | --- |
| 1 | [T15 — Configurar integración con Bonita Runtime](https://github.com/neftalito/RescueSync/issues/15) | 14–18 sep. | 2,0 | Alta | Configurar por entorno URL, credenciales e identificador de proceso y crear el cliente HTTPX reutilizable con timeout explícito. |
| 2 | [T4 — Implementar alta de emergencia](https://github.com/neftalito/RescueSync/issues/4) | 21–25 sep. | 2,0 | Alta | Implementar el caso de uso y `POST /api/v1/emergencias`, persistiendo el municipio autenticado y el estado `REGISTRADA`. |
| 3 | [T17 — Setear variables iniciales del proceso](https://github.com/neftalito/RescueSync/issues/17) | 28 sep.–2 oct. | 1,5 | Alta | Validar el contrato real de Bonita y tipar el mapeo de `idEmergencia`, `gravedad` y `zona`. |
| 4 | [T16 — Iniciar instancia desde una emergencia](https://github.com/neftalito/RescueSync/issues/16) | 28 sep.–2 oct. | 3,0 | Muy alta | Iniciar y vincular la instancia sin perder la emergencia ante fallos; persistir estado de sincronización y error seguro y cubrir éxito, rechazo y timeout con RESPX. |
|  | **Total** |  | **8,5 h** |  |  |

T15, T17 y T16 quedan en una sola persona para evitar un contrato HTTPX/Bonita
partido entre integrantes. El orden T17 → T16 dentro de la tercera semana permite
cerrar primero el payload antes de conectarlo al alta.

### Riesgo detectado en el modelo BPM

El `.bos` analizado originalmente contenía el proceso `RescueSync`, las lanes de
Operador Municipal, Centro Coordinador, ONG y Red Nacional, y el timer de ofertas
de dos horas. Ese proyecto fuente ya no está disponible en el repositorio; la
referencia ejecutable vigente es `RescueSync-1.2.bar`.

Por eso, T17 debe verificar el contrato de inicio en el Runtime y mantener
alineados el `.bar`, FastAPI y sus pruebas. Si un ajuste excede el criterio de
T17, se debe registrar un issue correctivo explícito y reestimar, no ocultar
trabajo adicional dentro de otra tarea.

## Integrante 4 — Flujo de lotes e interfaces operativas

| Orden | Issue | Semana del Project | Horas | Dificultad | Responsabilidad principal |
| ---: | --- | --- | ---: | --- | --- |
| 1 | [T5 — Implementar creación y edición de lotes](https://github.com/neftalito/RescueSync/issues/5) | 21–25 sep. | 2,5 | Alta | Implementar lotes en borrador, autorización, cantidades positivas e invariantes concurrentes sin publicar la convocatoria. |
| 2 | [T9 — Crear formulario de alta de emergencia](https://github.com/neftalito/RescueSync/issues/9) | 21–25 sep. | 3,0 | Media | Crear la experiencia municipal accesible y responsive con React Hook Form, Zod y TanStack Query contra el contrato de T4. |
| 3 | [T11 — Crear formulario de generación de lotes](https://github.com/neftalito/RescueSync/issues/11) | 21–25 sep. | 3,0 | Alta | Implementar detalle de emergencia y lotes dinámicos con `useFieldArray`, manteniendo separado guardar de publicar. |
| 4 | [T12 — Implementar publicación de convocatoria](https://github.com/neftalito/RescueSync/issues/12) | 28 sep.–2 oct. | 1,5 | Alta | Implementar de forma atómica la validación, transición a `PUBLICADA` y acción explícita del Coordinador. |
|  | **Total** |  | **10,0 h** |  |  |

T5, T11 y T12 forman una misma vertical de lotes, con menos traspasos y menos
conflictos entre backend y frontend. T9 equilibra la carga y puede avanzar en
paralelo usando MSW desde que el integrante 3 publique el esquema de solicitud y
respuesta de T4.

## Integrante 5 — Flujo de ofertas, E2E y seguimiento

| Orden | Issue | Semana del Project | Horas | Dificultad | Responsabilidad principal |
| ---: | --- | --- | ---: | --- | --- |
| 1 | [T6 — Implementar carga de oferta básica](https://github.com/neftalito/RescueSync/issues/6) | 21–25 sep. | 2,0 | Alta | Implementar `POST /api/v1/ofertas` con asociación a ONG y lotes, cantidades positivas, convocatoria publicada y transacción atómica. |
| 2 | [T13 — Crear formulario básico de oferta](https://github.com/neftalito/RescueSync/issues/13) | 21–25 sep. | 3,0 | Alta | Implementar ofertas parciales básicas con `useFieldArray`, Zod, TanStack Query y estados accesibles. |
| 3 | [T14 — Implementar convocatorias abiertas y Mis ofertas](https://github.com/neftalito/RescueSync/issues/14) | 28 sep.–2 oct. | 1,5 | Media | Completar consultas y pantallas de convocatorias, lotes publicados y ofertas propias sin exponer datos de otras organizaciones. |
| 4 | [T18 — Implementar pruebas extremo a extremo](https://github.com/neftalito/RescueSync/issues/18) | 28 sep.–2 oct. | 2,0 | Muy alta | Automatizar el recorrido Municipio → Bonita → Coordinador → ONG y un caso denegado o un fallo representativo. |
| 5 | [T20 — Actualizar grooming con estimado vs. real](https://github.com/neftalito/RescueSync/issues/20) | 28 sep.–2 oct. | 1,5 | Baja | Consolidar las horas reales informadas por cada dueño, desvíos y planificación inicial de Entrega 3 sin implementarla. |
|  | **Total** |  | **10,0 h** |  |  |

T6, T13 y T14 forman una vertical completa de ONG. T6 no necesita esperar a que
T12 esté terminado: sus pruebas pueden crear una convocatoria `PUBLICADA` como
fixture, y T13/T14 pueden avanzar con MSW. Solo la integración final depende del
flujo real de publicación.

## Dependencias y forma de evitar bloqueos

| Dependencia | Responsable que habilita | Tareas consumidoras | Acuerdo para no bloquear |
| --- | --- | --- | --- |
| Entorno y estructura base | Integrante 1 — T2 | Todas | Integrar T2 primero y evitar reorganizaciones transversales posteriores. |
| Modelo, enums y relaciones | Integrante 1 — T1/T3 | T4–T8, T10, T12, T14 y T16 | Publicar temprano el diagrama/contrato de T1. Los demás preparan servicios y tests con fixtures mientras se integra la migración. |
| Sesión y autorización | Integrante 2 — T7/T8 | Todos los endpoints y pantallas | Entregar una dependencia backend pequeña y estable; los dueños funcionales aplican y prueban los permisos en sus rutas. |
| Contrato de alta | Integrante 3 — T4 | T9, T10 y T16 | Compartir modelos Pydantic/OpenAPI y fixture MSW antes de completar toda la implementación. |
| Contrato de lotes/publicación | Integrante 4 — T5/T12 | T6, T11, T13 y T14 | Compartir schemas y errores; usar convocatorias publicadas creadas como datos de prueba hasta integrar T12. |
| Cliente y variables Bonita | Integrante 3 — T15/T17 | T16 y T18 | Mantener los tres issues de Bonita bajo el mismo dueño y probar con RESPX; reservar el Runtime para la verificación controlada. |
| Flujo funcional completo | Integrantes 1–5 | T18, T19, T20 y T21 | Es una dependencia final inevitable. Se distribuye entre tres responsables y cada dueño entrega evidencias y horas, en vez de delegar toda la integración a una sola persona. |

### Contratos que deben acordarse antes de programar en paralelo

En una sincronización breve al inicio de la primera semana se deben fijar:

1. Nombres de enums y transiciones mínimas, en particular `REGISTRADA` y
   `PUBLICADA`, más los estados de sincronización con Bonita.
2. Payloads y respuestas de `/api/v1/emergencias`,
   `/api/v1/emergencias/{id}/lotes`,
   `/api/v1/emergencias/{id}/publicar`, `/api/v1/ofertas` y
   `/api/v1/convocatorias`.
3. Forma uniforme de errores y códigos HTTP para validación, autorización,
   conflictos de estado y fallos externos.
4. Matriz de roles y organización aplicable a cada operación.
5. Payload exacto de inicio de proceso y tratamiento de timeout incierto con
   Bonita.

Una vez acordados, los consumidores trabajan con fixtures de Pytest, RESPX o
MSW. Cambiar un contrato requiere avisar a sus consumidores en el mismo PR.

## Orden recomendado de integración

1. **Fundación:** T2 → T1 → T3, con T7 y T15 avanzando en paralelo sobre los
   contratos acordados.
2. **Seguridad y casos de uso base:** T7 → base de T8; luego T4, T5 y T6 en
   paralelo.
3. **Interfaces:** T9, T11 y T13 contra contratos estables y mocks.
4. **Lectura y transiciones:** T10, T12 y T14.
5. **Bonita:** T17 → T16, sin reintentar ciegamente un POST cuyo resultado sea
   incierto.
6. **Cierre:** T18 y T19; después T20 y T21 con horas y evidencias de todos.

Este orden indica precedencias de integración, no obliga a esperar para escribir
formularios, servicios o pruebas contra los contratos acordados.

## Acuerdos de trabajo compartidos

- Crear **una rama por issue** desde `develop` actualizado y usar los nombres de
  rama definidos en `../AGENTS.md`; no crear una rama por integrante.
- Integrar siempre mediante pull request pequeño. Cada integrante revisa de
  forma principal los PR del siguiente: 1 → 2 → 3 → 4 → 5 → 1. Seguridad y
  esquema pueden pedir una segunda revisión especializada cuando corresponda.
- Registrar tiempo real por issue desde el primer día. T20 consolida; no intenta
  reconstruir las horas al final.
- Cada issue funcional incluye sus pruebas proporcionales al riesgo. Las pruebas
  de T18 y T19 complementan, pero no reemplazan, las pruebas unitarias y de
  endpoints de T4–T17.
- Las integraciones automáticas usan RESPX/MSW y datos deterministas. Ninguna
  prueba automatizada depende de Internet o de un Runtime Bonita real.
- Antes de pedir revisión, ejecutar los checks del área modificada; antes de la
  entrega, ejecutar lint, pruebas, typecheck y build de todas las capas afectadas
  y verificar el check obligatorio `quality`.
- Los desvíos mayores a **0,5 h** o cualquier hallazgo que agregue alcance se
  registran en GitHub y se reequilibran explícitamente. No se transfieren tareas
  de manera informal ni se adelanta funcionalidad de Entrega 3.
