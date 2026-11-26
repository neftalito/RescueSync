# Prueba local paso a paso: RescueSync + Bonita + API nacional

> Actualización 20/10/2026: [perfiles informativos](../perfiles-competencia.md) reemplaza las
> reglas de certificación, habilitación previa y clasificación por riesgo de este
> documento. Las referencias a esas reglas describen el comportamiento anterior.


Esta guía levanta en local, con Docker, los dos repositorios:

- `RescueSync`: frontend, backend, PostgreSQL y Bonita 10.4.
- `RescueSyncAPI`: Sistema Nacional y su PostgreSQL.

Después recorre manualmente el proceso BPM `RescueSync 1.5` adaptado, desde la
alerta hasta la emergencia `RESUELTA`. El detalle del proceso está en
[proceso 1.5 adaptado](./contratos-t36-t37.md#proceso-14-adaptado-mínimo-entregable).

| Servicio                              | URL local                      |
| ------------------------------------- | ------------------------------ |
| Frontend RescueSync                   | <http://localhost:5173>        |
| Backend RescueSync (Swagger)          | <http://localhost:8000/docs>   |
| Bonita Portal (`install` / `install`) | <http://localhost:8080/bonita> |
| API nacional (Swagger)                | <http://localhost:8001/docs>   |
| Mailpit (correos de notificación)     | <http://localhost:8025>        |

La guía arranca desde cero. Así ningún `idEmergencia` local coincide con un
proyecto nacional de pruebas anteriores (ver
[problemas frecuentes](#problemas-frecuentes)).

## 0. Requisitos

- Docker con Compose v2.
- Puertos libres: 5173, 8000, 8001, 8025, 8080, 5432 y 5433.
- Repositorios clonados uno junto al otro:
  - `RescueSyncAPI` en la rama de integración (`develop`)
  - `RescueSync` en la rama que contiene el BAR adaptado
- `docs/` de RescueSync contiene **un único** `.bar`. Comprobarlo con `ls docs/*.bar`.

## 1. API nacional (raíz de `RescueSyncAPI`)

1. Crear la configuración. Los valores de `.env.example` sirven en desarrollo:
   ```bash
   cp .env.example .env
   ```
   Con `JWT_SECRET` vacío, la API genera una clave temporal por proceso. Es válido para esta prueba porque Bonita inicia sesión en cada tarea. Para que los tokens sobrevivan a un reinicio de la API, definir un valor fijo de al menos 32 caracteres.
2. Partir de cero. Ojo: borra la base nacional local, incluida la cuenta de integración:
   ```bash
   docker compose down -v
   ```
3. Construir y levantar. El servicio `migrate` aplica Alembic antes de iniciar la API:
   ```bash
   docker compose up -d --build
   ```
4. Cargar los datos demo (ONGs, certificaciones, recursos, administrador y cuentas técnicas):
   ```bash
   docker compose run --rm api python -m app.scripts.seed
   ```
5. Crear la cuenta `INTEGRACION` que usan Bonita y el backend local. El comando pide una contraseña de 12 caracteres o más; anotarla, porque va en el `.env` local:
   ```bash
   docker compose run --rm api python -m app.scripts.bootstrap_integracion --login integracion-rescuesync --sistema-origen rescuesync-local
   ```
6. Comprobación: en <http://localhost:8001/docs>, `POST /api/v1/login` con `{"identificadorLogin": "integracion-rescuesync", "password": "<la del paso 5>"}` responde 200 con `access_token`.

### Datos demo relevantes del seed nacional

| ONG                                               | Estado     | Habilitada para                                                 | Recursos                                                    |
| ------------------------------------------------- | ---------- | --------------------------------------------------------------- | ----------------------------------------------------------- |
| Ayuda Sin Fronteras (`ong@rescuesync.org`)        | HABILITADA | **Personal paramédico** hasta ALTA; **Ambulancias** hasta MEDIA | Personal paramédico: 12 personas; Agua potable: 5000 litros |
| Red Médica Solidaria (`redmedica@rescuesync.org`) | PENDIENTE  | nada                                                            | Personal paramédico; Ambulancias                            |

El seed incluye a propósito acreditaciones **vencidas, revocadas y futuras** para
mostrar la validación por niveles. La de **Agua potable** de Ayuda Sin Fronteras
empieza a regir un mes después del seed. Por eso una oferta de agua se clasifica
como `SIN_HABILITACION` ("La acreditación no inició"); no es un error.

## 2. RescueSync (raíz de `RescueSync`)

### 2.1 Variables de entorno

```bash
cp .env.example .env
```

Completar en `.env` estas variables. Las demás pueden quedar como en `.env.example`:

```dotenv
# Sistema Nacional (desde los contenedores locales)
NACIONAL_BASE_URL=http://host.docker.internal:8001/api/v1
# Igual al --sistema-origen del bootstrap. Configurarlo ANTES de publicar lotes:
# cada ronda congela el sistema de origen al publicarse.
NACIONAL_SISTEMA_ORIGEN=rescuesync-local
# Clave Fernet estable. Generarla con:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
NACIONAL_ENCRYPTION_KEY=<clave-fernet>
# Cuenta INTEGRACION creada en el paso 1.5 (alta automática de ONGs)
NACIONAL_APROVISIONAMIENTO_LOGIN=integracion-rescuesync
NACIONAL_APROVISIONAMIENTO_PASSWORD=<contraseña del paso 1.5>

# Bonita: proceso, credencial nacional y ventana corta para probar
BONITA_PROCESS_VERSION=1.5
BONITA_NATIONAL_API_BASE_URL=http://host.docker.internal:8001
BONITA_NATIONAL_API_LOGIN=integracion-rescuesync
BONITA_NATIONAL_API_PASSWORD=<contraseña del paso 1.5>
# 2 minutos de ventana de ofertas (el valor por defecto es 2 horas)
BONITA_OFFER_WINDOW_MS=120000
```

Notas sobre estas variables:

- `BONITA_NATIONAL_API_BASE_URL` va **sin** `/api/v1`; `NACIONAL_BASE_URL`, **con** `/api/v1`.
- `BONITA_CALLBACK_TOKEN` puede quedar con el valor de desarrollo, que tiene 32 caracteres o más.
- Si `BONITA_NATIONAL_API_LOGIN` o `BONITA_NATIONAL_API_PASSWORD` quedan vacías, `bonita-deploy` falla y Bonita no instala el proceso.

### 2.2 Levantar

1. Partir de cero. Esto borra la base local y la de Bonita:
   ```bash
   docker compose down -v
   ```
   Es necesario cada vez que se reemplaza el `.bar`: el deploy no sustituye un proceso que ya tiene casos.
2. Construir y levantar:
   ```bash
   docker compose up -d --build
   ```
3. Esperar a que `bonita-deploy` termine, en uno o dos minutos:
   ```bash
   docker compose logs -f bonita-deploy
   ```
   La última línea esperada es `Despliegue de Bonita finalizado correctamente.` Cortar con Ctrl+C.
4. Cargar los datos demo locales (usuarios, organizaciones y emergencias de ejemplo):
   ```bash
   docker compose run --rm backend python -m app.scripts.seed
   ```

### 2.3 Comprobaciones

- `curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/v1/health/bonita` devuelve `200`.
- En Bonita Portal → Administración → Procesos aparece **RescueSync 1.5** _Enabled / Resolved_.
- El contrato del BAR versionado devuelve `2 passed`:
  ```bash
  docker compose run --rm -v "$PWD/docs:/docs:ro" backend pytest -q tests/integrations/bonita/test_bar_versionado.py
  ```

## 3. Casos de prueba (UI en <http://localhost:5173>)

Usuarios del seed local (contraseña = nombre del usuario + `123`):

| Rol                | Usuario                      | Contraseña       |
| ------------------ | ---------------------------- | ---------------- |
| Operador municipal | `municipio@rescuesync.org`   | `municipio123`   |
| Centro coordinador | `coordinador@rescuesync.org` | `coordinador123` |
| ONG habilitada     | `ong@rescuesync.org`         | `ong123`         |
| ONG pendiente      | `redmedica@rescuesync.org`   | `redmedica123`   |
| Auditor            | `auditor@rescuesync.org`     | `auditor123`     |

Dónde observar cada paso:

- **Bonita Portal** → Administración → Casos → caso de la emergencia (índice `idEmergencia`): tareas, estado y variables.
- **Swagger nacional**:
  - `GET /api/v1/compromisos/{id}`: estado del compromiso.
  - `GET /api/v1/recursos/disponibilidad`: stock comprometido o disponible.
- **Logs**: `docker compose logs -f backend` y `docker logs rescuesync-bonita-1 --since 10m`.

> En los lotes, la capacidad se elige por su **nombre** del catálogo nacional.
> Para los casos que deben validar, usar **"Personal paramédico"** (unidad
> `personas`). No usar "Personal médico", que ninguna ONG demo tiene habilitado.

### Caso A — Camino feliz completo

| #   | Quién        | Acción                                                                                                 | Resultado esperado                                                                                                                                                        |
| --- | ------------ | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Municipio    | _Nueva emergencia_, gravedad **MEDIA**                                                                 | Emergencia REGISTRADA. En Bonita, un caso nuevo con `Generar lotes de necesidades` lista.                                                                                 |
| 2   | Coordinador  | Lotes de la emergencia: **Personal paramédico**, 2 `personas`, riesgo **MEDIA** → **Publicar**         | Convocatoria abierta. Bonita completa `Generar lotes` y queda en el timer `EsperarOfertas`.                                                                               |
| 3   | ONG (`ong@`) | _Convocatorias_ → nueva oferta: 2 personas sobre el lote, eligiendo su recurso **Personal paramédico** | Oferta presentada.                                                                                                                                                        |
| 4   | —            | Esperar unos 2 minutos                                                                                 | Bonita cierra la convocatoria, consolida, prepara la evaluación, valida con la API nacional y guarda los perfiles. En Bonita queda lista `Seleccionar ofertas validadas`. |
| 5   | Municipio    | _Ejecución_ de la emergencia → seleccionar el aporte (2) → **Adjudicar**                               | Adjudicación **CONFIRMADA** y compromiso nacional **ACTIVO** (disponibilidad −2). La ONG recibe la notificación y queda lista `Marcar como finalizada la tarea`.          |
| 6   | ONG          | _Ejecución_ (o la notificación) → **Finalizar** su participación                                       | Participación **LIBERADA** y compromiso nacional **LIBERADO**; la disponibilidad se restituye.                                                                            |
| 7   | Coordinador  | _Ejecución_ → **Solicitar cierre**                                                                     | Seguimiento muestra **Cierre confirmado** y la emergencia **RESUELTA**. El proyecto nacional queda **TERMINADO** y Bonita archiva el caso como _completed_, sin tareas fallidas. |

### Caso B — Cobertura parcial → CONTINUAR_PARCIAL

1. Crear otra emergencia MEDIA con un lote de **Personal paramédico** de **5** personas, riesgo MEDIA, y publicar.
2. La ONG ofrece **2**.
3. Después del timer:
   - Esperado: el lote **no** queda cubierto y en Bonita aparece `Evalua situacion` (Coordinador), no la selección.
   - La pantalla muestra "Hay necesidades pendientes de cobertura" con el faltante.
4. El coordinador decide **Continuar con cobertura parcial**, con un motivo de 3 caracteres o más.
   - Esperado: aparece `Seleccionar ofertas validadas`.
5. Seguir los pasos 5 a 7 del Caso A con los 2 ofrecidos.

### Caso C — Reabrir la convocatoria

1. Igual que el Caso B hasta `Evalua situacion`, y elegir **Reabrir convocatoria**.
   - Esperado: ronda nueva (variable de caso `intentoConvocatoria` = 2) y otro timer.
2. La ONG presenta una oferta que **cubra** (5 personas; Ayuda Sin Fronteras tiene 12).
   - Esperado tras el timer: la ronda 2 se valida y aparece `Seleccionar ofertas validadas`. No se reutilizan resultados de la ronda anterior.
3. Opcional: completar como en el Caso A.

### Caso D — Reformular los lotes

1. Igual que el Caso B hasta `Evalua situacion`, y elegir **Reformular lotes**.
   - Esperado: el caso vuelve a `Generar lotes de necesidades`.
2. El coordinador ajusta o crea lotes (por ejemplo, Personal paramédico de 2) y publica.
   - Esperado: nueva convocatoria y nuevo timer. Continuar como en el Caso A.

### Caso E — Validación por niveles (sin rechazo binario)

Elegir una de las variantes y publicar el lote:

| Variante | Lote                      | Oferta                        | Motivos esperados                                                                   |
| -------- | ------------------------- | ----------------------------- | ----------------------------------------------------------------------------------- |
| E1       | Personal paramédico       | `redmedica@` (ONG PENDIENTE)  | `ONG_NO_HABILITADA`                                                                 |
| E2       | **Agua potable** (litros) | `ong@` con su recurso de agua | "No hay acreditación vigente" y "La acreditación no inició" (`ACREDITACION_FUTURA`) |

Resultado esperado en las dos:

- El coordinador ve en _Ejecución_ el diagnóstico `SIN_HABILITACION` con sus motivos.
- El lote queda sin cubrir → `Evalua situacion`.
- Se puede continuar con REABRIR o REFORMULAR, como en los casos C y D.

### Caso F — Disponibilidad insuficiente (opcional)

- Lote de Personal paramédico de **20**. Ayuda Sin Fronteras ofrece **20** y tiene 12.
- Esperado: el aporte trae `DISPONIBILIDAD_INSUFICIENTE`, con la cantidad limitada al stock. El lote queda sin cubrir → `Evalua situacion`.

## Problemas frecuentes

| Síntoma                                                                                             | Causa / solución                                                                                                                                        |
| --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `bonita-deploy`: "Se esperaba exactamente un archivo .bar"                                          | Hay más de un `.bar` en `docs/`.                                                                                                                        |
| `bonita-deploy`: "El BAR … contiene RescueSync:1.5, pero el backend espera …"                       | `BONITA_PROCESS_VERSION` debe ser `1.5`.                                                                                                                |
| `bonita-deploy` falla por variable requerida                                                        | Faltan `BONITA_NATIONAL_API_LOGIN` o `BONITA_NATIONAL_API_PASSWORD`.                                                                                    |
| Tarea _failed_ en `Validar Oferta` o `Registrar compromiso nacional`, con 401 en los logs de Bonita | La contraseña del `.env` no coincide con la del bootstrap nacional.                                                                                     |
| 403/404 "sistema de origen" o "La ronda no conserva el sistema de origen nacional"                  | `NACIONAL_SISTEMA_ORIGEN` vacío o distinto del `--sistema-origen`. Recrear la emergencia después de corregirlo.                                         |
| Tarea _failed_ en `Registrar compromiso nacional` con 409                                           | Ese `idEmergencia` ya tiene un proyecto nacional de otro caso (pruebas previas sin reiniciar la base nacional). Reiniciar ambos entornos (pasos 1 y 2). |
| La oferta queda `SIN_HABILITACION` aunque la ONG sea HABILITADA                                     | La capacidad del lote no está acreditada o vigente para esa ONG (ver datos demo). Usar Personal paramédico.                                             |
| La emergencia no tiene caso Bonita                                                                  | Se creó antes de que terminara el deploy. Usar el botón _Vincular con Bonita_ de la bandeja de emergencias.                                             |
| Se reemplazó el `.bar` y Bonita sigue con el anterior                                               | La definición ya tenía casos. Ejecutar `docker compose down -v` y volver a levantar.                                                                    |
| Ver qué conector falló                                                                              | `docker logs rescuesync-bonita-1 --since 10m 2>&1 \| grep -E 'WARN\|ERROR'`                                                                             |

## Repetir la prueba

- **Entre casos:** no hace falta reiniciar; cada emergencia es un caso nuevo.
- **Para volver a cero:**
  1. `docker compose down -v` en los dos repositorios.
  2. Repetir los pasos 1 y 2 completos, incluido el bootstrap de integración.
