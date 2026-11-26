# RescueSync

Las ONG operan sin certificaciones ni aprobación institucional previa. El
[perfil de competencia](./docs/perfiles-competencia.md) describe sus recursos;
la adjudicación controla compatibilidad y disponibilidad, sin límites por riesgo.


RescueSync coordina la respuesta regional ante emergencias conectando municipios,
centros coordinadores y ONGs. La prioridad actual es la Entrega 2: alta de
emergencias, publicación de lotes, ofertas básicas, autenticación local e
integración inicial con Bonita.

## Arquitectura

| Componente | Tecnología y responsabilidad                                                                                         |
| ---------- | -------------------------------------------------------------------------------------------------------------------- |
| Frontend   | React, TypeScript estricto, Vite y Tailwind CSS. Consume solamente FastAPI.                                          |
| Backend    | FastAPI, SQLAlchemy, Alembic, Psycopg y HTTPX. Autentica, autoriza, adapta Bonita y entrega novedades por WebSocket. |
| Base local | PostgreSQL 16. Persiste emergencias, lotes, convocatorias, ofertas y notificaciones.                                 |
| BPM        | Bonita Runtime 10.4. Administra el recorrido y los temporizadores.                                                   |

El frontend nunca llama directamente a Bonita ni a PostgreSQL. FastAPI concentra
las sesiones locales, RBAC, CSRF, persistencia y traducción de contratos externos.
La API Nacional con JWT corresponde a la Entrega 3.
La captura de referencias nacionales y el GET ampliado para Bonita se describen
en [Ofertas consolidadas nacionales](./docs/ofertas-consolidadas-nacionales.md).

En **Mis ofertas**, desplegar una oferta permite ver **Oferta conjunta** e invitar
hasta diez ONGs a una misma propuesta mediante selección múltiple. Las acciones de
edición y consorcio permanecen visibles y deshabilitadas cuando no se pueden usar,
con una explicación de los recursos requeridos, el plazo o el estado de la oferta.
En **Lotes publicados**, **Crear oferta** queda deshabilitado cuando la ONG ya
ofertó ese lote en la convocatoria vigente. Para sumar otros lotes de esa misma
convocatoria se debe editar la oferta existente desde **Mis ofertas**. Las ofertas
de rondas anteriores no bloquean una convocatoria nueva.
Al ofertar para un lote vinculado al catálogo nacional, la **Cantidad ofrecida**
se calcula con las cantidades ingresadas en **Recursos de mi ONG**.

El formulario de lotes usa un selector de capacidades nacionales y determina
automáticamente el nombre y la unidad de cada necesidad. El coordinador completa
la cantidad y una descripción opcional. Para cargar el catálogo se requieren
credenciales de una cuenta nacional autorizada. Compose reutiliza la cuenta de
integración para consultar, o permite elegir otra mediante
`NACIONAL_CATALOGO_LOGIN` y `NACIONAL_CATALOGO_PASSWORD`; los detalles están en la
guía de ofertas consolidadas enlazada arriba.

El administrador dispone de **Gestionar capacidades** para ampliar el catálogo
nacional usando unidades predefinidas, cargadas por migraciones en todos los
entornos. Crear capacidades exige una cuenta nacional `ADMIN_NACIONAL`.
El código se genera a partir del nombre en mayúsculas, sin tildes y con guiones
en lugar de espacios; el formulario verifica los códigos existentes antes del alta.
Ver [Administración del catálogo nacional](docs/catalogo-nacional.md).

## Actualizaciones y notificaciones en tiempo real

FastAPI expone `WS /api/v1/notificaciones/ws`. El navegador se autentica con la
misma cookie `HttpOnly` de la sesión y el backend valida el encabezado `Origin`
contra `CORS_ORIGINS`. Cada novedad se persiste primero en PostgreSQL y recién
después del commit se envía al usuario conectado. Si estuvo desconectado, puede
recuperarla mediante `GET /api/v1/notificaciones` y marcarla como leída con
`PATCH /api/v1/notificaciones/{id}/leida`.

Las notificaciones municipales **Emergencia publicada** y **Emergencia en
evaluación** identifican la zona y la descripción de la emergencia. Su botón
**Ver detalle** abre directamente la evaluación y ejecución de esa emergencia.
La migración también actualiza estos avisos existentes, conservando sus fechas
y su estado de lectura.

