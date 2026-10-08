# Documentación de RescueSync

Este índice separa la puesta en marcha, que permanece resumida en el
[`README` principal](../README.md), de las guías técnicas y los artefactos de
referencia.

## Desarrollo

- [Autenticación local](./autenticacion-local.md): administrador inicial,
  gestión de usuarios, contraseñas, seed, sesiones, CSRF y matriz RBAC.
- [Inventario nacional](./inventario-nacional.md): Mis recursos, vinculación de
  ONGs, conexión nacional, seeds coordinados y pruebas manuales.
- [Migraciones](./desarrollo/migraciones.md): modelos SQLAlchemy y flujo de
  trabajo con Alembic.
- [Calidad y pruebas](./desarrollo/calidad-y-pruebas.md): comandos, hooks,
  verificaciones de CI y pruebas frontend.
- [Flujo actual](./flujo-actual.md): recorrido operativo, notificaciones y mapa
  de endpoints implementados.
- [Imágenes de producción](./despliegue.md): targets Docker disponibles.
- [Demo local y con Cloudflare Tunnel](./demo-cloudflare.md): publicación del
  frontend de producción, configuración de orígenes y WebSocket.

Las reglas obligatorias de ramas, arquitectura, código y definición de terminado
están en [`AGENTS.md`](../AGENTS.md). No se duplican aquí para mantener una sola
fuente de verdad.

## Bonita BPM

- [Proceso BPM vigente](./bonita/proceso-bpm.md): alcance de la versión 1.2,
  contrato inicial y recorrido implementado.
- [Cliente HTTPX reutilizable](./bonita/cliente-httpx.md): inyección, ciclo de
  vida, operaciones, errores y pruebas con RESPX.
- [Despliegue y operación](./bonita/despliegue-y-operacion.md): instalación del
  `.bar`, parámetros, actualizaciones y diagnóstico.
- [Callbacks hacia FastAPI](./bonita/callbacks.md): endpoints internos,
  autenticación, correlación e idempotencia.
- [Pruebas E2E con el Runtime](./bonita/pruebas-e2e.md): verificación manual y
  entorno aislado con una ventana breve.
- [Diagnóstico histórico del modelado](./bonita/diagnostico-modelado-historico.md):
  análisis del antiguo proyecto `.bos` y decisiones que llevaron al `.bar`
  vigente. No es una guía operativa actual.

## Modelo y planificación

- [Modelo de base de datos](./modelo-base-datos-rescuesync.md), con el diagrama
  Mermaid vigente dentro del documento.
- [División de tareas de la Entrega 2](./DIVISION_TAREAS_ENTREGA_2.md).
- [Gantt de ejecución real de la Entrega 2](./generated/gantt-entrega-2.pdf),
  generado con las horas efectivas de `Grooming Etapa Actual.xlsx` y las
  precedencias de T1–T21. Se regenera desde la raíz con
  `python docs/generar_gantt.py`; requiere GitHub CLI autenticado y el
  Playwright instalado en `frontend`.

## Fuentes de verdad funcionales

- [`Trabajo integrador 2026.pdf`](<./Trabajo integrador 2026.pdf>).
- [`Grooming Etapa 2.pdf`](<./Grooming Etapa 2.pdf>).
- [`Descripción textual del flujo BPM.pdf`](<./Descripción textual del flujo BPM.pdf>).
- [`RescueSync-1.2.bar`](./RescueSync-1.2.bar), único artefacto BPM desplegable
  versionado. El proyecto fuente `.bos` no forma parte del repositorio.
