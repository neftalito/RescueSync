# Demo local y con Cloudflare Tunnel

Esta guía publica el frontend de producción mediante Nginx bajo una sola URL.
El navegador usa rutas relativas `/api/v1`, por lo que Nginx sirve React y
reenvía tanto HTTP como WebSocket al backend sin exponer FastAPI ni Bonita.

Cloudflare Tunnel admite WebSocket. El endpoint de RescueSync es
`/api/v1/notificaciones/ws` y se autentica con la misma cookie de sesión. El
backend también comprueba que el encabezado `Origin` coincida exactamente con
uno de los valores de `CORS_ORIGINS`.

## Levantar el entorno base

Crear `.env` a partir del ejemplo si todavía no existe:

```bash
cp .env.example .env
```

Para usar simultáneamente el frontend de desarrollo y el frontend de demo,
mantener inicialmente estos orígenes:

```dotenv
CORS_ORIGINS=["http://localhost:5173","http://localhost:4173"]
```

Levantar RescueSync y comprobar su estado:

```bash
docker compose up -d --build
docker compose ps
curl http://localhost:8000/api/v1/health
```

El frontend de desarrollo continúa disponible en
<http://localhost:5173>. No se debe compartir esa URL: su compilación apunta a
`localhost:8000`, que en un equipo visitante identificaría al propio visitante.

## Preparar el frontend de demo

Construir el target de producción con una URL de API relativa:

```bash
docker build \
  --target production \
  --build-arg VITE_API_URL=/api/v1 \
  -t rescuesync-demo-frontend \
  ./frontend
```

Compose crea normalmente la red `rescuesync_default`. Confirmar el nombre con:

```bash
docker network ls
```

Eliminar una instancia anterior, si existe, y ejecutar la imagen dentro de esa
red:

```bash
docker rm -f rescuesync-demo-frontend 2>/dev/null || true

docker run -d \
  --rm \
  --name rescuesync-demo-frontend \
  --network rescuesync_default \
  -p 4173:80 \
  rescuesync-demo-frontend
```

Validar primero la ruta local completa, incluido el proxy hacia FastAPI:

```bash
curl http://localhost:4173/api/v1/health
```

La aplicación queda disponible localmente en <http://localhost:4173>. El origen
`http://localhost:4173` debe permanecer en `CORS_ORIGINS` para que su WebSocket
sea aceptado.

## Publicar con un Quick Tunnel

Conservar abierto el proceso siguiente durante toda la demostración:

```bash
cloudflared tunnel --url http://localhost:4173
```

El comando informa una URL HTTPS temporal, por ejemplo:

```text
https://nombre-aleatorio.trycloudflare.com
```

Copiar la URL exacta, sin una barra final, a `CORS_ORIGINS` en `.env`, sin quitar
los orígenes locales. Por ejemplo:

```dotenv
CORS_ORIGINS=["http://localhost:5173","http://localhost:4173","https://nombre-aleatorio.trycloudflare.com"]
```

Recrear el backend para que lea la nueva configuración:

```bash
docker compose up -d --force-recreate backend
```

No es necesario reconstruir el frontend por este cambio. Compartir solamente la
URL HTTPS generada por Cloudflare; no publicar los puertos de FastAPI, Bonita o
PostgreSQL.

Cada reinicio de un Quick Tunnel puede producir otro hostname. Cuando cambie,
reemplazar el valor anterior en `CORS_ORIGINS` y volver a recrear el backend. Un
túnel administrado con hostname estable evita ese paso para demostraciones
recurrentes.

## Verificar el WebSocket

Iniciar sesión desde la URL que se quiera probar y abrir las herramientas de
desarrollo del navegador. La solicitud a
`/api/v1/notificaciones/ws` debe quedar conectada y responder con
`101 Switching Protocols`.

El log esperado de FastAPI contiene una conexión WebSocket aceptada. Si muestra
un GET HTTP con respuesta `404`, la imagen del frontend de demo es anterior al
ajuste de Nginx o no preserva los encabezados `Upgrade` y `Connection`; volver a
construir la imagen y recrear el contenedor. Si la conexión recibe `403` o se
cierra con el código `1008`, revisar que el origen usado por el navegador figure
exactamente en `CORS_ORIGINS` y que el backend haya sido recreado.

Para confirmar qué configuración recibió Compose:

```bash
docker compose config | grep -A1 CORS_ORIGINS
```

## Finalizar la demo

Interrumpir `cloudflared` con `Ctrl+C` y detener el contenedor de Nginx:

```bash
docker stop rescuesync-demo-frontend
docker compose down
```

El contenedor de demo se elimina automáticamente porque se ejecutó con `--rm`.
`docker compose down` conserva los volúmenes; agregar `--volumes` también borra
las bases de datos y no corresponde al cierre normal de una demostración.

Referencias oficiales:

- [Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).
- [Compatibilidad de Cloudflare Tunnel con WebSocket](https://developers.cloudflare.com/cloudflare-one/faq/cloudflare-tunnels-faq/).
