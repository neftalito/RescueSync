# Mis certificaciones nacionales — T28

En **Mis recursos**, una ONG con mapping y conexión nacional puede consultar
sus acreditaciones y capacidades habilitadas. El navegador sólo llama al
backend de RescueSync; el JWT nacional permanece cifrado en el servidor.

## Preparación y recorrido

1. Integrar la API nacional de T28 y levantar ambos stacks según
   [inventario nacional](./inventario-nacional.md).
2. En RescueSyncAPI, ejecutar `python -m app.scripts.seed` mediante Compose.
   En RescueSync, ejecutar su seed. Se conservan los mismos mappings UUID de
   Ayuda Sin Fronteras y Red Médica Solidaria.
3. Aprovisionar el [acceso automático por ONG](./acceso-nacional-automatico.md),
   ingresar como representante local y abrir **Mis recursos**.
4. Consultar **Mis certificaciones**: estado institucional, momento de evaluación,
   capacidades por riesgo y el historial vigente/futuro/vencido/revocado.
5. Abrir **Catálogo nacional de certificaciones** para ver definiciones y
   revisiones. Ese catálogo no significa que la ONG posea esas credenciales.

Ayuda Sin Fronteras tiene habilitación institucional y credencial sanitaria
vigente: paramédicos hasta `ALTA` y ambulancias hasta `MEDIA`. La credencial
crítica vencida no eleva ese permiso. También hay ejemplos futura y revocada.
Red Médica Solidaria queda pendiente aunque posea una credencial vigente: el
registro no sustituye la verificación institucional.

