# RescueSync

## Componentes

- **frontend**: React con TypeScript estricto, Vite y Tailwind CSS, con React
  Router para la navegación, TanStack Query para el estado remoto y React Hook
  Form + Zod para formularios y validaciones en tiempo de ejecución.
- **backend**: FastAPI, SQLAlchemy, Alembic, Psycopg y HTTPX. Incluye pwdlib con
  Argon2 para el hash de contraseñas e itsdangerous para las sesiones locales.
- **db**: PostgreSQL 16 para los datos locales de RescueSync.
- **Bonita 10.4**: se ejecuta desde Bonita Studio en el host durante esta etapa,
  hasta completar la configuración del archivo .bos.

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
├── docs/                     # Documentación funcional y proyecto de Bonita
│   ├── *.pdf                 # Requisitos, grooming y descripción del flujo
│   └── rescuesync.bos        # Proyecto fuente para Bonita Studio 10.4
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
- Bonita Studio 10.4 para importar y ejecutar rescuesync.bos.

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

2. Construir y levantar el entorno:

       docker compose up --build

3. Abrir los servicios:

   - Frontend: <http://localhost:5173>
   - API: <http://localhost:8000>
   - Swagger UI: <http://localhost:8000/docs>
   - Health de PostgreSQL: <http://localhost:8000/api/v1/health/database>

Compose espera a que PostgreSQL esté saludable, ejecuta las migraciones y recién
después inicia FastAPI y Vite.

Para detener los contenedores sin borrar los datos:

    docker compose down

El comando docker compose down --volumes también elimina la base de datos local
y las dependencias de Node guardadas en volúmenes.

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

El archivo rescuesync.bos fue generado con Bonita Studio 10.4.0. Durante el
desarrollo se debe abrir en esa versión del Studio y ejecutar su Runtime en el
puerto 8080.

Dentro de Docker, FastAPI usa esta URL:

    http://host.docker.internal:8080/bonita

Antes de implementar el inicio de una instancia hay que completar en el proceso:

- contrato de instanciación;
- variables idEmergencia, gravedad y zona como mínimo;
- despliegue y activación del proceso;
- valor de BONITA_PROCESS_DEFINITION_ID en .env.

Las credenciales y la URL de Bonita están centralizadas en .env. El frontend
no debe comunicarse directamente con Bonita: FastAPI será el adaptador y
mantendrá la sesión, cookies y token CSRF de la API REST.

### Runtime Docker opcional

compose.yaml contiene un servicio Bonita 10.4.0 preparado pero completamente
comentado. También contiene, comentados, los volúmenes utilizados por ese
servicio. Para habilitarlo:

1. Descomentar el servicio bonita y los volúmenes bonita_temp y bonita_work.
2. Cambiar en .env el valor de BONITA_BASE_URL:

       BONITA_BASE_URL=http://bonita:8080/bonita

3. Levantar el Runtime:

       docker compose up -d bonita

4. Acceder al portal desde <http://localhost:8080/bonita>.

El Runtime de Bonita no consume archivos .bos directamente. rescuesync.bos es
el proyecto fuente: debe importarse en Bonita Studio 10.4, compilarse/exportarse
como artefacto desplegable y luego desplegarse y activarse en el Runtime.

Mientras el bloque continúe comentado, el entorno utiliza Bonita Studio en el
host mediante host.docker.internal y Compose mantiene solamente frontend,
backend y PostgreSQL.

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