El ojo de **Nueva oferta recibida** abre la oferta, sus ONGs y aportes; el de
**Tarea de Bonita con errores** muestra el incidente observado y su emergencia
en modo consulta. Para las ONGs, los avisos de apertura y cierre abren la
convocatoria exacta, incluso si ya cerró o comenzó otra ronda. El detalle incluye
su oferta, o indica que no participaron. Ver [Detalles de notificaciones](docs/notificaciones.md).

El botón **Notificaciones** abre un panel adaptable a móviles y escritorio, con
desplazamiento interno para listas largas. Se cierra al hacer clic o tocar fuera
del panel, volver a pulsar el botón o presionar `Escape`.
La campana muestra un emblema con la cantidad de notificaciones sin leer, que se
actualiza al recibir novedades y al marcarlas como vistas. El emblema desaparece
cuando no quedan notificaciones pendientes.

El engranaje del encabezado abre **Opciones** (`/opciones`), donde la sección
**Cambiar contraseña** permite actualizar la clave de la cuenta. Las cuentas con
contraseña temporal deben completar esta sección antes de continuar. La antigua
ruta `/cambiar-password` redirige a Opciones. El cierre de sesión se encuentra
separado de estos accesos, en el extremo superior derecho del encabezado.

El mensaje WebSocket funciona como una señal: el frontend invalida la consulta
TanStack Query afectada y vuelve a obtener el estado por REST. Bonita continúa
siendo responsable de los temporizadores; sus callbacks producen las novedades
al confirmar la apertura o el cierre de una convocatoria.

El distribuidor de conexiones es local al proceso de FastAPI, apropiado para la
única instancia configurada actualmente en Compose. Antes de ejecutar varias
réplicas del backend se debe incorporar un bus compartido (por ejemplo Redis)
para propagar el mismo evento a las conexiones mantenidas por cada réplica. La
persistencia del buzón no depende de ese bus.

## Requisitos

- Docker Engine con Docker Compose v2, o Docker Desktop.
- En WSL 2, integración de Docker Desktop con la distribución donde está clonado
  el repositorio.
