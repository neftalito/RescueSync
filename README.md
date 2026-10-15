# RescueSync

RescueSync coordina la respuesta regional ante emergencias conectando municipios,
centros coordinadores y ONGs. La prioridad actual es la Entrega 2: alta de
emergencias, publicación de lotes, ofertas básicas, autenticación local e
integración inicial con Bonita.

## Arquitectura

| Componente | Tecnología y responsabilidad |
| --- | --- |
| Frontend | React, TypeScript estricto, Vite y Tailwind CSS. Consume solamente FastAPI. |
| Backend | FastAPI, SQLAlchemy, Alembic, Psycopg y HTTPX. Autentica, autoriza, adapta Bonita y entrega novedades por WebSocket. |
| Base local | PostgreSQL 16. Persiste emergencias, lotes, convocatorias, ofertas y notificaciones. |
| BPM | Bonita Runtime 10.4. Administra el recorrido y los temporizadores. |

El frontend nunca llama directamente a Bonita ni a PostgreSQL. FastAPI concentra
las sesiones locales, RBAC, CSRF, persistencia y traducción de contratos externos.
La API Nacional con JWT corresponde a la Entrega 3.
La captura de referencias nacionales y el GET ampliado para Bonita se describen
en [Ofertas consolidadas nacionales](./docs/ofertas-consolidadas-nacionales.md).

El formulario de lotes usa un selector de capacidades nacionales y determina
automáticamente el nombre y la unidad de cada necesidad. El coordinador completa
la cantidad y una descripción opcional. Para cargar el catálogo se requieren
`NACIONAL_CATALOGO_LOGIN` y `NACIONAL_CATALOGO_PASSWORD` de una cuenta nacional
autorizada; los detalles están en la guía de ofertas consolidadas enlazada arriba.

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

   Para probar inventario, ejecutar también el seed de RescueSyncAPI. Ambos seeds
   dejan preparadas las cuentas técnicas y sus accesos: entrar con `ong123` permite
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

## Cliente reutilizable de Bonita

[`docs/RescueSync-1.2.bar`](docs/RescueSync-1.2.bar) es la fuente de verdad del
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
