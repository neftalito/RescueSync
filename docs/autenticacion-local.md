# Autenticación local

La Entrega 2 usa sesiones locales firmadas en una cookie `HttpOnly`; no usa el
JWT del Sistema Nacional previsto para la Entrega 3. En cada petición autenticada,
el backend vuelve a cargar desde PostgreSQL el usuario, la organización y el rol
vigentes. Las operaciones que cambian estado también validan el token CSRF.

## Crear un usuario

La contraseña se solicita de forma interactiva para no mostrarla ni incluirla en
el historial del shell:

```bash
docker compose run --rm backend python -m app.scripts.create_user \
  --email operador@rescuesync.org \
  --rol OPERADOR_MUNICIPAL \
  --organizacion "Municipio del Delta"
```

Los roles disponibles son `OPERADOR_MUNICIPAL`, `COORDINADOR_REGIONAL`,
`REPRESENTANTE_ONG`, `AUDITOR_DIRECTIVO` y `ADMINISTRADOR`. Los tres primeros
crean o reutilizan una organización del tipo correspondiente. Auditor y
administrador no llevan el argumento `--organizacion`.

## Administrador inicial

Antes de aceptar peticiones, FastAPI comprueba en desarrollo y producción que
exista al menos un administrador activo. Si no lo encuentra, crea una cuenta de
forma transaccional con estas variables:

| Variable | Valor por defecto |
| --- | --- |
| `ADMIN_EMAIL` | `admin@rescuesync.org` |
| `ADMIN_INITIAL_PASSWORD` | `administrador123` |

La contraseña inicial queda marcada como temporal y debe cambiarse en el primer
ingreso. El bootstrap es idempotente: si ya existe un administrador activo no
modifica cuentas ni restablece contraseñas. Si `ADMIN_EMAIL` pertenece a una
cuenta incompatible, el backend no arranca para evitar tomar control de ella.

Los valores por defecto son públicos y sirven para facilitar el primer acceso.
En producción deben sobreescribirse antes del primer arranque y comunicarse por
un canal seguro. Ninguna contraseña se imprime en los logs.

## Datos de desarrollo

Para crear un escenario completo:

```bash
docker compose run --rm backend python -m app.scripts.seed
```

El seed es idempotente y no duplica registros. Crea cuatro organizaciones, una
cuenta activa por rol, una emergencia registrada, otra publicada, lotes, una
convocatoria abierta y una oferta parcial.

| Rol | Correo | Contraseña de desarrollo |
| --- | --- | --- |
| Operador municipal | `municipio@rescuesync.org` | `municipio123` |
| Coordinador regional | `coordinador@rescuesync.org` | `coordinador123` |
| Representante de ONG | `ong@rescuesync.org` | `ong123` |
| Auditor / Directivo | `auditor@rescuesync.org` | `auditor123` |
| Administrador | `admin@rescuesync.org` | `administrador123` |

Estas credenciales son exclusivamente locales. El seed guarda hashes Argon2 y
se niega a ejecutarse cuando `APP_ENV=production`.

## Endpoints de sesión

| Método | Ruta | Resultado |
| --- | --- | --- |
| `POST` | `/api/v1/auth/login` | Valida credenciales y establece la cookie. |
| `GET` | `/api/v1/auth/me` | Devuelve el contexto vigente y un token CSRF. |
| `POST` | `/api/v1/auth/logout` | Valida `X-CSRF-Token` y elimina la sesión. |
| `POST` | `/api/v1/auth/password` | Cambia la contraseña propia y renueva la sesión. |

El login y los endpoints de health son públicos. `/auth/me` y `/auth/logout`
recargan el usuario y aplican la matriz RBAC antes de responder.

## Matriz funcional de la Entrega 2

| Operación | Rol habilitado |
| --- | --- |
| Registrar una emergencia | Operador Municipal |
| Gestionar y publicar lotes | Centro Coordinador Regional |
| Presentar una oferta | Representante de ONG |
| Gestionar usuarios | Administrador |

Los cinco roles pueden consultar, cambiar su contraseña y cerrar su sesión. Auditor/Directivo queda
autenticado y modelado, pero no recibe operaciones funcionales en esta entrega.
El frontend puede filtrar la navegación, pero cada endpoint debe volver a
autorizar mediante `requerir_operacion`.

El rol Administrador puede listar, crear, editar, desactivar/reactivar usuarios
y asignar contraseñas temporales. Las cuentas operativas solo pueden asociarse a
una organización activa del tipo compatible. La baja es lógica para conservar
la trazabilidad y no se permite quitar el acceso propio ni dejar el sistema sin
un administrador activo.

## Contraseñas y sesiones

Las cuentas creadas desde la administración y las contraseñas restablecidas son
temporales. Hasta reemplazarlas, el backend solo permite consultar la sesión,
cambiar la contraseña y cerrar sesión. El cambio personal exige la contraseña
actual.

La cookie y el token CSRF incluyen una versión de sesión. Cambiar o restablecer
una contraseña y desactivar una cuenta incrementan esa versión: las cookies
anteriores dejan de ser válidas. Quien cambia su propia contraseña recibe una
cookie renovada y puede continuar trabajando.

### Endpoints administrativos

| Método | Ruta | Resultado |
| --- | --- | --- |
| `GET` | `/api/v1/usuarios` | Lista cuentas activas e inactivas. |
| `POST` | `/api/v1/usuarios` | Crea una cuenta con contraseña temporal. |
| `PATCH` | `/api/v1/usuarios/{id}` | Edita email, rol, organización o estado. |
| `DELETE` | `/api/v1/usuarios/{id}` | Desactiva sin borrar la trazabilidad. |
| `PUT` | `/api/v1/usuarios/{id}/password` | Asigna una contraseña temporal. |
| `GET` | `/api/v1/organizaciones` | Lista organizaciones activas asignables. |

Las operaciones mutables exigen `X-CSRF-Token`. Los controles del frontend son
solo navegación; FastAPI vuelve a cargar y autorizar al administrador en cada
petición.

## Configuración segura

En desarrollo, un `SESSION_SECRET` vacío genera una clave efímera al iniciar el
backend; cada reinicio invalida las sesiones abiertas. En producción,
`APP_ENV=production` exige una clave estable de al menos 32 caracteres, generada
fuera del repositorio, por ejemplo:

```bash
openssl rand -hex 32
```

Las cookies son `Secure` por defecto fuera de desarrollo. `SameSite=None` solo
es válido junto con cookies seguras.
