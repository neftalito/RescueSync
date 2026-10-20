# Pruebas E2E con Bonita Runtime

Las pruebas automatizadas habituales usan RESPX y no necesitan un Runtime real.
Esta guía corresponde a una verificación controlada con Bonita, FastAPI y
PostgreSQL levantados. Para recorrer el proceso completo con la API nacional
(validación, compromiso, liberación y cierre) seguir la
[prueba local paso a paso](./prueba-local-integracion-nacional.md).

## Verificación de disponibilidad

Sin crear casos:

```bash
curl --fail http://localhost:8000/api/v1/health/bonita
docker compose exec backend python -m app.scripts.check_bonita_api
```

## Ejecutar la prueba

Con el entorno levantado:

```bash
docker compose exec -e RUN_BONITA_E2E=1 backend \
  pytest tests/e2e/test_bonita_runtime.py -m bonita_e2e -rs
```

La prueba crea una emergencia, una convocatoria abierta y una oferta en
PostgreSQL; inicia y vincula el caso; verifica el rechazo del contrato, las
variables, la reconciliación y la publicación. También comprueba que
`notificar-apertura` alinee `cierra_en` con el timer. Al terminar cancela el caso
y elimina sus datos locales.

La suite normal omite esta prueba para conservar determinismo y no depender de
un servicio externo.

## Cubrir el vencimiento del timer

Con la ventana predeterminada de dos horas, la prueba se detiene después de la
notificación y marca el resto como `SKIPPED`. Para recorrer también el cierre, la
consolidación y la compuerta, se instala el proceso con una ventana de 60 segundos
o menos en un proyecto Compose aislado:

```bash
export BONITA_PORT=18080 BACKEND_PORT=18000 POSTGRES_PORT=15432 FRONTEND_PORT=15173
BONITA_OFFER_WINDOW_MS=15000 docker compose -p rescuesync-e2e up -d --build \
  db migrate backend bonita-db bonita bonita-deploy
docker compose -p rescuesync-e2e exec -e RUN_BONITA_E2E=1 \
  -e BONITA_E2E_TIMEOUT_SECONDS=60 backend \
  pytest tests/e2e/test_bonita_runtime.py -m bonita_e2e -rs
docker compose -p rescuesync-e2e down -v
```

El último comando elimina los volúmenes del proyecto aislado
`rescuesync-e2e`. Antes de ejecutarlo hay que comprobar que `-p rescuesync-e2e`
esté presente para no afectar el entorno de desarrollo habitual.

## Cuándo ejecutar esta prueba

- Al publicar una versión nueva del `.bar`.
- Al cambiar contratos, callbacks, actor mappings o parámetros del proceso.
- Antes de una demostración o entrega que dependa del recorrido BPM completo.

No reemplaza las pruebas RESPX: complementa la verificación rápida y
determinista del cliente con una prueba del Runtime real.
