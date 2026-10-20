# CORS y dominios del frontend

Los dominios se configuran con **`CORS_ORIGINS` en el `.env` de RescueSync**.
No hay que editar código para agregar un frontend. Compose transmite esta
variable al backend; fuera de Compose se configura en el entorno de la API.

## Agregar o quitar dominios

1. Agregar el origen nuevo a la lista JSON del `.env`, conservando los anteriores
   que deban seguir funcionando:

   ```dotenv
   CORS_ORIGINS=["http://localhost:5173","http://localhost:4173","https://app.example.org","https://admin.example.org"]
   ```

2. Usar **el origen del frontend que aparece en la barra del navegador**:
   protocolo, dominio y puerto si es distinto del predeterminado. No agregar
   `/api/v1`, otra ruta, credenciales, query ni fragmento. La URL pública de la
   API no reemplaza los orígenes de sus consumidores.

3. Recrear el servicio para cargar el entorno actualizado:

   ```bash
   docker compose up -d --no-deps --force-recreate backend
   ```

   `docker compose restart backend` no actualiza variables de un contenedor
   existente. No hace falta reconstruir la imagen para cambiar esta lista.
   En cloud, actualizar `CORS_ORIGINS` en las variables del servicio y ejecutar
   su reinicio/redeploy para que todos los procesos reciban el valor nuevo.
   El panel del proveedor debe recibir el JSON, sin comillas adicionales
   envolviendo toda la lista.

4. Verificar el preflight usando uno de los orígenes agregados:

   ```bash
   curl -i -X OPTIONS http://localhost:8000/api/v1/auth/login \
     -H 'Origin: https://app.example.org' \
     -H 'Access-Control-Request-Method: POST' \
     -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
   ```

   Debe responder 200, `Access-Control-Allow-Origin: https://app.example.org`,
   `Access-Control-Allow-Credentials: true` y `Vary: Origin`. Al desplegar,
   reemplazar localhost por la URL HTTPS de la API y repetir la comprobación.
   Un origen ajeno debe devolver 400 en el preflight y no recibir permiso CORS.

HTTP y HTTPS, distintos puertos, `www` y otros subdominios son orígenes distintos.
Se eliminan espacios exteriores, barras finales, duplicados y puertos
predeterminados, y se normaliza el host. Comodines como `*` y `*.example.org`
se rechazan al iniciar. Para deshabilitar acceso desde otros orígenes usar `[]`.
Las variables del entorno del proceso tienen prioridad sobre un archivo `.env`.

## Cookies, WebSocket y frontend desplegado

RescueSync usa cookies de sesión y token CSRF. El cliente HTTP ya utiliza
`credentials: "include"`; las escrituras autenticadas deben conservar
`X-CSRF-Token`. La misma lista `CORS_ORIGINS` autoriza el `Origin` del WebSocket
de notificaciones, que también exige sesión. CORS HTTP no sustituye ese control.

Para frontend y API en **sitios distintos**, sobre HTTPS, configurar además:

```dotenv
SESSION_COOKIE_SAMESITE=none
SESSION_COOKIE_SECURE=true
FRONTEND_PUBLIC_URL=https://app.example.org
```

Compose ahora transmite las opciones de cookie del `.env` al backend. Por defecto
se usa `SameSite=lax`; `SESSION_COOKIE_SECURE` vacío conserva el valor automático
por `APP_ENV` (seguro en producción). El backend rechaza `SameSite=None` sin
cookies Secure. Cambiar `FRONTEND_PUBLIC_URL` configura los enlaces enviados por
correo; no agrega automáticamente ese dominio a CORS.

Las restricciones del navegador sobre cookies de terceros pueden impedir una
sesión entre sitios aun con CORS correcto. La imagen Nginx del frontend permite
publicar `/api/` bajo su mismo origen, reduciendo esa dependencia. Si se usa un
frontend con API separada, configurar también `VITE_API_URL` con la URL pública
y `/api/v1` al construir el frontend; esta variable sí se incorpora al build.

## Diagnóstico

- **Preflight 400:** comparar el header `Origin` de DevTools con la lista del
  servicio; revisar puerto, protocolo y las cabeceras solicitadas.
- **No aparece un dominio nuevo:** recrear el servicio y comprobar únicamente
  la variable relevante, sin imprimir secretos del entorno:
  `docker compose exec backend python -c 'from app.core.config import get_settings; print(get_settings().cors_origins)'`.
- **401/403 con cabeceras CORS:** revisar sesión, cookies y CSRF. La configuración
  CORS no elimina esos controles.
- **500:** las respuestas generadas por la aplicación ahora mantienen CORS para
  orígenes permitidos. Revisar el error del servidor; CORS no lo corrige.
- **502/503 del proxy o conexión TLS fallida:** comprobar disponibilidad y proxy.
  Una respuesta creada fuera de FastAPI no pasa por su middleware CORS.
- **Cabeceras duplicadas:** dejar CORS en FastAPI; evitar que el proxy agregue
  otro `Access-Control-Allow-Origin` sobre la misma respuesta.

La API nacional tiene su propio `.env` y su
[guía independiente](../../RescueSyncAPI/docs/cors.md). Las peticiones de FastAPI
o Bonita hacia ella son servidor a servidor y no dependen de CORS.

Referencias: [CORS en FastAPI](https://fastapi.tiangolo.com/tutorial/cors/) y
[CORS sobre respuestas de error en Starlette](https://starlette.dev/middleware/#corsmiddleware-global-enforcement).
