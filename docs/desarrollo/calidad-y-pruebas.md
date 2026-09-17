# Calidad y pruebas

## Backend

```bash
docker compose run --rm backend pytest
docker compose run --rm backend pytest --cov=app --cov-report=term-missing
docker compose run --rm backend ruff check .
docker compose run --rm backend ruff format --check .
```

Las integraciones automáticas con Bonita usan RESPX. El Runtime real queda
reservado para las pruebas E2E controladas descritas en
[`docs/bonita/pruebas-e2e.md`](../bonita/pruebas-e2e.md).

## Frontend

```bash
docker compose run --rm frontend npm run lint
docker compose run --rm frontend npm run typecheck
docker compose run --rm frontend npm test
docker compose run --rm frontend npm run build
```

Para Playwright se requiere Node.js 24 en el host y la instalación inicial del
navegador administrado:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

## Hook compartido

Después de clonar, activar una vez los hooks versionados:

```bash
git config core.hooksPath .githooks
```

El `pre-commit` ejecuta Ruff cuando hay Python staged y ESLint junto con el
typecheck cuando hay JavaScript o TypeScript staged. Usa las herramientas
locales si están disponibles y, en caso contrario, las imágenes de Compose, que
deben haberse construido previamente.

## Integración continua

`.github/workflows/quality.yml` se ejecuta en cada pull request y en cada push a
`develop` o `main`. Verifica Ruff, migraciones y pruebas del backend, además de
tipos, ESLint, pruebas y build del frontend. El job final se llama `quality` y
es el status check obligatorio antes de integrar.

Antes de solicitar revisión se ejecutan primero los controles del área
modificada. Antes de integrar una historia deben pasar lint, pruebas y build de
todas las capas afectadas.
