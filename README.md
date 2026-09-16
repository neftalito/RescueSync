# RescueSync

## Componentes

- **frontend**: React con TypeScript estricto, Vite y Tailwind CSS, con React
  Router para la navegación, TanStack Query para el estado remoto y React Hook
  Form + Zod para formularios y validaciones en tiempo de ejecución.
- **backend**: FastAPI, SQLAlchemy, Alembic, Psycopg y HTTPX. Incluye pwdlib con
  Argon2 para el hash de contraseñas e itsdangerous para las sesiones locales.
- **db**: PostgreSQL 16 para los datos locales de RescueSync.
- **Bonita 10.4**: Runtime dockerizado con PostgreSQL propio, despliegue
  idempotente del `.bar` versionado y cliente HTTPX tipado en el backend.

Las herramientas de pruebas y calidad están separadas de las dependencias de
producción:

| Área | Herramientas | Uso |
| --- | --- | --- |
| Backend | Pytest y pytest-cov | Pruebas de endpoints, reglas y cobertura |
| Integración con Bonita | RESPX | Simulación y verificación de llamadas HTTPX |
| Frontend | Vitest y Testing Library | Pruebas de componentes e interacciones |
| API simulada | MSW | Respuestas controladas del backend en pruebas frontend |
| Extremo a extremo | Playwright | Flujo Municipio → Coordinador → ONG en un navegador |
| Calidad | Ruff, TypeScript y ESLint | Análisis estático de Python, TypeScript y TSX |

## Estructura del proyecto

```text
RescueSync/
├── .github/workflows/         # Verificaciones automáticas de GitHub Actions
├── .githooks/                 # Hooks de Git compartidos por el equipo
├── backend/                  # API y acceso a datos
│   ├── alembic/              # Configuración y versiones de las migraciones
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/       # Endpoints de FastAPI
│   │   │   └── router.py     # Registro de las rutas de la API
│   │   ├── core/             # Configuración de la aplicación
│   │   ├── db/               # Modelos base, sesión y conexión a PostgreSQL
│   │   └── main.py           # Punto de entrada de FastAPI
│   ├── tests/                # Pruebas automatizadas del backend
│   ├── Dockerfile
│   └── requirements*.txt     # Dependencias de ejecución y desarrollo
├── frontend/                 # Aplicación web
│   ├── src/
│   │   ├── App.test.tsx       # Prueba básica del componente principal
│   │   ├── App.tsx            # Componente principal de React
│   │   ├── index.css          # Estilos globales y Tailwind CSS
│   │   ├── main.tsx           # Punto de entrada de la interfaz
│   │   └── vite-env.d.ts      # Tipos provistos por Vite
│   ├── Dockerfile
│   ├── eslint.config.js       # Reglas de TypeScript, TSX y hooks de React
│   ├── nginx.conf            # Servidor de la imagen de producción
│   ├── package.json          # Dependencias y scripts de npm
│   ├── tsconfig.json         # Compilación estricta de TypeScript
│   └── vite.config.js        # Configuración de Vite y Tailwind CSS
├── docker/
│   └── bonita-db-init/       # Inicialización de la base de negocio de Bonita
├── docs/                     # Documentación funcional y proceso de Bonita
│   ├── *.pdf                 # Requisitos, grooming y descripción del flujo
│   └── RescueSync-1.1.bar    # Proceso desplegable (Bonita Studio 10.4)
├── .env.example              # Plantilla de variables de entorno
├── AGENTS.md                # Convenciones de arquitectura, código y pruebas
├── compose.yaml              # Entorno local: frontend, backend y PostgreSQL
└── README.md
```

Los directorios `node_modules/`, `__pycache__/` y los volúmenes de Docker se
generan durante el desarrollo y no forman parte del código fuente. El archivo
`.env` también es local; debe crearse a partir de `.env.example`.

## Requisitos

- Docker Engine con Docker Compose v2, o Docker Desktop.
- Bonita Studio 10.4 solo para modificar el proceso y generar un nuevo `.bar`.

Si se utiliza WSL 2, Docker Desktop debe tener habilitada la integración con la
distribución Linux donde está clonado este repositorio.

## Flujo de trabajo con ramas

`main` contiene las versiones estables y `develop` integra el trabajo de la
próxima entrega. No se implementan cambios ni se crean commits directamente en
esas ramas: cada tarea se desarrolla en una rama propia y se integra mediante un
pull request.

