# Alta y acceso nacional automático por ONG

Al crear una organización de tipo ONG en **Administración de organizaciones**, el
backend registra su identidad nacional, crea la cuenta `TECNICA_ONG`, guarda el
vínculo y cifra su secreto. Sólo se requiere nombre y tipo; el correo de contacto
es opcional. El identificador institucional se genera automáticamente en la API
nacional como `rs:<UUID emisor sin guiones>:<referencia sin guiones>`.

El representante sólo inicia sesión local. Puede consultar y gestionar inventario
sin importar archivos, elegir contraseñas nacionales ni vincular UUID manualmente.
La institución se crea `PENDIENTE`: esto permite inventario, pero no concede
certificaciones ni habilitación para adjudicaciones.

## Preparación única del entorno

1. Desplegar primero RescueSyncAPI y aplicar `alembic upgrade head`. Preparar una
   cuenta `INTEGRACION` para el sistema emisor con
   [su comando de bootstrap](../../RescueSyncAPI/docs/acceso-automatico-ong.md).
2. Configurar en todos los workers locales:

   - `NACIONAL_BASE_URL`: URL de `/api/v1` nacional.
   - `NACIONAL_APROVISIONAMIENTO_LOGIN` y `NACIONAL_APROVISIONAMIENTO_PASSWORD`:
     credenciales de integración del emisor, conservadas únicamente en el servidor.
     En Compose, el login predeterminado es `integracion-rescuesync` y la
     contraseña toma `NACIONAL_INTEGRACION_PASSWORD` si no tiene un override propio.
   - `NACIONAL_ENCRYPTION_KEY`: clave Fernet propia, estable y compartida entre
     workers, independiente de `SESSION_SECRET`.

   Generar la clave fuera del repositorio:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

3. Aplicar `alembic upgrade head` local y arrancar el backend con esas variables.
   Compose ya propaga las dos variables de aprovisionamiento. No hay pasos
   administrativos adicionales por cada nueva ONG.

La configuración de catálogo permite una cuenta independiente. En Compose,
cuando `NACIONAL_CATALOGO_LOGIN` y `NACIONAL_CATALOGO_PASSWORD` están vacías,
reutiliza la cuenta de integración para consultar; crear capacidades sigue
exigiendo un `ADMIN_NACIONAL` configurado explícitamente para catálogo. No usar
una cuenta personal ONG ni un administrador nacional en las variables de alta.
No cambiar la cuenta emisora a otra instalación con altas pendientes: la referencia
se interpreta dentro del emisor autenticado.

## Fallos y recuperación

- El alta local y su solicitud cifrada se confirman **antes** de llamar a la API.
  No se mantienen locks de PostgreSQL durante HTTP.
- Si la API falla o responde fuera de tiempo, la ONG queda creada localmente. La
  interfaz informa que el alta nacional está pendiente y ofrece **Reintentar alta
  nacional** en su tarjeta. No crear otra organización.
- `POST /api/v1/organizaciones/{id}/aprovisionamiento-nacional`, sólo administrador
  con CSRF, vuelve a usar la misma referencia, nombre, contacto y secreto.
- La API nacional confirma ONG, cuenta y correlación juntas. Repetir la misma
  referencia y contenido devuelve la misma identidad; cambiar el contenido produce
  `409`. Una cuenta revocada o una ONG suspendida no se reactiva con reintentos.
- **Mis recursos → Gestionar inventario → Registrar ONG en el Sistema Nacional** aplica el mismo flujo
  a una ONG local anterior sin vínculo. Pide sólo correo opcional, autovincula y
  habilita el inventario al terminar. El administrador también puede iniciar el
  alta con el botón de reintento y sin correo.
- Las solicitudes guardadas son inmutables para reconciliar timeouts. Renombrar
  la organización local durante un alta pendiente no altera el alta ya enviada.
- La vinculación manual sigue disponible para registros nacionales anteriores.
  No se reclaman registros existentes por nombre ni se reemplazan sus cuentas.
  Una ONG anterior ya vinculada y sin acceso conserva el procedimiento de
  importación descrito abajo. El seed demo usa el mismo aprovisionamiento para
  crear las dos ONG y sus cuentas técnicas; no se modifican otras identidades anteriores.
- Cambiar o eliminar un vínculo borra la solicitud y el acceso anteriores; una
  respuesta atrasada no puede restablecerlos. Guardar el mismo UUID los conserva.

## Operación y credenciales anteriores

`GET /api/v1/mi-ong/conexion` devuelve `LISTA`, `SIN_CONFIGURAR` o
`REQUIERE_REVISION`. `LISTA` permite operar aunque todavía no haya JWT en caché.
Los JWT técnicos duran cinco minutos; se renuevan cuando faltan o quedan menos de
30 segundos. No llegan al navegador. Cerrar sesión local no elimina el acceso.

Ante `401`, se renueva una vez y sólo se reintentan consultas. Las escrituras de
inventario no se repiten automáticamente. Un `403` de negocio no se interpreta
como expiración. Credenciales revocadas quedan en revisión.

Para recuperar una credencial técnica anterior o rotada, el administrador nacional
exporta su archivo privado y el operador local ejecuta:

```bash
python -m app.scripts.acceso_nacional --login admin@example.org --organizacion ID_LOCAL --archivo /tmp/credencial-ong.json
```

El comando pide la contraseña del administrador local y exige un archivo regular
`0600`. Verifica cuenta, rol, propósito y pertenencia mediante `/me`. Eliminar las
copias del archivo después de importarlo. Cambiar la clave Fernet exige recuperar
las credenciales; los reintentos no regeneran un secreto que ya fue enviado.

## Validación y rollback

Las pruebas cubren alta sin correo ni identificador ingresado, RBAC/CSRF, cifrado,
timeout y reintento estable, pertenencia y concurrencia nacional. Las migraciones
locales se prueban en ambas direcciones sobre schemas descartables.

El downgrade local descarta las solicitudes de aprovisionamiento y conserva los
accesos ya completados. Respaldar las referencias pendientes antes de un rollback:
un nuevo upgrade no puede reconstruir el secreto de una solicitud descartada.


## Seeds de desarrollo

`python -m app.scripts.seed` confirma los datos locales y aprovisiona las dos ONG
demo y sus cuentas técnicas en la API de `NACIONAL_BASE_URL`. Requiere la clave
Fernet estable y las credenciales de integración descritas arriba. No necesita
ejecutar el seed de RescueSyncAPI ni carga inventario o certificaciones.

Un fallo nacional conserva la solicitud cifrada para repetir el mismo comando.
Los UUID sintéticos del seed anterior sólo se reemplazan si la API confirma que
esa ONG no existe y la credencial local sigue siendo la pública del fixture.
Los vínculos existentes, accesos importados y revocaciones se conservan. El
recorrido está en [Inventario nacional](./inventario-nacional.md). El seed masivo
mantiene su modalidad de carga sintética coordinada independiente.
