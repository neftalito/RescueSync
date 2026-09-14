# Guía de desarrollo para RescueSync

## Alcance y fuentes de verdad

Estas reglas se aplican a todo el repositorio. Antes de implementar una historia,
consultar `docs/Trabajo integrador 2026.pdf`, `docs/Grooming Etapa 2.pdf` y el
modelo de `docs/rescuesync.bos` cuando la tarea involucre el proceso BPM.

La prioridad actual es la Entrega 2: alta de emergencias, creación y publicación
de lotes, ofertas básicas de ONGs, autenticación/RBAC local e integración inicial
con Bonita. No adelantar componentes de la API Nacional de la Entrega 3 salvo
que sean necesarios para mantener un contrato claro.

## Flujo y nombres de ramas

- `main` contiene versiones estables y `develop` integra el trabajo de la próxima
  entrega. Son ramas protegidas: no implementar cambios, crear commits ni hacer
  push directo sobre ninguna de las dos.
- Antes de modificar archivos, comprobar la rama con `git branch --show-current`.
  Para una tarea normal, partir de `develop` actualizado y crear una rama nueva.
  Los hotfix son la única excepción: parten de `main` y luego deben integrarse
  también en `develop`.
- Una rama debe corresponder a una sola tarea. No mezclar correcciones o
  refactors ajenos aunque resulten convenientes durante la implementación.
- Usar el formato `<tipo>/<descripcion>` o `<tipo>/<ticket>-<descripcion>`, con
  uno de estos tipos: `feature`, `fix`, `hotfix`, `refactor`, `test`, `docs`,
  `ci`, `chore` o `release`.
- La descripción usa minúsculas ASCII, números y guiones medios; no usa espacios,
  guiones bajos, acentos, barras adicionales ni guiones al principio o al final.
  Ejemplos: `feature/rs-123-alta-emergencia`, `fix/cantidad-oferta` y
  `ci/controles-calidad`.
- Si hay cambios sin confirmar que no pertenecen a la tarea actual, no moverlos,
  descartarlos ni incluirlos en la rama nueva. Detenerse y solicitar indicaciones.
- Integrar siempre mediante pull request. Antes de solicitar revisión, actualizar
  la rama con su base y verificar que el check obligatorio `quality` finalice
  correctamente.

## Invariantes de arquitectura

- El frontend solo consume la API de FastAPI; nunca llama directamente a Bonita
  ni accede a PostgreSQL.
- FastAPI es el adaptador de Bonita y concentra autenticación, cookies, token
  CSRF, traducción de payloads, timeouts y manejo de errores de esa integración.
- Bonita administra el flujo BPM y los temporizadores. No duplicar timers con
  tareas programadas, Celery o lógica del navegador.
- Emergencias, lotes, borradores y ofertas se persisten en la base PostgreSQL
  local. La futura API Nacional no debe recibir borradores de ofertas.
- Los permisos del frontend son solo una ayuda de navegación. Cada endpoint debe
  volver a autenticar y autorizar la operación en el backend.
- Mantener separadas las capas HTTP, casos de uso, persistencia e integraciones
  externas. Los handlers de FastAPI deben ser pequeños.

## Organización del código

- Rutas HTTP: `backend/app/api/routes/`.
- Configuración transversal y seguridad: `backend/app/core/`.
- Base, sesión y modelos de persistencia: `backend/app/db/`.
- Crear `backend/app/schemas/` para modelos Pydantic de entrada y salida.
- Crear `backend/app/services/` para reglas y casos de uso reutilizables.
- Crear `backend/app/integrations/bonita/` para el cliente y los contratos de
  Bonita. No colocar llamadas HTTPX directamente en las rutas.
- En el frontend, separar páginas, componentes, esquemas, hooks y cliente HTTP
  cuando `src/App.tsx` deje de ser una pantalla introductoria.
- No crear abstracciones genéricas antes de contar con dos usos reales.

## Python: tipado y estilo

- El backend usa Python 3.13 y sintaxis moderna: `list[str]`, `X | None` y tipos
  de `collections.abc` cuando corresponda.
- Toda función debe declarar tipos de parámetros y retorno, incluidas funciones
  internas, fixtures y dependencias de FastAPI.
- Evitar `Any`, diccionarios sin estructura y casts que oculten errores. En los
  límites HTTP usar modelos Pydantic; para estructuras internas usar dataclasses,
  enums, protocolos o tipos concretos.
- Los modelos SQLAlchemy deben usar el estilo 2.x con `Mapped[T]` y
  `mapped_column()`. No exponer instancias ORM como contrato público accidental.
- Representar estados y roles con enums, no con strings dispersos en el código.
- Usar fechas y horas conscientes de zona horaria y almacenar UTC. No usar
  `datetime.now()` sin zona.
