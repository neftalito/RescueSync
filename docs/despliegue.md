# Imágenes de producción

Los Dockerfiles de backend y frontend incluyen un target de producción:

```bash
docker build --target production -t rescuesync-backend ./backend
docker build --target production -t rescuesync-frontend ./frontend
```

La imagen final del frontend utiliza Nginx y redirige `/api/` al servicio
backend. La imagen final del backend ejecuta un único proceso FastAPI; la
cantidad de réplicas se configura en la plataforma de despliegue.

Esta guía documenta solo los artefactos disponibles. La topología, los secretos,
TLS, observabilidad, backups y estrategia de rollout deben definirse para el
entorno donde se publique la aplicación antes de considerarlo productivo.
