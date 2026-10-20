# RescueSync

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
Ver [Administración del catálogo nacional](docs/catalogo-nacional.md).

## Actualizaciones y notificaciones en tiempo real

FastAPI expone `WS /api/v1/notificaciones/ws`. El navegador se autentica con la
misma cookie `HttpOnly` de la sesión y el backend valida el encabezado `Origin`
contra `CORS_ORIGINS`. Cada novedad se persiste primero en PostgreSQL y recién
después del commit se envía al usuario conectado. Si estuvo desconectado, puede
recuperarla mediante `GET /api/v1/notificaciones` y marcarla como leída con
`PATCH /api/v1/notificaciones/{id}/leida`.

El botón **Notificaciones** abre un panel adaptable a móviles y escritorio, con
desplazamiento interno para listas largas. Se cierra al hacer clic o tocar fuera
del panel, volver a pulsar el botón o presionar `Escape`.

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
- Bonita Studio 2025.2 solamente si se dispone externamente del proyecto fuente
  y se necesita generar otra versión del `.bar`.

## Inicio rápido

1. Crear la configuración local y activar los hooks compartidos:

   ```bash
   cp .env.example .env
   git config core.hooksPath .githooks
   ```

2. Construir y levantar el entorno:

   ```bash
   docker compose up --build
   ```

3. Opcionalmente, cargar un escenario completo de desarrollo. Configurar antes
   `NACIONAL_ENCRYPTION_KEY` en `.env` y recrear el backend si ya estaba levantado;
   el seed utiliza esa clave estable para cifrar los accesos nacionales demo:

   ```bash
   docker compose run --rm backend python -m app.scripts.seed
   ```

   Para medir el sistema con miles de registros, usar el
   [seed masivo configurable](docs/seed-masivo.md):
   `docker compose run --rm backend python -m app.scripts.seed_masivo`.
   La carga predeterminada incluye 5.000 emergencias y evita duplicados al repetirla.
   Reconstruir primero la imagen de desarrollo para instalar Faker.

   Elegir demo o masivo para cada demostración y usar la misma modalidad en ambos
   proyectos. El masivo funciona sin ejecutar el demo previamente. Ambos reutilizan
   el administrador inicial (`admin@rescuesync.org` / `administrador123` por defecto,
   configurable con `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD`). El catálogo nacional
   usa `admin.nacional.demo@rescuesync.org` / `admin-nacional-demo123` en cualquiera
   de las dos modalidades para administrar capacidades; configurar esos valores
   explícitamente en `NACIONAL_CATALOGO_LOGIN` y `NACIONAL_CATALOGO_PASSWORD`.
   Si quedan vacíos, Compose usa la cuenta de integración para consultar.

   Para probar inventario demo, ejecutar también `app.scripts.seed` de RescueSyncAPI.
   Los seeds demo de los dos proyectos dejan preparadas las cuentas técnicas y
   sus accesos: entrar con `ong123` permite
   abrir Mis recursos sin importaciones manuales. El recorrido y la configuración
   están en [Inventario nacional](docs/inventario-nacional.md).
   Configurar una sola vez el [alta y acceso nacional automático](docs/acceso-nacional-automatico.md).
   Las nuevas ONG generan su identificador y cuenta técnica al crearlas; el correo de contacto es opcional.

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
Los indicadores que requieren adjudicación y cierre se identifican como no disponibles.

El [monitoreo de procesos](docs/monitoreo-procesos.md) agrega tareas activas y
los seis indicadores BAM del material de clase, con evidencia confirmada,
fórmulas, cobertura de datos y exportación. La guía distingue las consultas
disponibles con el BPM 1.2 de las emisiones que corresponden a T35–T37.

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