Antes de comenzar una tarea normal, comprobar que no haya cambios ajenos sin
confirmar, actualizar `develop` y crear la rama correspondiente:

```bash
git switch develop
git pull --ff-only
git switch -c feature/rs-123-alta-emergencia
```

Los nombres usan `<tipo>/<descripcion>` o `<tipo>/<ticket>-<descripcion>`:

| Tipo | Uso |
| --- | --- |
| `feature` | Nueva funcionalidad |
| `fix` | Corrección de un defecto |
| `hotfix` | Corrección urgente que parte de `main` |
| `refactor` | Cambio interno sin modificar comportamiento |
| `test` | Incorporación o ajuste exclusivo de pruebas |
| `docs` | Documentación |
| `ci` | Automatización, integración continua o hooks |
| `chore` | Mantenimiento sin funcionalidad de usuario |
| `release` | Preparación de una versión |

La descripción admite únicamente minúsculas ASCII, números y guiones medios.
No admite espacios, guiones bajos, acentos, barras adicionales ni guiones al
principio o al final. Ejemplos válidos: `fix/cantidad-oferta`,
`docs/modelos-base-datos` y `ci/controles-calidad`.

Los hotfix parten de `main` y, una vez aprobados, deben integrarse tanto en
`main` como en `develop`. Todas las demás ramas parten de `develop`. Antes del
merge, la rama debe estar actualizada con su base y aprobar el check `quality`.
El hook `pre-commit` compartido rechaza commits en ramas protegidas o con nombres
que no cumplen esta convención.

## Inicio rápido

1. Crear el archivo local de configuración:

       cp .env.example .env

2. Comprobar que `docs/` contenga un único `.bar` y que su versión coincida con
   `BONITA_PROCESS_VERSION` en `.env`. El repositorio ya incluye
   `RescueSync-1.1.bar`; solo hace falta regenerarlo si cambia el proceso.

3. Construir y levantar el entorno:

       docker compose up --build

4. Abrir los servicios:

   - Frontend: <http://localhost:5173>
   - API: <http://localhost:8000>
   - Swagger UI: <http://localhost:8000/docs>
   - Bonita Runtime: <http://localhost:8080/bonita>
   - Health de PostgreSQL: <http://localhost:8000/api/v1/health/database>
   - Health de Bonita: <http://localhost:8000/api/v1/health/bonita>

Compose espera a que PostgreSQL esté saludable, ejecuta las migraciones y recién
después inicia FastAPI y Vite. En paralelo, `bonita-deploy` espera al Runtime,
importa la organización requerida, instala el `.bar` si falta y habilita el
proceso. El contenedor de despliegue queda con estado `Exited (0)` al terminar;
ese estado es esperado.

Para detener los contenedores sin borrar los datos:

    docker compose down

El comando docker compose down --volumes también elimina las bases de datos de
RescueSync y Bonita, además de las dependencias de Node guardadas en volúmenes.

## Autenticación local

La aplicación usa sesiones firmadas en una cookie `HttpOnly`; no usa el JWT del
Sistema Nacional previsto para la Entrega 3. El backend vuelve a cargar el
usuario, la organización y el rol desde PostgreSQL en cada petición autenticada.
El cierre de sesión también exige el token CSRF entregado al frontend.

Antes del primer ingreso, crear un usuario desde una terminal interactiva. La
contraseña se solicita sin mostrarla ni incluirla en el historial del shell:

```bash
docker compose run --rm backend python -m app.scripts.create_user \
  --email operador@rescuesync.org \
  --rol OPERADOR_MUNICIPAL \
  --organizacion "Municipio del Delta"
```

Para disponer de un escenario completo de pruebas, ejecutar el seed:

```bash
docker compose run --rm backend python -m app.scripts.seed
```

El seed es idempotente y puede repetirse sin duplicar sus registros. Crea cuatro
organizaciones, una cuenta activa por cada rol, una emergencia registrada, otra
publicada, tres lotes, una convocatoria abierta y una oferta parcial. Sus cuentas
de desarrollo son:

| Rol | Correo | Contraseña de desarrollo |
| --- | --- | --- |
| Operador municipal | `municipio@rescuesync.org` | `municipio123` |
| Coordinador regional | `coordinador@rescuesync.org` | `coordinador123` |
| Representante de ONG | `ong@rescuesync.org` | `ong123` |
| Auditor / Directivo | `auditor@rescuesync.org` | `auditor123` |

