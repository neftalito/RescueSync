# Validación manual de T25, T26 y T27

Esta guía cubre [T25 / issue #4](https://github.com/neftalito/RescueSyncAPI/issues/4),
[T26 / issue #5](https://github.com/neftalito/RescueSyncAPI/issues/5) y
[T27 / issue #6](https://github.com/neftalito/RescueSyncAPI/issues/6). Los cambios
se revisan juntos en los PR [RescueSyncAPI #28](https://github.com/neftalito/RescueSyncAPI/pull/28)
y [RescueSync #45](https://github.com/neftalito/RescueSync/pull/45).

## Preparación

1. Usar las ramas de ambos PR y levantar cada proyecto con
   `docker compose up --build -d` desde su raíz. Aplicar migraciones antes de
   probar. Si ya están levantados, reconstruir para cargar el código nuevo.
2. En RescueSyncAPI ejecutar
   `docker compose run --rm api python -m app.scripts.seed`.
3. En RescueSync ejecutar
   `docker compose run --rm backend python -m app.scripts.seed`.
4. Abrir la web en `http://localhost:5173`, Swagger local en
   `http://localhost:8000/docs` y Swagger nacional en `http://localhost:8001/docs`.
   Ajustar URLs si se cambiaron puertos. El backend local debe alcanzar
   `NACIONAL_BASE_URL`; Compose usa `http://host.docker.internal:8001/api/v1`.
5. Para el registro, un administrador local debe crear una **ONG nueva sin UUID
   nacional** y un usuario representante asociado. Ingresar como ese usuario y
   cambiar su contraseña inicial si se solicita.

| ONG demo | Usuario | Contraseña local | Contraseña nacional |
| --- | --- | --- | --- |
| Ayuda Sin Fronteras | `ong@rescuesync.org` | `ong123` | `ong-nacional123` |
| Red Médica Solidaria | `redmedica@rescuesync.org` | `redmedica123` | `redmedica123` |

Si el seed ya se ejecutó, preserva contraseñas y cantidades editadas; los valores
iniciales sólo se esperan en datos nuevos. Todas las credenciales de esta tabla
son ejemplos públicos de desarrollo.

## T25: login JWT y autorización

| Caso | Acción | Resultado esperado |
| --- | --- | --- |
| Login válido | En Swagger nacional llamar `POST /api/v1/login` con `identificadorLogin=ong@rescuesync.org` y su contraseña nacional | `200`, `access_token`, `token_type=bearer`, `expires_in`; cabecera `Cache-Control: no-store` |
| Normalización | Repetir con ` ONG@RESCUESYNC.ORG ` | Login correcto con la misma cuenta |
| Credenciales incorrectas | Usar contraseña incorrecta o login inexistente | `401` y el mismo mensaje seguro, sin revelar si el usuario existe |
| Datos inválidos | Enviar login de sólo espacios o contraseña vacía | `422`, sin contraseña ni cuerpo enviado en la respuesta |
| Bearer | Usar Authorize con el JWT y consultar `GET /api/v1/me` | Cuenta con rol `ONG` y el UUID nacional de Ayuda Sin Fronteras |
| Sin token / token alterado | Quitar Authorize o cambiar un carácter de la firma del JWT | `401`; nunca datos del inventario |
| Expiración | En desarrollo configurar `JWT_ACCESS_SECONDS=60`, recrear la API, conectar y esperar más de 60 segundos; consultar stock / Actualizar listado | La credencial deja de funcionar; la web pide reconectar y conserva la sesión local. Restaurar la duración después |
| ONG ajena | Con JWT de Ayuda Sin Fronteras intentar GET/POST/PATCH bajo el UUID de Red Médica Solidaria | `403`; sin lecturas ni cambios en la otra ONG |
| Cuenta desactivada | En una base de prueba desactivar la cuenta después de emitir su JWT y volver a consultar `/me` | `401` con el JWT anterior |
| ONG suspendida/de baja | En una base de prueba cambiar el estado institucional después de emitir el JWT y consultar `/me` o inventario | `403` con el JWT anterior; los roles/estados se consultan de nuevo |

Para pruebas API, los UUID de las dos ONGs pueden obtenerse con `/me` al iniciar
sesión con cada cuenta. Las cuentas `ADMIN_NACIONAL` e `INTEGRACION`, si se
aprovisionan en un entorno de prueba, tienen permisos distintos: administración
puede gestionar inventario; integración sólo consulta y recibe `403` al escribir.
Ninguna de esas cuentas sirve para conectar la pantalla local de una ONG.

## T26: registro y asociación de la cuenta

| Caso | Acción | Resultado esperado |
| --- | --- | --- |
| Registro desde la web | Entrar con el representante nuevo, ir a Mis recursos → Registrar ONG en el Sistema Nacional y completar identificador institucional único, contacto, login único y contraseña de al menos 8 caracteres | Confirmación, UUID nacional y estado `PENDIENTE`; nombre tomado de la ONG local |
| Sin autovinculación | Después del alta mirar Mis recursos y, como administrador, la organización local | Continúa sin vínculo; no hay conexión ni inventario accesible aún |
| Verificar nueva identidad | Usar las nuevas credenciales en `POST /login` nacional y luego `/me` | `200`, rol `ONG`, `ongId` igual al UUID mostrado por la web |
| Estado y permisos | Revisar la fila nacional / respuesta del alta | ONG pendiente; sin habilitación administrativa ni certificaciones autoemitidas |
| Completar vínculo | Administrador local: Gestionar organizaciones → Editar → UUID nacional. Guardar el UUID mostrado; representante: Volver a consultar vinculación y conectar con sus credenciales | Vínculo correcto, conexión válida e inventario inicialmente vacío |
| Login duplicado | Registrar otra ONG usando un login existente, incluso con mayúsculas/espacios | `409`; no se crea la segunda ONG ni se cambia la cuenta original |
| Identificador institucional duplicado | Usar un login distinto pero el identificador institucional existente, incluso con mayúsculas | `409`; no se crea una cuenta huérfana ni se altera la ONG original |
| Validaciones | Dejar campos vacíos, poner contacto inválido o contraseña corta | Errores visibles y ninguna alta. Por API, `422` |
| Escalamiento | En `POST /ongs` nacional agregar `rol`, `estado` o `certificaciones`; en el adaptador local agregar `nombre` de otra ONG | `422`; sin persistir ONG/cuenta ni permisos |
| CSRF y rol local | Enviar el POST local sin CSRF con sesión válida, o desde un usuario que no sea representante ONG | `403` y sin llamada nacional. Sin sesión: `401` |
| Error seguro | Repetir un registro duplicado en el formulario | Mensaje accionable, campo de contraseña limpio y datos institucionales conservados |

El alta nacional y el vínculo local son dos pasos: no hay una transacción entre
las bases. Si un registro devuelve timeout, comprobar con login nacional y `/me`
si se creó antes de repetirlo. La aplicación no reintenta el POST automáticamente.

## T27: inventario y disponibilidad

| Caso | Acción | Resultado esperado |
| --- | --- | --- |
| Datos demo | Conectar Ayuda Sin Fronteras desde Mis recursos | Agua 5000 litros y 12 paramédicos en datos nuevos; total, comprometido y disponible visibles |
| Otra ONG | Entrar como Red Médica Solidaria y conectar su cuenta nacional | Sus 4 ambulancias y 20 paramédicos; inventario independiente |
| Identidad incorrecta | Estando como Ayuda Sin Fronteras intentar conectar con credenciales nacionales de Red Médica | Rechazo; no se guarda la conexión ni se muestra el inventario ajeno |
| Alta | Seleccionar una capacidad, código interno nuevo, nombre y cantidad positiva; registrar | Recurso visible, unidad del catálogo, comprometido `0.000`, disponible igual al total; corroborar con GET nacional |
| Decimales | Crear agua con `12.125` | Exactamente `12.125`, sin redondeos de floats |
| Cantidades inválidas | Probar `0`, `0.000`, negativo, más de 3 decimales, letras y más de 11 dígitos enteros, tanto en alta como en edición | Sin cambios; validación web y `422` en ambas APIs |
| Unidades discretas | Crear/editar paramédicos o ambulancias con `2.5` | Rechazo. Con `2` se permite |
| Código duplicado | Crear otro recurso con el mismo código dentro de la ONG | `409` y no aparece un recurso duplicado. Otra ONG puede usar ese código |
| Editar y persistir | Modificar agua a `5100.125`, guardar y recargar la página; comprobar el GET nacional | Total persistido y disponible recalculado |
| Edición simultánea | Dos navegadores/contextos: abrir edición del mismo recurso sin refrescar. Guardar en A y luego en B | A guarda; B recibe `409` por versión obsoleta. Actualizar listado carga el valor ganador |
| Desconexión / logout | Desconectar o cerrar sesión local y volver a entrar | Se exige conectar de nuevo; el stock nacional permanece |
| Vínculo administrativo | Quitar/cambiar UUID como administrador, o intentar reutilizar el de otra organización local | Quitar/cambiar revoca conexiones; duplicar UUID devuelve `409` y preserva el vínculo anterior |
| Caída nacional | Detener sólo la API nacional y consultar/guardar | Error seguro de comunicación; no hay reintentos automáticos de escrituras. Al restaurar, Actualizar listado permite comprobar el resultado |
| Navegador y móvil | Revisar Network/localStorage/cookies y recorrer la pantalla a 320 px y con teclado | El navegador consume sólo FastAPI local, sin JWT nacional almacenado; campos accesibles y sin desbordamiento horizontal |

### Stock comprometido: fixture de desarrollo

Los endpoints que crean/liberan compromisos corresponden a T32/T33. Para validar
manualmente T27 con reservas, preparar un recurso descartable con total `10` y
un compromiso activo de `4` en la base nacional de prueba; no usar datos reales.
Las fixtures `crear_datos` y `crear_compromiso` de
`RescueSyncAPI/tests/test_database_models.py` reproducen las relaciones necesarias
(emisor, proyecto, operación idempotente, compromiso e ítem).

1. Consultar el inventario: total `10.000`, comprometido `4.000`, disponible `6.000`.
2. Enviar PATCH con total `3` y la versión vigente: `409`, total conservado en `10`.
   La pantalla también debe impedirlo si la ONG del fixture está vinculada.
3. Editar a `4`: se permite; disponible `0.000`.
4. Liberar el compromiso en el fixture manteniendo sus ítems y los campos de
   auditoría `liberadoEn` / `liberadoPorId`: comprometido `0.000`, disponible `4.000`.
5. Para el locking, usar dos transacciones: en A bloquear el recurso con
   `SELECT ... FOR UPDATE`; en B enviar PATCH que reduciría el total por debajo
   de una reserva nueva. A registra la reserva y confirma; B debe recalcular
   después del bloqueo y devolver `409`.

Las pruebas automatizadas del PR cubren estos casos sobre PostgreSQL con
conexiones independientes, además de la validación manual sugerida aquí.
