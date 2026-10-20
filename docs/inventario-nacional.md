# Mis recursos: inventario nacional desde RescueSync

El representante de ONG encuentra **Gestionar mis recursos** en su dashboard.
`/mis-recursos` presenta dos tarjetas de navegación, con un encabezado consistente
con las otras vistas:

- **Ver mis certificaciones** → `/mis-recursos/certificaciones`: acreditaciones,
  vigencia, capacidades habilitadas y catálogo de referencia.
- **Gestionar inventario** → `/mis-recursos/inventario`: registrar recursos,
  consultar cantidades totales/comprometidas/disponibles y editar el total.

Al editar un recurso registrado, el formulario se abre en un modal centrado,
con foco en la cantidad actual. Se cierra con Cancelar, la X o Escape y devuelve
el foco al botón de edición. Mientras guarda, los controles y el cierre quedan
deshabilitados. Si la operación falla, el modal conserva la cantidad ingresada
y muestra el error para permitir corregirla o reintentar.

La vista de certificaciones distingue cuatro tarjetas: estado institucional,
capacidades habilitadas, historial de acreditaciones y catálogo nacional. Las
capacidades, el historial y el catálogo tienen desplazamiento vertical dentro de
sus tarjetas. El historial y el catálogo muestran los registros como acordeones.
Se puede abrir un registro por lista;
el catálogo es una referencia y no implica que la ONG posea esas acreditaciones.

Cada pantalla consulta únicamente sus datos y permite volver a Mis recursos o al
inicio. Las rutas requieren una sesión de representante de ONG y conservan los
estados de carga, error, vinculación y revisión del acceso nacional. La capacidad
del catálogo define la unidad y si admite fracciones; comprometido y disponible
se muestran como datos calculados.

## Preparar y probar los datos de ejemplo

Configurar la cuenta `INTEGRACION` del emisor según
[Alta y acceso nacional automático](./acceso-nacional-automatico.md), además de
`NACIONAL_BASE_URL` y una `NACIONAL_ENCRYPTION_KEY` estable en el `.env` de RescueSync.
La URL debe apuntar a la API donde se quieren crear las ONG, por ejemplo Render.
Luego recrear el backend si ya estaba levantado con
`docker compose up -d --force-recreate backend`. El seed y el backend deben usar
la misma clave Fernet
estable. Si falta, el seed local falla con un mensaje accionable antes de crear
datos; no informa éxito con un acceso incompleto.

Con la API nacional disponible y migrada, ejecutar desde RescueSync:

```bash
docker compose up --build -d
docker compose run --rm backend python -m app.scripts.seed
```

El seed confirma primero los datos locales y las solicitudes de alta con secretos
aleatorios cifrados. Después llama a `/integraciones/ongs/{referencia}` para crear
cada ONG nacional en estado `PENDIENTE` y su cuenta `TECNICA_ONG`. Guarda los UUID y
el login devueltos por esa API; no inventa vínculos nacionales. No es necesario
ejecutar el seed nacional ni importar credenciales por consola.

No carga recursos, certificaciones ni habilitaciones. El inventario de las ONG
nuevas empieza vacío y se puede cargar manualmente en **Mis recursos**:

| ONG | Cuenta local | Contraseña local |
| --- | --- | --- |
| Ayuda Sin Fronteras | `ong@rescuesync.org` | `ong123` |
| Red Médica Solidaria | `redmedica@rescuesync.org` | `redmedica123` |

Ante un timeout o rechazo nacional, el comando termina con código 1 y conserva
los datos locales. Corregir la causa y repetir el mismo comando reutiliza la
referencia, el contenido y el secreto de cada solicitud, incluso si la API ya
confirmó el alta antes del timeout. Las altas completadas no se duplican.

Las nuevas ONG creadas desde Administración de organizaciones se registran y vinculan con
su cuenta técnica automáticamente. El identificador es generado y el contacto es
opcional. Mis recursos queda disponible al completar el alta.

Si la API no responde, la tarjeta de la organización permite **Reintentar alta
nacional**. Las ONG locales anteriores sin vínculo también pueden completar el
registro desde Mis recursos, sin ingresar credenciales ni identificadores.
Si una versión anterior del seed guardó UUID demo sin crear sus registros
nacionales, volver a ejecutar el seed actualizado los recupera automáticamente:
verifica con la cuenta de integración que la ONG anterior responde `404` en su
perfil de certificaciones y sólo entonces reemplaza el vínculo y la credencial
pública del fixture por un alta real. Un rechazo de autenticación, un timeout o
una ONG existente no permiten reemplazar el vínculo. Los accesos importados,
rotados o revocados de ONG existentes se conservan y requieren el procedimiento
administrativo de recuperación cuando corresponda.

`app.scripts.seed_masivo` conserva su carga sintética independiente; consultar su
[modalidad e integración nacional](./seed-masivo.md).