Las fechas demo quedan fijadas en la primera ejecución nacional, por lo que
pueden vencer con el tiempo. Repetir el seed no desplaza fechas ni revive
revocaciones. La carga administrativa oficial está documentada en
[RescueSyncAPI](https://github.com/neftalito/RescueSyncAPI/blob/feature/t28-certificaciones/docs/certificaciones.md).

## Servicios locales

| Ruta local | Consulta nacional | Acceso |
| --- | --- | --- |
| `GET /api/v1/mi-ong/catalogo-certificaciones` | `GET /api/v1/certificaciones` | Representante ONG con conexión vigente. |
| `GET /api/v1/mi-ong/certificaciones` | `GET /api/v1/ongs/{uuid}/certificaciones` | Representante ONG, UUID obtenido del mapping del usuario. |

Las rutas reutilizan `UsuarioInventario`, `credencial`, el cliente HTTPX nacional
y la renovación automática por ONG. No aceptan un UUID de ONG del navegador; la API
nacional vuelve a autorizar. El adaptador valida los DTO y que el `ongId`
devuelto coincida con el solicitado. No crea otra fuente de certificaciones en
PostgreSQL local y no requiere migración nueva.

Ante un `401` nacional se renueva el token y se repite la consulta una sola vez.
Una credencial técnica rechazada requiere revisión administrativa. Timeout,
caída y respuesta inválida devuelven `504`, `503` y `502`, sin secretos.
Las consultas llevan `no-store`. No se solicitan credenciales a representantes.

TanStack Query consulta el perfil cada minuto y al actualizar. Las claves incluyen
usuario y UUID nacional. Ante rechazo se vuelve a consultar el estado de acceso.
El cierre de sesión limpia la caché
general. El perfil muestra su hora de evaluación: no autoriza acciones futuras
ni garantiza stock. Las consultas pueden fallar independientemente del inventario
y ofrecen actualización manual. Los formularios no permiten autoacreditarse.

## Verificación manual de este corte

- Credencial vigente: revisar capacidades y niveles permitidos por separado.
- Vencida: historia visible y motivo, sin elevar competencia.
- Futura/revocada: visible con su estado, sin contribuir a capacidades.
- ONG pendiente: mensaje institucional y ausencia de capacidades efectivas.
- Catálogo vacío: mensaje de ausencia de certificaciones, no error de conexión.
- Caída nacional: mensaje seguro y reintento; no mostrar habilitación como si
  la consulta fallida la hubiese confirmado.
- JWT vencido: renovación transparente. Credencial revocada: revisión administrativa.
- Cuenta de otra ONG: conexión denegada. Otro rol local: GET denegado.

El backend tiene pruebas RESPX de contrato, mapping, JWT, errores y roles. La
pantalla se prueba con Vitest/Testing Library/MSW: estados de vigencia, perfil,
historial vacío, pendiente, reintento y acceso automático. Se mantienen las pruebas
existentes de inventario, onboarding y CSRF.

## Orden y condiciones de integración de los PRs

Integrar primero el contrato de certificaciones en RescueSyncAPI, luego este
consumidor. Ambos deben obtener `quality` exitoso y mantener los mismos campos,
enums y fechas camelCase. Las variables existentes `NACIONAL_BASE_URL` y
`NACIONAL_TIMEOUT_SECONDS` son suficientes para este corte.

No se modifica `RescueSync-1.2.bar`: la consulta personal de certificaciones
funciona sin un conector BPM. El issue nacional se referencia sin cierre automático;
estos PRs entregan la consulta T28 y su integración en la aplicación local.

Para usar esos datos en el proceso automático debe completarse el trabajo
coordinado siguiente antes de declarar la integración de Entrega 3 terminada:

| Tarea | Cambio necesario |
| --- | --- |
| T31 nacional | `POST /validaciones` con perfiles por oferta/versión/participante/lote/aporte. Reutilizar vigencia y riesgo; no guardar ofertas nacionalmente. |
| T34 local | Snapshot publicado con capacidad/riesgo y aportes vinculados a recursos/ONGs nacionales; cantidades nuevas como strings decimales. Migraciones y formularios proporcionales. |
| T36 local/BPM | Obtener `.bos` o reconstruir en Studio, nueva versión de pool y único `.bar`; implementar el conector de `Validar Oferta`, login técnico JWT y callback local idempotente de perfiles. |
| T36 cobertura | Evaluar cobertura compatible y conservar `REABRIR`, `REFORMULAR`, `CONTINUAR_PARCIAL`. Una ronda anterior no actualiza perfiles de otra ronda. |
| Configuración BPM | Reemplazar el default reservado `http://national-api:8000` por URL alcanzable entre stacks, agregar host-gateway a Bonita e inyectar secretos técnicos/timeouts al desplegar. |
| Versionado BPM | Actualizar `BONITA_PROCESS_VERSION`, `deploy.py`, contratos, callbacks, prueba del `.bar` y E2E controlada en el mismo PR. Conservar casos de versiones anteriores. |
| T32/T37 | Revalidar acreditaciones y stock después de locks antes de comprometer; la consulta de T28 no reserva inventario. |

Bonita ya consulta ofertas consolidadas en 1.2; no duplicar ese conector ni
descargar el catálogo para repetir las reglas en Groovy. Bonita debe invocar
T31; la autoridad sobre las acreditaciones sigue siendo la API nacional.
Un fallo técnico deja pendiente la evaluación, no habilita por defecto.

Estos pasos adicionales requieren sus propios PRs y evidencias. Mergear la
consulta local no acredita que el BPM valide o comprometa recursos. Los PRs de
T28 quedan abiertos para revisión, sin merge ni cierre automático.

## Entorno de pruebas

Construir también la imagen `migrate` antes de aplicar Alembic: una imagen
anterior puede no incluir `20261008_0008`, aunque el backend use modelos nuevos.
Esa revisión de inventario/mapping es una dependencia previa, no una migración
creada por T28.

Para las suites, usar una base descartable vacía y las identidades demo de
`.env.example`. Un volumen de desarrollo con contraseñas ya cambiadas no es
equivalente: el seed conserva esas contraseñas. Se verificaron las 374 pruebas
del backend (una E2E de Runtime omitida), las 95 del frontend, lint, typecheck y
build. La validación BPM con un Runtime real sigue correspondiendo al cambio T36.