Estas credenciales son exclusivamente locales: el seed guarda únicamente hashes
Argon2 y se niega a ejecutarse cuando `APP_ENV=production`.

Los roles disponibles son `OPERADOR_MUNICIPAL`, `COORDINADOR_REGIONAL`,
`REPRESENTANTE_ONG` y `AUDITOR_DIRECTIVO`. Los tres primeros crean o reutilizan
una organización del tipo que corresponde al rol; el auditor no lleva el
argumento `--organizacion`.

Los endpoints locales son:

| Método | Ruta | Resultado |
| --- | --- | --- |
| `POST` | `/api/v1/auth/login` | Valida credenciales y establece la cookie |
| `GET` | `/api/v1/auth/me` | Devuelve el contexto vigente y un token CSRF |
| `POST` | `/api/v1/auth/logout` | Valida `X-CSRF-Token` y elimina la sesión |

En desarrollo, un `SESSION_SECRET` vacío genera una clave efímera al iniciar el
backend, por lo que sus reinicios invalidan las sesiones abiertas. En producción
`APP_ENV=production` exige una clave estable de al menos 32 caracteres, generada
fuera del repositorio, por ejemplo con `openssl rand -hex 32`.

## Migraciones

### Crear un modelo

Cada modelo se define en un módulo dentro de `backend/app/db/models/` y hereda
de `Base`, declarada en `backend/app/db/base.py`. El siguiente ejemplo solo
muestra la estructura técnica; los campos y restricciones reales deben salir
del grooming y del modelo de dominio. Si el directorio todavía no existe,
crearlo junto con su archivo `__init__.py`:

```python
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EntidadEjemplo(Base):
    __tablename__ = "entidades_ejemplo"
    __table_args__ = (
        CheckConstraint(
            "char_length(nombre) > 0",
            name="ck_entidades_ejemplo_nombre_no_vacio",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
```

Además del tipado, agregar en el modelo las claves foráneas, índices y
restricciones `NOT NULL`, `CHECK` o `UNIQUE` que representen invariantes de la
base. Los estados y roles deben usar enums y los timestamps deben conservar zona
horaria.

Para que Alembic detecte el modelo, importar su módulo en
`backend/alembic/env.py` antes de asignar `target_metadata`:

```python
# Esta importación registra la tabla en Base.metadata.
from app.db.models import entidad_ejemplo  # noqa: F401
```

Cuando haya varios modelos, centralizar esas importaciones en
`backend/app/db/models/__init__.py` e importar ese paquete desde `env.py`.

### Crear y aplicar la migración

Desde la raíz del repositorio, generar una revisión con un nombre descriptivo.
En Linux o WSL se pasa el usuario anfitrión para que el archivo generado no quede
propiedad de `root` ni del usuario interno del contenedor:

```bash
docker compose run --rm --user "$(id -u):$(id -g)" backend \
  alembic revision --autogenerate -m "create entidades ejemplo table"
```

Revisar manualmente el archivo nuevo en `backend/alembic/versions/`: tanto
`upgrade()` como `downgrade()` deben ser viables y el autogenerado debe contener
las restricciones esperadas. Alembic no puede inferir correctamente todas las
operaciones, especialmente renombres, conversiones de datos y cambios de enums.

Construir la imagen actualizada y aplicar todas las migraciones pendientes:

```bash
docker compose run --rm --build migrate
```

Finalmente, ejecutar Ruff y las pruebas del backend. Si se comprueba el
`downgrade`, hacerlo únicamente sobre una base local descartable. No modificar
una migración que ya pueda haber sido aplicada por otra persona; crear una nueva
revisión correctiva.

## Integración con Bonita

`docs/RescueSync-1.1.bar`, construido con Bonita Studio 10.4.0, es la única
referencia versionada del proceso. El antiguo `rescuesync.bos` quedó desactualizado
y se eliminó del repositorio. Para cambiar el BPM se debe crear una nueva versión
en Studio, generar su `.bar`, reemplazar el anterior en `docs/` y actualizar
`BONITA_PROCESS_VERSION` y `backend/app/integrations/bonita/contratos.py`.

El entorno contiene los siguientes servicios adicionales:

- `bonita-db`: PostgreSQL exclusivo para el motor y el BDM de Bonita;
- `bonita`: Runtime 10.4.0 expuesto en el puerto configurado;
- `bonita-deploy`: inicializador de ejecución única que despliega el proceso.

FastAPI y el inicializador acceden al Runtime mediante la red interna de
Compose:

    http://bonita:8080/bonita

### Despliegue automático

`bonita-deploy` espera al Runtime, crea los usuarios que `actorMapping.xml`
asigna a los actores, instala el único `.bar` de `docs/` y habilita el proceso.
Los actores se mapean a usuarios, por lo que no se importa ninguna organización.
La contraseña inicial de esos usuarios proviene de `BONITA_ACTOR_PASSWORD`; si
queda vacía, el inicializador genera una aleatoria y no la registra.

Antes de instalar, inyecta los parámetros del proceso desde
`BONITA_BACKEND_BASE_URL`, `BONITA_NATIONAL_API_BASE_URL`,
`BONITA_OFFER_WINDOW_MS`, `BONITA_CONNECT_TIMEOUT_MS` y `BONITA_READ_TIMEOUT_MS`.
Esos valores se aplican solo al instalar: cambiarlos en `.env` no modifica una
definición ya desplegada. El despliegue es idempotente por nombre y versión y
nunca elimina ni reemplaza una definición existente, porque podría tener casos
activos. Si el `.bar` tiene configuraciones sin resolver, `bonita-deploy`
termina con error y muestra los motivos que informa Bonita.

    docker compose logs -f bonita bonita-deploy

### Uso desde FastAPI

El frontend nunca llama a Bonita. El backend comparte un único `ClienteBonita`
(`backend/app/integrations/bonita/cliente.py`), creado en el `lifespan` y
disponible en las rutas mediante la dependencia `ClienteBonitaDep`. El cliente:

- inicia sesión con la cuenta técnica, envía `X-Bonita-API-Token` y renueva la
  sesión una sola vez si Bonita responde 401;
- usa `BONITA_CLIENT_CONNECT_TIMEOUT_SECONDS` y
  `BONITA_CLIENT_READ_TIMEOUT_SECONDS` como timeouts explícitos;
- resuelve el ID de la definición por `BONITA_PROCESS_NAME` y
  `BONITA_PROCESS_VERSION`, sin configurarlo manualmente;
- valida con Pydantic las respuestas y traduce los fallos a excepciones seguras.

| Operación | Método del cliente | Uso en la Entrega 2 |
| --- | --- | --- |
| Proceso habilitado | `obtener_proceso_habilitado()` | Obtener el ID antes de instanciar |
| Iniciar caso | `iniciar_instancia(proceso_id, contrato)` | Alta de emergencia (T16/T17) |
| Reconciliar | `buscar_casos_por_emergencia(proceso_id, id)` | Resolver un resultado incierto |
| Tarea pendiente | `buscar_tarea_lista(case_id, nombre)` | Localizar `Generar lotes de necesidades` |
| Completar tarea | `ejecutar_tarea(tarea_id, usuario_actor)` | Publicar la convocatoria (T12) |

`ContratoInicioProceso` (`contratos.py`) replica el contrato de instanciación
1.1: `idEmergencia` (LONG), `gravedad`, `zona`, `descripcion` y `municipioId`
(LONG). Bonita guarda cada entrada en una variable del mismo nombre e indexa el
caso por `idEmergencia`.

`iniciar_instancia` distingue los fallos que exige el alta:

| Excepción | Significado | Acción esperada |
| --- | --- | --- |
| `BonitaNoDisponibleError` | La petición no llegó a Bonita | `ERROR`, reintento posible |
| `BonitaOperacionRechazadaError` | Contrato rechazado | `ERROR` con mensaje seguro |
| `BonitaResultadoDesconocidoError` | Se perdió la respuesta de un POST | `RESULTADO_DESCONOCIDO`; reconciliar antes de reintentar |

### Verificación

Readiness HTTP, sin detalles internos: `GET /api/v1/health/bonita` responde
`200` si el login funciona y el proceso está `RESOLVED` y `ENABLED`; en caso
contrario, `503`.

Verificación desde la terminal, sin crear casos:

```bash
docker compose exec backend python -m app.scripts.check_bonita_api
```

Prueba E2E del cliente contra el Runtime levantado:

