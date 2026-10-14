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
requiere usar su propia cuenta nacional. El escenario T28 y la nueva consulta
personal se describen en [Mis certificaciones](./certificaciones-nacionales.md).
La ONG no puede emitir acreditaciones desde la pantalla.

Para una ONG fuera del seed y sin vínculo, abrir **Mis recursos → Registrar ONG
en el Sistema Nacional**. Ingresar identificador institucional, email de contacto
y credenciales nuevas. Se toma el nombre de la organización local y se crea la
ONG nacional en estado `PENDIENTE`. La pantalla muestra el UUID que se debe
compartir con el administrador. No inicia una conexión ni establece el vínculo.
También se puede registrar directamente con `POST /api/v1/ongs` de RescueSyncAPI.
Como administrador local, ir a **Gestionar organizaciones →
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
| `POST /api/v1/mi-ong/registro-nacional` | Registrar la ONG local sin vínculo y su cuenta nacional pendiente; sólo representante ONG |
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

El formulario de registro y su adaptador validan contraseña de al menos ocho
caracteres, contacto e identificador institucional. No aceptan un nombre ajeno,
rol, habilitación ni certificación desde el navegador. El administrador conserva
el control del mapping institucional. Contraseñas de registro/conexión se
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
