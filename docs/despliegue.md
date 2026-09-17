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

La API crea un administrador inicial cuando no existe ninguno activo. Antes del
primer despliegue productivo se deben establecer `ADMIN_EMAIL` y
`ADMIN_INITIAL_PASSWORD` con valores propios. La contraseña es temporal y el
primer login obliga a reemplazarla; el bootstrap nunca registra ni vuelve a
aplicar la clave sobre una cuenta existente.