```bash
docker compose run --rm -e RUN_BONITA_E2E=1 backend \
  pytest tests/e2e/test_bonita_runtime.py -m bonita_e2e
```

Crea un caso temporal y verifica, con `ClienteBonita`, el rechazo del contrato,
la instanciación, las variables, la reconciliación por `idEmergencia` y la
ejecución de `Generar lotes de necesidades`. Después espera al timer
`EsperarOfertas` y cancela el caso al terminar. Si una actividad automática
falla, el resultado muestra su nombre. La suite normal omite esta prueba.

### Pendientes del proceso 1.1

La prueba contra el Runtime confirmó que el tramo de FastAPI funciona, pero el
`.bar` 1.1 impide completar el flujo de la Entrega 2. Se debe corregir en Studio
y publicar como versión 1.2:

1. **Conectores que siempre fallan.** En `Enviar notificacion a ONGs de
   convocatoria`, `Cerrar convocatoria local`, `Solicitar ofertas consolidadas`
   y `Marcar emergencia como resuelta`, el script que exige `status == 200` es
   una operación de la tarea. Bonita ejecuta las operaciones antes que los
   conectores `ON_FINISH`, por lo que el script lee `null` y la tarea queda
   `failed` sin llamar a FastAPI. Mover la validación a las salidas del conector
   o activar `fail_on_http_4xx` y `fail_on_http_5xx`.
2. **Gravedad `CRITICA`.** PostgreSQL y FastAPI la admiten, pero la restricción
   del contrato solo acepta `BAJA`, `MEDIA` y `ALTA` (HTTP 400). Mientras tanto,
   `ContratoInicioProceso` la rechaza antes de llamar a Bonita.
3. **Callbacks sin autenticación.** Los conectores usan `auth_type = NONE`. Los
   endpoints que reciban esas llamadas deben autenticarse; por ejemplo, con un
   parámetro de proceso que se envíe como cabecera secreta.
4. **Valor inicial erróneo.** `ofertasConsolidadasJson` se inicializa con la
   constante `"ofertasConsolidadasJson = bodyAsString"`; debe comenzar vacía.

Además, el backend todavía no expone
`POST /api/v1/emergencias/{id}/notificar-apertura`, que Bonita llama al publicar
la convocatoria. Hasta resolver estos puntos, la prueba E2E se detiene en esa
actividad.

## Calidad y pruebas

Backend:

    docker compose run --rm backend pytest
    docker compose run --rm backend pytest --cov=app --cov-report=term-missing
    docker compose run --rm backend ruff check .
    docker compose run --rm backend ruff format --check .

Frontend:

    docker compose run --rm frontend npm run lint
    docker compose run --rm frontend npm run typecheck
    docker compose run --rm frontend npm test
    docker compose run --rm frontend npm run build

Para ejecutar los futuros casos E2E, primero se debe levantar el entorno con
Compose. En el host se requiere Node.js 24 y, la primera vez, instalar el
navegador administrado por Playwright:

    cd frontend
    npx playwright install chromium
    npm run test:e2e

El proyecto ya incluye una prueba básica del montaje de la interfaz, además de
los runners, los mocks y sus scripts de ejecución. Los casos funcionales y el
recorrido E2E se incorporarán junto con las funcionalidades de la Entrega 2.

### Controles automáticos de calidad

El workflow `.github/workflows/quality.yml` se ejecuta en cada pull request y en
cada push a `develop` o `main`. Verifica Ruff, migraciones y pruebas del backend,
además de tipos, ESLint, pruebas y build del frontend. El job final se llama
`quality` para poder configurarlo como status check obligatorio en GitHub.

Activar una vez el hook local versionado después de clonar el repositorio:

    git config core.hooksPath .githooks

El hook `pre-commit` ejecuta Ruff cuando hay Python staged y ESLint junto con el
typecheck cuando hay JavaScript o TypeScript staged. Usa las herramientas locales
si están disponibles; de lo contrario usa las imágenes de Docker Compose, que
deben haberse construido previamente.

## Imágenes de producción

Ambos Dockerfiles incluyen un target de producción:

    docker build --target production -t rescuesync-backend ./backend
    docker build --target production -t rescuesync-frontend ./frontend

La imagen final del frontend utiliza Nginx y redirige /api/ al servicio backend.
La imagen final del backend ejecuta un único proceso FastAPI; la cantidad de
réplicas se configura en la plataforma de despliegue.