- Minikube y kubectl para el [despliegue con Kubernetes](#despliegue-con-kubernetes).
- Bonita Studio 2025.2 solamente si se dispone externamente del proyecto fuente
  y se necesita generar otra versión del `.bar`.

## Archivos `.env` y valores de configuración

Para ejecutar los dos proyectos con Docker Compose se configura un `.env` en
la raíz de **cada repositorio**:

| Archivo | Configura | Plantilla y valores |
| --- | --- | --- |
| `RescueSync/.env` | Frontend, backend local, PostgreSQL local, correo y Bonita | [`.env.example`](.env.example) y bloque completo de esta sección |
| `RescueSyncAPI/.env` | API nacional, PostgreSQL nacional, JWT y cuenta de integración | [README nacional](https://github.com/neftalito/RescueSyncAPI/blob/develop/README.md#configuración) y [plantilla nacional](https://github.com/neftalito/RescueSyncAPI/blob/develop/.env.example) |

Ejecutar `cp .env.example .env` desde cada raíz solamente si el archivo todavía
no existe. Con Compose, los servicios de RescueSync reciben sus variables desde
el `.env` de la raíz; no hace falta crear otros en `backend/` o `frontend/`.
Los valores siguientes son de desarrollo. Las asignaciones vacías se explican
debajo; las contraseñas reales se guardan en `.env` o en el proveedor del entorno.

### `RescueSync/.env`: valores completos de desarrollo

```dotenv
# Puertos publicados en el host
FRONTEND_PORT=5173
BACKEND_PORT=8000
POSTGRES_PORT=5432
MAILPIT_UI_PORT=8025

# Entorno, sesiones y navegador
APP_ENV=development
SESSION_SECRET=
CORS_ORIGINS=["http://localhost:5173"]
SESSION_COOKIE_SAMESITE=lax
SESSION_COOKIE_SECURE=
ADMIN_EMAIL=admin@rescuesync.org
ADMIN_INITIAL_PASSWORD=administrador123

# Correo local: Mailpit, sin autenticación ni STARTTLS
SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_STARTTLS=false
SMTP_SENDER_EMAIL=no-reply@rescuesync.org
SMTP_TIMEOUT_SECONDS=10
FRONTEND_PUBLIC_URL=http://localhost:5173

# PostgreSQL de RescueSync
POSTGRES_DB=rescuesync
POSTGRES_USER=rescuesync
POSTGRES_PASSWORD=rescuesync_dev

# Bonita Runtime y administrador de plataforma
BONITA_BASE_URL=http://bonita:8080/bonita
BONITA_PORT=8080
BONITA_USERNAME=install
BONITA_PASSWORD=install
BONITA_ACTOR_PASSWORD=
BONITA_PLATFORM_USERNAME=platformAdmin
BONITA_PLATFORM_PASSWORD=platform
BONITA_MONITORING_USERNAME=monitoring
BONITA_MONITORING_PASSWORD=monitoring_dev
BONITA_PROCESS_NAME=RescueSync
BONITA_PROCESS_VERSION=1.5
BONITA_TIMEZONE=UTC
BONITA_MONITOR_ENABLED=true
BONITA_MONITOR_INTERVAL_SECONDS=30
BONITA_CALLBACK_TOKEN=dev-only-rescuesync-bonita-callback-token
BONITA_STARTUP_TIMEOUT_SECONDS=300
BONITA_REQUEST_TIMEOUT_SECONDS=30

# Parámetros inyectados al instalar el proceso
BONITA_BACKEND_BASE_URL=http://backend:8000
BONITA_NATIONAL_API_BASE_URL=http://host.docker.internal:8001
BONITA_OFFER_WINDOW_MS=7200000
BONITA_CONNECT_TIMEOUT_MS=5000
BONITA_READ_TIMEOUT_MS=30000
BONITA_CLIENT_CONNECT_TIMEOUT_SECONDS=3
BONITA_CLIENT_READ_TIMEOUT_SECONDS=10

# PostgreSQL interno de Bonita y base de datos de negocio
BONITA_DB_NAME=bonita
BONITA_DB_USER=bonita
BONITA_DB_PASS=bpm
BONITA_BIZ_DB_NAME=business_data
BONITA_BIZ_DB_USER=business_data
BONITA_BIZ_DB_PASS=bpm

# URL de FastAPI accesible desde el navegador
VITE_API_URL=http://localhost:8000/api/v1

# Servicio de prioridad en la red de Compose
PRIORIDAD_BASE_URL=http://prioridad:8000

# Adaptador nacional del backend local
NACIONAL_BASE_URL=http://host.docker.internal:8001/api/v1
NACIONAL_TIMEOUT_SECONDS=10
NACIONAL_SISTEMA_ORIGEN=rescuesync-local
NACIONAL_CATALOGO_LOGIN=
NACIONAL_CATALOGO_PASSWORD=
NACIONAL_ENCRYPTION_KEY=
NACIONAL_APROVISIONAMIENTO_LOGIN=integracion-rescuesync
NACIONAL_APROVISIONAMIENTO_PASSWORD=

# Cuenta nacional de Bonita y secreto compartido con el backend
BONITA_NATIONAL_API_LOGIN=integracion-rescuesync
BONITA_NATIONAL_API_PASSWORD=
NACIONAL_INTEGRACION_PASSWORD=
BONITA_MAX_REINTENTOS_INTEGRACION=3
```

### Valores que hay que completar antes de iniciar

- `NACIONAL_INTEGRACION_PASSWORD`: contraseña de la cuenta `INTEGRACION` nacional,
  de al menos 12 caracteres. **Es necesaria para instalar el proceso Bonita 1.5**.
  En una instalación nacional local, crear primero la cuenta desde `RescueSyncAPI`:

  ```bash
  docker compose up -d --build
  docker compose run --rm api python -m app.scripts.bootstrap_integracion --login integracion-rescuesync --sistema-origen rescuesync-local
  ```

  El comando solicita la contraseña; guardar ese mismo valor en
  `NACIONAL_INTEGRACION_PASSWORD` de `RescueSync/.env`. En Render corresponde a
  `INTEGRACION_PASSWORD`, como explica la sección de integración de este README.
- `NACIONAL_ENCRYPTION_KEY`: clave Fernet estable, necesaria para acceso nacional
  por ONG, altas automáticas y seeds demo/masivo. Para generarla, desde `RescueSync`:

  ```bash
  docker compose build backend
  docker compose run --rm --no-deps backend python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```

  Copiar la salida en esa variable y conservarla entre reinicios y workers.
- `SESSION_SECRET`: vacío genera una clave efímera en desarrollo. Para conservar
  sesiones entre reinicios, y obligatoriamente en producción, generar una clave
  propia de al menos 32 caracteres con `openssl rand -hex 32`.

Con Compose, `NACIONAL_APROVISIONAMIENTO_PASSWORD` y
`BONITA_NATIONAL_API_PASSWORD` pueden quedar vacías: ambas toman
`NACIONAL_INTEGRACION_PASSWORD`. El catálogo reutiliza las credenciales efectivas
de aprovisionamiento cuando sus dos variables están vacías. Si se define un
override, ese valor tiene prioridad y debe corresponder a la cuenta indicada.

Para **crear capacidades** desde la administración, configurar una cuenta
`ADMIN_NACIONAL` en las variables de catálogo. Después de cargar el seed demo o
masivo nacional, los valores de desarrollo son:

```dotenv
NACIONAL_CATALOGO_LOGIN=admin.nacional.demo@rescuesync.org
NACIONAL_CATALOGO_PASSWORD=admin-nacional-demo123
```

`BONITA_ACTOR_PASSWORD` vacía hace que el instalador genere una contraseña
aleatoria para los actores del proceso. `SESSION_COOKIE_SECURE` vacía se resuelve
por entorno: `false` en desarrollo/test y `true` en producción. Las credenciales
SMTP quedan vacías con Mailpit; con otro proveedor completar juntas
`SMTP_USERNAME` y `SMTP_PASSWORD`, además de host, puerto y STARTTLS.

### URLs, puertos y ejecución fuera de Compose

`VITE_API_URL` es la URL que abre el navegador; `NACIONAL_BASE_URL` y
`BONITA_NATIONAL_API_BASE_URL` se usan desde los contenedores. La primera URL
nacional incluye `/api/v1` y la de Bonita no lo incluye. Para apuntar a Render,
cambiar ambas como indica la [integración nacional](#integración-con-la-api-nacional-de-render).

Si se cambian los puertos publicados de frontend/backend, ajustar también
`CORS_ORIGINS`, `FRONTEND_PUBLIC_URL` y `VITE_API_URL`. `POSTGRES_PORT` modifica
el puerto del host; el backend de Compose sigue usando `db:5432`. El timer
`BONITA_OFFER_WINDOW_MS=7200000` dura dos horas; para una prueba de dos minutos,
usar `120000`.

Para ejecutar herramientas y servicios directamente en el host:

| Archivo o variable | Valor | Cuándo se configura |
| --- | --- | --- |
| `RescueSync/backend/.env` | Copiar las variables del backend del bloque anterior | Al ejecutar FastAPI o Alembic desde `backend/`; Pydantic busca `.env` en el directorio de ejecución |
| `POSTGRES_HOST` | `localhost` | Backend en el host contra PostgreSQL de Compose; `POSTGRES_PORT=5432` o el puerto publicado elegido |
| `DATABASE_URL` | `postgresql+psycopg://rescuesync:rescuesync_dev@localhost:5432/rescuesync` | Alternativa a `POSTGRES_*`, con prioridad; Compose local no propaga esta variable |
| `BONITA_BASE_URL` | `http://localhost:8080/bonita` | Backend en el host contra Bonita de Compose |
| `NACIONAL_BASE_URL` | `http://localhost:8001/api/v1` | Backend en el host contra API nacional local |
| `SMTP_HOST` / `SMTP_PORT` | Host y puerto SMTP accesibles desde el backend | Mailpit de Compose publica solamente la interfaz web; para usar SMTP desde el host hay que publicar también su puerto SMTP o usar otro proveedor |
| `SESSION_COOKIE_NAME` | `rescuesync_session` | Override opcional del backend; Compose no lo propaga |
| `SESSION_MAX_AGE_SECONDS` | `28800` | Duración de la sesión, ocho horas; Compose no lo propaga |
| `APP_NAME` / `API_V1_PREFIX` | `RescueSync API` / `/api/v1` | Overrides opcionales del backend; Compose no los propaga |
| `BONITA_BAR_PATH` | Ruta al archivo `.bar` o al directorio que contiene un único `.bar` | Al ejecutar el instalador manualmente; Compose fija `/bonita-source` |
| `RescueSync/frontend/.env` | `VITE_API_URL=http://localhost:8000/api/v1` | Al ejecutar Vite con npm desde `frontend/` |

Las credenciales efectivas de aprovisionamiento, catálogo y Bonita deben estar
definidas explícitamente al ejecutar fuera de Compose: los fallbacks de
`NACIONAL_INTEGRACION_PASSWORD` los implementa Compose. El instalador manual
usa variables exportadas al proceso. En el build Docker de producción del
frontend, `VITE_API_URL` se pasa con `--build-arg VITE_API_URL=/api/v1` o la URL
pública correspondiente; cambiarla exige reconstruir el frontend.

### Valores para producción

Configurar `APP_ENV=production`, un `SESSION_SECRET` estable y un
`BONITA_CALLBACK_TOKEN` propio de al menos 32 caracteres, generados por separado.
Definir `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` propios antes del primer arranque,
reemplazar las contraseñas de PostgreSQL y Bonita y configurar el SMTP real.
Usar las URLs públicas HTTPS en `FRONTEND_PUBLIC_URL`, `VITE_API_URL` y
`CORS_ORIGINS`. Si frontend y API están en sitios distintos, usar
`SESSION_COOKIE_SAMESITE=none` y `SESSION_COOKIE_SECURE=true`.

Los parámetros de Bonita se aplican al instalar el proceso: cambiar la URL,
credenciales nacionales, token de callbacks o timer en `.env` no actualiza una
definición ya instalada. Seguir la [guía de despliegue y operación](docs/bonita/despliegue-y-operacion.md)
para una instalación existente.

## Inicio rápido

1. Crear la configuración local y activar los hooks compartidos:

   ```bash
   cp .env.example .env
   git config core.hooksPath .githooks
   ```

   Completar los [valores requeridos](#valores-que-hay-que-completar-antes-de-iniciar),
   en particular la contraseña nacional antes de instalar Bonita.

2. Construir y levantar el entorno:

   ```bash
   docker compose up --build
   ```

   Compose levanta también el servicio `prioridad`, que el backend usa para la
   consulta previa al alta municipal. El valor predeterminado es
   `PRIORIDAD_BASE_URL=http://prioridad:8000`. Para la demo de escalado o para
   servir la prioridad desde un clúster, seguí el
   [despliegue con Kubernetes](#despliegue-con-kubernetes).

3. Opcionalmente, cargar el escenario demo de desarrollo. Configurar antes
   `NACIONAL_ENCRYPTION_KEY` y la cuenta de integración del
   [alta nacional automática](docs/acceso-nacional-automatico.md). La API indicada
   por `NACIONAL_BASE_URL` debe estar disponible. Recrear el backend si cambió su
   entorno:

   ```bash
   docker compose run --rm backend python -m app.scripts.seed
   ```

   Este comando crea las dos ONG demo y sus cuentas técnicas mediante la API
   nacional, guarda los UUID reales y cifra sus secretos. No requiere ejecutar
   el seed de RescueSyncAPI y no carga inventario ni certificaciones. Entrar con
   `ong@rescuesync.org` / `ong123` o `redmedica@rescuesync.org` / `redmedica123`
   permite cargar los recursos manualmente en **Mis recursos**.
   Si falla el alta nacional, los datos locales y las solicitudes quedan guardados;
   corregir la causa y repetir el mismo comando no duplica las altas.

   Para medir el sistema con miles de registros, usar el
   [seed masivo configurable](docs/seed-masivo.md):
   `docker compose run --rm backend python -m app.scripts.seed_masivo`.
   La carga predeterminada incluye 5.000 emergencias y evita duplicados al repetirla.
   Reconstruir primero la imagen de desarrollo para instalar Faker.

   El masivo funciona sin ejecutar el demo previamente y conserva su modalidad
   de datos sintéticos coordinados con el masivo nacional. Ambos reutilizan
   el administrador inicial (`admin@rescuesync.org` / `administrador123` por defecto,
   configurable con `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD`). El catálogo usa la
   cuenta de integración para consultas cuando las variables propias quedan vacías.
   Crear capacidades requiere una cuenta `ADMIN_NACIONAL` existente en esa API,
   configurada en `NACIONAL_CATALOGO_LOGIN` y `NACIONAL_CATALOGO_PASSWORD`.
   El recorrido y la recuperación de vínculos demo anteriores se describen en
   [Inventario nacional](docs/inventario-nacional.md).

4. Abrir los servicios:
   - Frontend: <http://localhost:5173>
   - API: <http://localhost:8000>
   - Swagger UI: <http://localhost:8000/docs>
   - Bandeja local de correos (Mailpit): <http://localhost:8025>
   - Bonita Runtime: <http://localhost:8080/bonita>
   - Health de PostgreSQL: <http://localhost:8000/api/v1/health/database>
   - Health de Bonita: <http://localhost:8000/api/v1/health/bonita>

Compose espera a PostgreSQL, aplica las migraciones y luego inicia FastAPI y
Vite. En paralelo, `bonita-deploy` instala y habilita el proceso versionado. El
estado `Exited (0)` de ese contenedor al finalizar es esperado.

FastAPI garantiza además que exista un administrador activo. En una instalación
nueva se puede ingresar con `admin@rescuesync.org` / `administrador123` y el
sistema obliga a cambiar esa contraseña antes de habilitar cualquier gestión.
Para producción, definir `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` antes del
primer arranque; consultar la [guía de autenticación](docs/autenticacion-local.md).

Para detener el entorno sin borrar datos:

```bash
docker compose down
```

`docker compose down --volumes` también elimina las bases de RescueSync y Bonita,
además de las dependencias de Node almacenadas en volúmenes.

La guía de [autenticación local](docs/autenticacion-local.md) contiene las
cuentas del seed, bootstrap del administrador, gestión de usuarios, cambio de
contraseñas, endpoints de sesión y matriz RBAC.

Desde el dashboard, el administrador también puede crear, editar, desactivar y
recuperar municipios, centros coordinadores y ONG. La baja es lógica y desactiva
las cuentas relacionadas; la recuperación no devuelve acceso a esas cuentas de
forma automática.

Al crear un usuario desde la administración, el backend genera una contraseña
temporal y la envía por SMTP. En desarrollo, Mailpit captura el mensaje sin
entregarlo a Internet; puede inspeccionarse en <http://localhost:8025>. Las
variables `SMTP_*` permiten apuntar el mismo cliente a un sandbox de Mailtrap u
otro proveedor SMTP.

## Integración con la API nacional de Render

Cuando RescueSyncAPI se ejecuta en Render con
`INTEGRACION_AUTO_BOOTSTRAP=true`, la cuenta nacional INTEGRACION se crea
automáticamente en el arranque de esa API. Antes debe tener aplicadas sus
migraciones y configurado un secreto estable en `INTEGRACION_PASSWORD`, junto con
`INTEGRACION_LOGIN=integracion-rescuesync` e
`INTEGRACION_SISTEMA_ORIGEN=rescuesync-local`.

Para una instalación nueva, generar una sola vez la contraseña compartida y la
clave Fernet local con la imagen del backend:

```bash
docker compose run --rm --no-deps backend python -c "from secrets import token_urlsafe; from cryptography.fernet import Fernet; print('NACIONAL_INTEGRACION_PASSWORD=' + token_urlsafe(32)); print('NACIONAL_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
```

Guardar la salida únicamente en el `.env` local y copiar el valor de
`NACIONAL_INTEGRACION_PASSWORD` a `INTEGRACION_PASSWORD` en Render. La clave
Fernet permanece en RescueSync: cifra las credenciales y JWT de cada ONG y debe
mantenerse estable entre reinicios y workers. Si ya hay secretos configurados,
conservarlos; generar otros no recupera ni rota las cuentas existentes.

La configuración local para el despliegue actual es:

```dotenv
NACIONAL_BASE_URL=https://rescuesyncapi.onrender.com/api/v1
BONITA_NATIONAL_API_BASE_URL=https://rescuesyncapi.onrender.com
NACIONAL_SISTEMA_ORIGEN=rescuesync-local
NACIONAL_INTEGRACION_PASSWORD=<mismo-secreto-configurado-en-Render>
NACIONAL_ENCRYPTION_KEY=<clave-Fernet-local-estable>
```

Por defecto, Compose utiliza el login `integracion-rescuesync` en Bonita y
para el aprovisionamiento nacional del backend. El catálogo reutiliza las
credenciales efectivas de aprovisionamiento para consultar capacidades y unidades.
Crear capacidades requiere configurar por separado una cuenta `ADMIN_NACIONAL` en
`NACIONAL_CATALOGO_LOGIN` y `NACIONAL_CATALOGO_PASSWORD`.

Para usar la cuenta compartida, dejar vacíos o quitar los overrides
`NACIONAL_APROVISIONAMIENTO_PASSWORD`, `BONITA_NATIONAL_API_PASSWORD`,
`NACIONAL_CATALOGO_LOGIN` y `NACIONAL_CATALOGO_PASSWORD`, incluidos los valores del
administrador demo de un `.env` anterior. Los valores explícitos conservan
prioridad. Si el login de Render es distinto del predeterminado, configurar el
mismo en `NACIONAL_APROVISIONAMIENTO_LOGIN` y `BONITA_NATIONAL_API_LOGIN`.
`BONITA_NATIONAL_API_BASE_URL` va sin `/api/v1`.

Validar con `docker compose config --quiet`. El comando sin `--quiet` muestra los
secretos resueltos y su salida no debe publicarse. Una vez iniciada la API
nacional y aprovisionada la cuenta, ejecutar `docker compose up -d --build` para
una instalación nueva de RescueSync.

Si Bonita ya tiene instalado RescueSync 1.5 con otra URL o credencial, reconstruir
los contenedores **no actualiza los parámetros de esa definición**. Un cambio de
URL se informa como advertencia; otro usuario o contraseña nacional detiene el
deploy. Revisar [el procedimiento de transición a Render](docs/bonita/despliegue-y-operacion.md#pasar-una-instalación-existente-a-render)
antes de cambiar un entorno con casos. El health de Bonita comprueba el proceso
habilitado, pero no prueba su autenticación nacional.

## Prioridad de emergencias

Antes del alta, el operador municipal consulta la prioridad por gravedad y zona.

### Despliegue con Kubernetes

Para usar el priorizador en Kubernetes, ejecutá estos comandos desde la raíz
de RescueSync. El manifiesto usa la
[imagen publicada en Docker Hub](https://hub.docker.com/r/neftalito/rescuesync-prioridad/tags).

```bash
minikube start --driver=docker
minikube addons enable metrics-server
kubectl --context minikube apply -f prioridad-emergencias/k8s.yaml
kubectl --context minikube rollout status deployment/prioridad
```

Si querés que **el alta municipal use el priorizador del clúster**, levantá
primero RescueSync con Compose. Desde otra terminal, con el driver Docker y el
perfil predeterminado de Minikube, recreá el backend con la URL del Service y
conectalo a la red Docker del clúster.

```bash
IP_MINIKUBE=$(minikube ip)
PUERTO_PRIORIDAD=$(kubectl --context minikube get service prioridad -o jsonpath='{.spec.ports[0].nodePort}')
PRIORIDAD_BASE_URL="http://${IP_MINIKUBE}:${PUERTO_PRIORIDAD}" \
  docker compose up -d --no-deps --force-recreate backend
docker network connect minikube "$(docker compose ps -q backend)"
```

En un clúster remoto, usá como `PRIORIDAD_BASE_URL` la URL base del priorizador
que pueda alcanzar el backend. Para probar el autoescalado desde la terminal,
seguí la [guía de despliegue en PDF](docs/despliegue-prioridad-kubernetes.pdf)
o su [versión en Markdown](docs/despliegue-prioridad-kubernetes.md).

## Cliente reutilizable de Bonita

[`docs/RescueSync-1.5.bar`](docs/RescueSync-1.5.bar) es la fuente de verdad del
proceso desplegable. FastAPI crea un único `ClienteBonita` durante el `lifespan`,
comparte su pool HTTPX y lo cierra al apagar la aplicación.

Las rutas obtienen esa instancia con `ClienteBonitaDep`, como muestra el
[health check de Bonita](backend/app/api/routes/health.py):

```python
from app.api.dependencies import ClienteBonitaDep


@router.get("/bonita", response_model=HealthResponse)
def bonita_health(cliente: ClienteBonitaDep) -> HealthResponse:
    cliente.obtener_proceso_habilitado()
    return HealthResponse(service="bonita")
```

No se crea un `httpx.Client` por petición ni se cierra el cliente inyectado. Sus
métodos son sincrónicos, por lo que las rutas que los usan se declaran con
`def`. La ruta traduce HTTP y delega la transacción y la persistencia a un
servicio que recibe `ClienteBonita`.

Para iniciar un caso, el servicio resuelve primero la definición por
`BONITA_PROCESS_NAME` y `BONITA_PROCESS_VERSION`, construye un
`ContratoInicioProceso` y llama a `iniciar_instancia()`. Nunca configura el ID
numérico de la definición.

Un `BonitaResultadoDesconocidoError` significa que una operación con efectos
pudo haberse aplicado. No se repite ciegamente: una instanciación se reconcilia
primero con `buscar_casos_por_emergencia()`.

La guía de [uso del cliente HTTPX](docs/bonita/cliente-httpx.md) documenta el
contrato de inicio, todas las operaciones, el ciclo de vida fuera de FastAPI,
los errores y las pruebas con RESPX.

## Calidad y pruebas

La configuración nacional de Compose se verifica sin iniciar servicios ni leer
el `.env` del operador. Desde la raíz, con Python y Docker Compose disponibles:

```bash
python -m unittest discover --start-directory tests --verbose
```

Backend:

```bash
docker compose run --rm backend pytest
docker compose run --rm backend ruff check .
docker compose run --rm backend ruff format --check .
```

Frontend:

```bash
docker compose run --rm frontend npm run lint
docker compose run --rm frontend npm run typecheck
docker compose run --rm frontend npm test
docker compose run --rm frontend npm run build
```

La [guía de calidad](docs/desarrollo/calidad-y-pruebas.md) agrega cobertura,
Playwright, hooks y verificaciones de CI. Las pruebas con un Runtime Bonita real
tienen un [procedimiento E2E separado](docs/bonita/pruebas-e2e.md).

## Documentación

- [CORS desde `.env` y dominios de despliegue](docs/cors.md).

El perfil **Auditor / Directivo** dispone de un [dashboard global de indicadores](docs/dashboard-auditor.md)
con filtros, gráficos interactivos, tiempos por tarea de Bonita y exportación CSV/JSON/PDF.
Se actualiza por WebSocket e incluye alertas de tareas fallidas de Bonita; el seed
contiene una demo ampliada para recorrer distintas métricas y estados.
Los indicadores de resultado usan las confirmaciones de adjudicación, liberación
y cierre que guarda el flujo operativo.

El [monitoreo de procesos](docs/monitoreo-procesos.md) explica los cálculos,
incluidos los suministros movilizados y la resolución mediante consorcios. Al
adjudicar, el municipio puede fijar plazos. Al finalizar, cada ONG informa
cuánto movilizó y cumplió por lote. Actualizá la base con `alembic upgrade head`
para habilitar el registro de estas cantidades.

El [índice de `docs/`](docs/README.md) organiza las guías por tema. Los accesos
principales son:

- [Proceso BPM vigente](docs/bonita/proceso-bpm.md).
- [Despliegue y operación de Bonita](docs/bonita/despliegue-y-operacion.md).
- [Callbacks de Bonita hacia FastAPI](docs/bonita/callbacks.md).
- [Modelos y migraciones](docs/desarrollo/migraciones.md).
- [Modelo de base de datos](docs/modelo-base-datos-rescuesync.md).
- [Imágenes de producción](docs/despliegue.md).
- [Demo local y con Cloudflare Tunnel](docs/demo-cloudflare.md).

Las fuentes funcionales de la entrega y el único `.bar` versionado también están
catalogados en ese índice.

## Colaboración

`main` y `develop` son ramas protegidas. Cada tarea parte de su base actualizada,
se implementa en una rama propia y se integra mediante pull request con el check
`quality` exitoso.

Las convenciones completas de ramas, arquitectura, estilo, seguridad y
definición de terminado están en [`AGENTS.md`](AGENTS.md), que es la fuente de
verdad para contribuir.

### Evaluación, adjudicación y cierre (T36/T37)

La API local y la pantalla de evaluación/ejecución implementan perfiles, cobertura
compatible, selección municipal, finalización de cada ONG y cierre coordinador.
Aplicar la migración `20261016_0015`. El BAR 1.5 fue adaptado en Studio y recorre
el camino feliz completo (sin tareas de incidentes). Ver
[contratos T36/T37](docs/bonita/contratos-t36-t37.md), incluyendo parámetros,
permisos, reintentos, pruebas y comprobación del Runtime.
