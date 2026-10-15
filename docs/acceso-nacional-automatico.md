# Acceso nacional automático por ONG

Los representantes sólo inician sesión local. El backend utiliza una cuenta
técnica distinta por ONG, obtiene JWT de cinco minutos y los renueva cuando
faltan o quedan menos de 30 segundos. No hay refresh tokens ni contraseñas
personales nacionales guardadas. El token se comparte entre representantes y
workers de la misma ONG y nunca llega al navegador.

## Preparación

1. Actualizar primero RescueSyncAPI y aplicar sus migraciones. Crear la cuenta
   técnica con su comando administrativo, documentado en
   [la API nacional](../../RescueSyncAPI/docs/acceso-automatico-ong.md).
2. Generar una clave Fernet fuera del repositorio y configurar
   `NACIONAL_ENCRYPTION_KEY` como secreto del backend:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   La misma clave debe estar disponible en el comando de importación y en todos
   los workers. Debe ser independiente de `SESSION_SECRET`. Si falta, las
   funciones locales siguen disponibles; el acceso nacional requiere configuración.
3. Aplicar `alembic upgrade head` local. La migración crea `acceso_nacional` y
   descarta los JWT manuales anteriores; no los convierte en credenciales técnicas.
4. Mantener la ONG local activa y vinculada al UUID nacional verificado. Copiar
   el archivo protegido al contenedor del backend y ejecutar:

   ```bash
   python -m app.scripts.acceso_nacional --login admin@example.org --organizacion ID_LOCAL --archivo /tmp/credencial-ong.json
   ```

   Se solicita la contraseña del administrador local. Debe haber completado su
   cambio de contraseña inicial. El archivo debe ser regular y privado (`0600`).
   El comando hace login nacional y verifica cuenta, propósito técnico, rol y ONG
   mediante `/me` antes de guardar. No acepta una cuenta personal ni autovincula.
5. Eliminar las copias del archivo transferido. No versionarlas ni conservarlas
   en logs, argumentos de proceso o capturas. Repetir por cada ONG vinculada.

Los comandos pueden ejecutarse con `docker compose run --rm --no-deps -it`
usando el servicio `api` o `backend` correspondiente y un archivo privado montado
desde una carpeta fuera del repositorio. No hace falta reiniciar para importar
otra ONG o reemplazar su credencial.

## Operación y recuperación

- `GET /api/v1/mi-ong/conexion` conserva vínculo y expiración y agrega `estado`:
  `LISTA`, `SIN_CONFIGURAR` o `REQUIERE_REVISION`. `LISTA` permite operar aunque
  todavía no haya JWT; `conectada` sólo describe la caché temporal.
- Los POST/DELETE locales de conexión manual se retiran. La web no ofrece
  conectar/desconectar para ONG vinculadas. El onboarding de ONG nuevas conserva
  su recorrido y queda fuera del aprovisionamiento automático.
- Cerrar sesión o cambiar una contraseña local no elimina el acceso institucional.
  Las validaciones locales siguen rechazando usuarios inactivos, roles incorrectos,
  sesiones vencidas y organizaciones desactivadas.
- Cambiar o eliminar el vínculo nacional borra la configuración anterior. Guardar
  el mismo UUID conserva el acceso.
- Ante `401`, el backend autentica nuevamente una sola vez y reintenta únicamente
  consultas. Una escritura nunca se repite automáticamente, tampoco ante timeout.
- Una caída nacional no bloquea el login local. Credenciales inválidas/revocadas
  dejan el acceso en revisión sin insistir con nuevos logins. Un `403` de negocio
  no se interpreta como expiración de token.
- Para recuperar una credencial, rotarla en la API nacional e importar el archivo
  nuevo. Rotar/revocar afecta sólo esa ONG e invalida sus JWT inmediatamente.
- Cambiar la clave Fernet exige reimportar las credenciales de todas las ONG; la
  aplicación no intenta descifrar con el secreto de sesión como alternativa.

La caché usa transacciones independientes y actualizaciones condicionadas a la
versión de configuración. Renovar no confirma cambios de ofertas del llamador ni
restaura una configuración reemplazada durante HTTP. Renovaciones simultáneas
pueden obtener tokens válidos diferentes; no es necesaria una exclusión global.
Los logs de operaciones completadas incluyen usuario local, ONG y acción.

## Validación y rollback

Las pruebas cubren aislamiento, renovación, logout, revocación, timeout, cambio de
configuración durante login y ausencia de commits sobre el caso de uso llamador.
Ejecutar las suites y checks de ambos proyectos. El downgrade local elimina la
configuración técnica y no recupera tokens manuales descartados; un nuevo upgrade
requiere importar otra vez las credenciales. El rollback nacional desactiva las
cuentas técnicas antes de retirar su propósito y versión.

Tener acceso no habilita institucionalmente ni certifica a una ONG. Bonita y las
cuentas técnicas de catálogo/integración conservan su autenticación separada.