## Configuración

| Variable del backend local | Valor de Compose | Uso |
| --- | --- | --- |
| `NACIONAL_BASE_URL` | `http://host.docker.internal:8001/api/v1` | URL completa del prefijo de RescueSyncAPI, accesible desde el backend |
| `NACIONAL_TIMEOUT_SECONDS` | `10` | Timeout HTTP explícito |
| `NACIONAL_APROVISIONAMIENTO_LOGIN/PASSWORD` | Vacío | Cuenta INTEGRACION del emisor para altas automáticas |
| `NACIONAL_ENCRYPTION_KEY` | Vacío | Clave Fernet propia para credenciales institucionales |

Si la API nacional publica otro puerto, actualizar `NACIONAL_BASE_URL`. Fuera de
Docker, usar `http://localhost:8001/api/v1`. En producción, usar la URL HTTPS del
Sistema Nacional y configurar los secretos propios de ambos servicios.

## Contratos y permisos

El navegador sólo llama a FastAPI local, con cookie y CSRF en las escrituras.
El backend obtiene la ONG desde el usuario vigente, busca el UUID vinculado e
invoca a RescueSyncAPI con el JWT nacional de esa ONG. El inventario permanece en
PostgreSQL nacional. No se reutiliza el token de Bonita ni se modifica el BPM.

| Método y ruta local | Operación |
| --- | --- |
| `GET /api/v1/mi-ong/conexion` | Estado de vinculación y conexión, sin JWT |
| `POST /api/v1/mi-ong/registro-nacional` | Registrar la ONG local sin vínculo y su cuenta nacional pendiente; sólo representante ONG |
| `GET /api/v1/mi-ong/capacidades` | Catálogo nacional |
| `GET /api/v1/mi-ong/recursos` | Inventario de la ONG del usuario |
| `POST /api/v1/mi-ong/recursos` | Registrar recurso propio |
| `PATCH /api/v1/mi-ong/recursos/{id}` | Editar total enviando `actualizadoEn` |
| `POST /api/v1/organizaciones/{id}/aprovisionamiento-nacional` | Completar/reintentar alta automática; sólo administrador + CSRF |
| `PATCH /api/v1/organizaciones/{id}/vinculo-nacional` | Vincular por UUID o desvincular; sólo administrador |

La conexión es institucional: una cuenta técnica de rol `ONG` por organización.
El backend guarda secreto y JWT cifrados con `NACIONAL_ENCRYPTION_KEY`, compartida
entre workers e independiente de `SESSION_SECRET`. Renueva el token al faltar o
restarle menos de 30 segundos. No utiliza contraseñas personales de las ONG.
Logout y cambios de contraseña local no desconectan a otros representantes.
Los estados son `LISTA`, `SIN_CONFIGURAR` y `REQUIERE_REVISION`; `conectada`
solamente informa si existe un token temporal vigente. Ningún secreto llega al
navegador. Los antiguos POST/DELETE de conexión manual se retiran.

El formulario de registro y su adaptador validan contraseña de al menos ocho
caracteres, contacto e identificador institucional. No aceptan un nombre ajeno,
rol, habilitación ni certificación desde el navegador. El administrador conserva
el control del mapping institucional. Contraseñas de registro se
eliminan del estado de mutaciones al terminar y se limpia el campo tras un error.
Un login o identificador institucional repetido devuelve `409` y conserva los
datos existentes. El registro no se reintenta automáticamente: ante `504`, puede
haberse confirmado nacionalmente; comprobar con el login y `/me` en Swagger antes
de repetirlo. El vínculo administrativo es un paso separado entre ambas bases.

Registrar y editar recursos exige total mayor que cero, hasta tres decimales y
once dígitos enteros. La disponibilidad puede ser cero cuando el total está
comprometido. Personal y vehículos sólo admiten enteros.

La API nacional vuelve a autorizar cada operación y serializa las ediciones con
los compromisos mediante locking. Un `409` exige revisar stock, código o versión.
Ante timeout, no se reintenta una escritura automáticamente: actualizar el listado
permite comprobar si el cambio quedó confirmado antes de repetirlo. Los errores
externos se traducen sin exponer cuerpos internos ni secretos.

## Verificación

Además de lint, typecheck, build y suites completas de ambos repositorios,
`backend/tests/test_inventario.py` prueba el adaptador con RESPX y PostgreSQL,
y `MisRecursosPage.test.tsx` cubre conexión, altas, unidades, edición, conflicto y
reconexión. La API nacional prueba edición concurrente con una reserva real.

Referencia del cifrado: [Fernet](https://cryptography.io/en/latest/fernet/).

La [lista de pruebas manuales T25–T27](./pruebas-manuales-t25-t27.md) detalla la
preparación, los casos y el resultado esperado para los dos PR.
