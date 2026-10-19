# Despliegue y operación de Bonita

El entorno de Compose agrega tres servicios:

- `bonita-db`: PostgreSQL exclusivo del motor y del BDM de Bonita;
- `bonita`: Runtime 10.4.0;
- `bonita-deploy`: inicializador de ejecución única que instala y habilita el
  proceso.

FastAPI y el inicializador alcanzan al Runtime en
`http://bonita:8080/bonita`. Los conectores de Bonita alcanzan FastAPI en
`http://backend:8000`.

## Artefacto y versión

[`docs/RescueSync-1.5.bar`](../RescueSync-1.5.bar) es el único artefacto BPM
versionado. `BONITA_PROCESS_NAME` y `BONITA_PROCESS_VERSION` determinan la
definición compatible.

`bonita-deploy` se niega a instalar un `.bar` cuyo nombre o versión no coincide
con esas variables. La prueba `test_bar_versionado.py` revisa además el contrato
y los parámetros en CI.

## Instalación automática

El inicializador espera al Runtime, importa la organización, crea los usuarios
referenciados por `actorMapping.xml`, instala el `.bar` y habilita el proceso.
`BONITA_ACTOR_PASSWORD` define la contraseña inicial; cuando está vacía se
genera una aleatoria y no se registra.

Durante la instalación inyecta estos parámetros:

| Parámetro de Bonita  | Variable de entorno            | Uso                                    |
| -------------------- | ------------------------------ | -------------------------------------- |
| `backendBaseUrl`     | `BONITA_BACKEND_BASE_URL`      | URL de FastAPI para callbacks.         |
| `callbackToken`      | `BONITA_CALLBACK_TOKEN`        | Token `Bearer` de callbacks.           |
| `ventanaOfertasMs`   | `BONITA_OFFER_WINDOW_MS`       | Duración de la ventana de ofertas.     |
| `connectTimeoutMs`   | `BONITA_CONNECT_TIMEOUT_MS`    | Timeout de conexión de los conectores. |
| `readTimeoutMs`      | `BONITA_READ_TIMEOUT_MS`       | Timeout de lectura de los conectores.  |
| `nationalApiBaseUrl` | `BONITA_NATIONAL_API_BASE_URL` | Reservado para la Entrega 3.           |

## Idempotencia y diferencias de configuración

Bonita Community no permite modificar los parámetros de una definición ya
instalada. El inicializador actúa así:

| Situación                                | Comportamiento                            |
| ---------------------------------------- | ----------------------------------------- |
| Proceso instalado con los mismos valores | No realiza cambios.                       |
| Otro valor para un parámetro no secreto  | Advierte el nombre y continúa.            |
| Otro `callbackToken`                     | Termina con error sin mostrar el secreto. |
| Definición sin resolver y sin casos      | La elimina y reinstala.                   |
| Definición con casos                     | Nunca la elimina ni reemplaza.            |

El contenedor `bonita-deploy` termina con `Exited (0)` cuando la instalación fue
correcta. Ese estado es esperado. Compose espera primero el health de FastAPI
para desplegar los callbacks; a su vez, el comando normal del frontend espera
que `/api/v1/health/bonita` confirme la definición habilitada antes de iniciar
Vite. Los comandos de prueba que reemplazan ese comando no dependen de un
Runtime real.

## Diagnóstico

```bash
docker compose ps -a
docker compose logs bonita-deploy
curl --fail http://localhost:8000/api/v1/health/bonita
```

El health responde `200` cuando el login funciona y el proceso configurado está
`RESOLVED` y `ENABLED`; de lo contrario responde `503` sin filtrar detalles del
Runtime.

También puede comprobarse desde el contenedor, sin crear casos:

```bash
docker compose exec backend python -m app.scripts.check_bonita_api
```

## Actualizar el proceso

Con volúmenes existentes, `docker compose up --build` instala una versión nueva
al lado de la anterior. El backend usa la indicada por
`BONITA_PROCESS_VERSION`; los casos anteriores continúan en su definición
original.

El procedimiento completo de versionado está en
[`proceso-bpm.md`](./proceso-bpm.md#cambiar-la-versión).

## Reinstalar parámetros

Para aplicar otro token o una ventana distinta es necesario recrear solamente
los volúmenes de Bonita. **Este procedimiento elimina todos los casos de Bonita,
aunque conserva la base local de RescueSync; solo debe usarse en un entorno
descartable:**

```bash
docker compose rm -sf bonita bonita-db
docker volume rm rescuesync_bonita_db_data rescuesync_bonita_temp rescuesync_bonita_work
docker compose up -d --build
```

Antes de ejecutarlo, verificar el nombre real del proyecto Compose y de sus
volúmenes con `docker volume ls`.
