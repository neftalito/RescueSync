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
`REPRESENTANTE_ONG` y `AUDITOR_DIRECTIVO`. Los tres primeros crean o reutilizan
una organización del tipo correspondiente. El auditor no lleva el argumento
`--organizacion`.

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

Estas credenciales son exclusivamente locales. El seed guarda hashes Argon2 y
se niega a ejecutarse cuando `APP_ENV=production`.

## Endpoints de sesión

| Método | Ruta | Resultado |
| --- | --- | --- |
| `POST` | `/api/v1/auth/login` | Valida credenciales y establece la cookie. |
| `GET` | `/api/v1/auth/me` | Devuelve el contexto vigente y un token CSRF. |
| `POST` | `/api/v1/auth/logout` | Valida `X-CSRF-Token` y elimina la sesión. |

El login y los endpoints de health son públicos. `/auth/me` y `/auth/logout`
recargan el usuario y aplican la matriz RBAC antes de responder.

## Matriz funcional de la Entrega 2

| Operación | Rol habilitado |
| --- | --- |
| Registrar una emergencia | Operador Municipal |
| Gestionar y publicar lotes | Centro Coordinador Regional |
| Presentar una oferta | Representante de ONG |

Los cuatro roles pueden consultar y cerrar su sesión. Auditor/Directivo queda
autenticado y modelado, pero no recibe operaciones funcionales en esta entrega.
El frontend puede filtrar la navegación, pero cada endpoint debe volver a
autorizar mediante `requerir_operacion`.

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