- Mantener el acceso SQLAlchemy sincrónico mientras el proyecto use `Session`.
  Una ruta que haga I/O bloqueante debe ser `def`, o delegar correctamente si se
  adopta una pila asíncrona completa. No mezclar sesiones sync y async.
- Capturar excepciones específicas. No usar `except Exception` salvo en un borde
  externo donde se registre y transforme el fallo sin ocultarlo.
- Ruff define el formato y lint de Python. No introducir reglas de estilo
  manuales que contradigan su salida.

## TypeScript y React: tipado y componentes

- El código fuente del frontend usa TypeScript/TSX con modo `strict`. No agregar
  archivos JavaScript/JSX dentro de `src/` ni relajar `tsconfig.json` para ocultar
  errores; los archivos de configuración pueden permanecer en JavaScript.
- Tipar los payloads de API, props no triviales y retornos de hooks o funciones
  compartidas. Evitar `any`, tipos excesivamente amplios y casts que oculten
  errores; usar `unknown` en límites externos y validarlo antes de consumirlo.
- Zod define la validación en tiempo de ejecución de formularios y datos externos.
  Inferir sus tipos con `z.infer` cuando corresponda. TypeScript y la validación
  del navegador no reemplazan la validación Pydantic del backend.
- Usar React Hook Form para formularios y `useFieldArray` para lotes u ofertas
  dinámicas. No duplicar el mismo estado de campo con `useState`.
- Usar TanStack Query para estado remoto, mutaciones e invalidación. No copiar
  respuestas de la API a un contexto global ni implementar caché manual.
- Centralizar `fetch`, serialización y traducción de errores en un cliente de API.
  Las peticiones autenticadas por sesión deben usar `credentials: "include"`.
- Cada pantalla debe contemplar estados de carga, vacío, error y éxito.
- Componentes y archivos de componentes usan PascalCase; hooks usan el prefijo
  `use`; funciones y variables usan camelCase.
- Mantener JSX semántico, navegación por teclado, labels asociados a inputs,
  mensajes de error accesibles y diseño funcional desde 320 px.
- TypeScript y ESLint son obligatorios. Ejecutar `npm run typecheck` y no
  desactivar reglas globalmente para resolver un caso local sin documentar por qué.

## Docstrings, comentarios y documentación

- Escribir docstrings en español para servicios, integraciones, dependencias de
  seguridad, clases y funciones cuya intención o contrato no sea obvio.
- La primera línea debe explicar el efecto o responsabilidad, no repetir el
  nombre. Agregar secciones de argumentos, retorno y excepciones solo cuando
  aporten información que el tipado no expresa.
- Los endpoints deben tener resumen/descripción útil en OpenAPI y declarar su
  `response_model` y códigos de estado relevantes.
- Los comentarios explican decisiones, invariantes o motivos; no narran línea
  por línea lo que el código ya muestra.
- Actualizar README, `.env.example` y documentación de API cuando cambien comandos,
  variables, puertos, dependencias visibles o flujos de usuario.

## API y reglas de negocio

- Mantener los endpoints bajo `/api/v1` y respetar los nombres definidos por el
  grooming (`/emergencias`, `/ofertas`, `/convocatorias`).
- Validar en base de datos las reglas que puedan sufrir concurrencia; no confiar
  en una lectura previa hecha por el frontend.
- Usar restricciones `NOT NULL`, `CHECK`, `UNIQUE` y claves foráneas además de
  validaciones Pydantic cuando representen invariantes persistentes.
- Una convocatoria solo se publica con al menos un lote válido. Una oferta solo
  puede referenciar lotes publicados y cantidades positivas.
- Devolver errores consistentes y accionables. No filtrar detalles internos,
  credenciales, SQL ni respuestas sensibles de Bonita.
- Delimitar claramente cada transacción. Confirmar una operación solo cuando sus
  cambios locales sean coherentes; hacer rollback ante fallos.

## Base de datos y migraciones

- Todo cambio de esquema requiere una migración Alembic revisada manualmente.
- Importar cada módulo de modelos desde `backend/alembic/env.py` o desde un punto
  común importado por ese archivo para que `--autogenerate` vea su metadata.
- No modificar una migración que pueda haber sido aplicada por otra persona;
  crear una migración correctiva.
- Las migraciones deben incluir `upgrade()` y `downgrade()` viables y evitar
  pérdida de datos salvo requisito y aprobación explícitos.
- No usar SQLite para pruebas que dependan de enums, restricciones, transacciones
  o locking de PostgreSQL.
- Preparar trazabilidad mediante timestamps y relaciones explícitas. El control
  optimista de versión no sustituye un historial de versiones de ofertas.

## Integración con Bonita

