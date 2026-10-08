# Mis recursos: inventario nacional desde RescueSync

El representante de ONG encuentra **Gestionar mis recursos** en su dashboard.
`/mis-recursos` permite conectar la cuenta nacional, consultar stock, registrar
recursos y editar su cantidad total. La capacidad del catálogo define la unidad y
si admite fracciones. Comprometido y disponible se muestran como datos calculados.

## Preparar y probar los datos de ejemplo

Levantar ambos proyectos desde sus propias raíces. Primero, en RescueSyncAPI:

```bash
docker compose up --build -d
docker compose run --rm api python -m app.scripts.seed
```

Luego, en RescueSync:

```bash
docker compose up --build -d
docker compose run --rm backend python -m app.scripts.seed
```

La nueva migración local agrega `organizacion.ong_nacional_id` y
`conexion_nacional`; el servicio `migrate` la aplica antes de arrancar el backend.
Los seeds de ambos proyectos comparten dos UUID demo explícitos y pueden ejecutarse
en cualquier orden. El seed local no escribe inventario nacional ni hace llamadas
HTTP. El seed nacional carga los recursos faltantes y preserva sus cantidades si
ya fueron editados. Una vinculación local demo distinta no se sobrescribe.

| ONG | Cuenta | Contraseña local | Contraseña nacional | Inventario inicial |
| --- | --- | --- | --- | --- |
| Ayuda Sin Fronteras | `ong@rescuesync.org` | `ong123` | `ong-nacional123` | Agua: 5000 litros; paramédicos: 12 personas |
| Red Médica Solidaria | `redmedica@rescuesync.org` | `redmedica123` | `redmedica123` | Ambulancias: 4 vehículos; paramédicos: 20 personas |

Ingresar a RescueSync con una cuenta local y abrir **Mis recursos**. Conectar con
las credenciales nacionales de esa misma ONG. Registrar un recurso y editar su
total; comprobar luego el stock en `/docs` de RescueSyncAPI. Cambiar de ONG local
requiere usar su propia cuenta nacional. Las cuentas demo no otorgan certificaciones.

Para una ONG fuera del seed, registrar su cuenta nacional con `POST /api/v1/ongs`
de RescueSyncAPI. Como administrador local, ir a **Gestionar organizaciones →
Editar → UUID de la ONG nacional** y guardar el UUID verificado. Vacío elimina la
vinculación. Guardar desconecta las cuentas nacionales de sus representantes.
El representante no puede establecer esta relación por sí mismo.

## Configuración

| Variable del backend local | Valor de Compose | Uso |
| --- | --- | --- |
| `NACIONAL_BASE_URL` | `http://host.docker.internal:8001/api/v1` | URL completa del prefijo de RescueSyncAPI, accesible desde el backend |
| `NACIONAL_TIMEOUT_SECONDS` | `10` | Timeout HTTP explícito |

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
| `POST /api/v1/mi-ong/conexion` | Login nacional y verificación de pertenencia |
| `DELETE /api/v1/mi-ong/conexion` | Eliminar credencial temporal |
| `GET /api/v1/mi-ong/capacidades` | Catálogo nacional |
| `GET /api/v1/mi-ong/recursos` | Inventario de la ONG del usuario |
| `POST /api/v1/mi-ong/recursos` | Registrar recurso propio |
| `PATCH /api/v1/mi-ong/recursos/{id}` | Editar total enviando `actualizadoEn` |
| `PATCH /api/v1/organizaciones/{id}/vinculo-nacional` | Vincular por UUID o desvincular; sólo administrador |

Una cuenta técnica o administrativa nacional no puede usarse para conectar la
pantalla de una ONG. La contraseña nacional se utiliza sólo para el login remoto
y no se persiste. El JWT se cifra con Fernet en PostgreSQL local, ligado al usuario,
versión de sesión, ONG nacional y expiración. No aparece en respuestas, cookies o
localStorage. La clave de cifrado se deriva del secreto de sesión con un propósito
separado; configurar `SESSION_SECRET` estable para compartirlo entre workers.
Rotarlo invalida conexiones anteriores y exige reconectar. Cerrar la sesión local
elimina la conexión nacional de ese usuario; el cambio de contraseña invalida su
versión. No hay refresh automático.

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