- Usar un cliente HTTPX reutilizable con timeout explícito y ciclo de vida claro.
- Tipar y validar las respuestas externas antes de persistir identificadores.
- Guardar `caseId`/`processInstanceId` junto con el estado de sincronización y el
  último error seguro para permitir reintentos trazables.
- No reintentar ciegamente el POST que inicia una instancia: un timeout puede
  ocurrir después de que Bonita haya creado el caso. Diseñar idempotencia o una
  verificación antes del reintento.
- Mantener el mapeo de variables alineado con el `.bos`; como mínimo:
  `idEmergencia`, `gravedad` y `zona`.
- Las pruebas automatizadas no dependen de un Runtime Bonita real: usar RESPX.
  Reservar el Runtime real para pruebas de integración manuales o E2E controladas.

## Autenticación y seguridad

- Nunca guardar ni registrar contraseñas en texto plano. Usar pwdlib con Argon2.
- Las sesiones locales deben contener solo un identificador mínimo; cargar usuario,
  organización y rol vigentes desde PostgreSQL.
- Generar secretos fuera del repositorio. No agregar `.env`, cookies, tokens,
  credenciales reales ni dumps de base de datos a Git.
- Configurar cookies `HttpOnly`, `SameSite` apropiado y `Secure` en producción.
- Mantener orígenes CORS explícitos cuando `allow_credentials=True`.
- Probar tanto operaciones permitidas como denegadas para cada rol. Ocultar un
  botón nunca cuenta como control de acceso.

## Estrategia de pruebas

- Todo cambio funcional debe incluir pruebas proporcionales al riesgo. Un bugfix
  debe agregar una prueba que falle antes del arreglo.
- Nombrar pruebas por comportamiento observable, no por la implementación interna.
- Mantenerlas deterministas: no depender de red externa, hora local, orden global
  ni datos dejados por otra prueba.
- Backend: usar Pytest para servicios y endpoints; RESPX para Bonita; PostgreSQL
  real para comportamiento específico de la base. Sobrescribir dependencias de
  FastAPI y limpiar los datos entre casos.
- Cubrir como mínimo validaciones, transiciones de estado, rollback, autorización
  por rol y fallos de Bonita. No perseguir cobertura alta mediante asserts vacíos.
- Frontend: usar Vitest y Testing Library para probar lo que ve y hace el usuario;
  MSW para respuestas HTTP. Preferir queries accesibles y `user-event`; evitar
  snapshots grandes y mocks de detalles internos.
- E2E: Playwright cubre al menos el camino Municipio registra → Bonita se vincula
  → Coordinador crea/publica lotes → ONG oferta, más un caso representativo de
  acceso denegado o fallo de integración.

## Dependencias y archivos generados

- Agregar una dependencia solo si resuelve una necesidad concreta no cubierta
  razonablemente por el stack. Explicar las incorporaciones no obvias.
- Dependencias usadas en producción van en `requirements.txt` o `dependencies`;
  herramientas de prueba/calidad van en `requirements-dev.txt` o `devDependencies`.
- Actualizar `package.json` mediante npm y versionar también `package-lock.json`.
  No editar el lockfile manualmente.
- No versionar `.env`, `node_modules/`, `dist/`, `__pycache__/`, coberturas,
  cachés de herramientas ni archivos del editor.

## Comandos de verificación

Después de clonar el repositorio, activar los hooks compartidos con
`git config core.hooksPath .githooks`. El hook `pre-commit` ejecuta los linters y
el typecheck que correspondan a los archivos staged. No usar `--no-verify` salvo
una emergencia documentada; los checks obligatorios de CI siguen siendo la
fuente de verdad para integrar cambios.

Desde la raíz, con las imágenes construidas:

```bash
docker compose run --rm backend pytest
docker compose run --rm backend pytest --cov=app --cov-report=term-missing
docker compose run --rm backend ruff check .
docker compose run --rm backend ruff format --check .
docker compose run --rm frontend npm run lint
docker compose run --rm frontend npm run typecheck
docker compose run --rm frontend npm test
docker compose run --rm frontend npm run build
```

Con los servicios levantados y los navegadores de Playwright instalados:

```bash
cd frontend
npm run test:e2e
```

Ejecutar primero las comprobaciones del área modificada. Antes de integrar una
historia, ejecutar lint, tests y build de todas las capas afectadas.

## Definición de terminado

Una tarea está terminada cuando:

- cumple el grooming y preserva los invariantes de arquitectura;
- incluye migración cuando cambia el esquema;
- valida permisos y entradas en el backend;
- contempla carga, vacío, error y éxito en la interfaz afectada;
- incluye o actualiza pruebas relevantes;
- pasa lint, pruebas y build de las capas modificadas;
- obtiene un resultado exitoso del check `quality` en GitHub Actions;
- actualiza configuración y documentación cuando corresponde;
- no deja secretos, artefactos generados ni cambios ajenos a la tarea.
