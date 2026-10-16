# Seed masivo para pruebas de volumen

`app.scripts.seed_masivo` es independiente del seed demo. Genera datos sintéticos
con [Faker](https://faker.readthedocs.io/) (`es_AR`), cantidades enteras y fechas
UTC distribuidas en los últimos seis meses. Faker es una dependencia de desarrollo;
reconstruir la imagen después de incorporar estos cambios.

Para cada demostración, elegir **demo** (`app.scripts.seed`) para un escenario
pequeño o **masivo** (`app.scripts.seed_masivo`) para alta carga, y usar la misma
modalidad en RescueSyncAPI. Cada modalidad se puede cargar por sí sola sobre una
base preparada para ese escenario; el masivo no necesita ejecutar antes el demo.
Ambas modalidades usan el mismo administrador inicial.

Desde la raíz de RescueSync, con PostgreSQL levantado, migraciones al día y
`NACIONAL_ENCRYPTION_KEY` configurada en `.env` como indica el inicio rápido:

```bash
docker compose build backend
docker compose run --rm backend python -m app.scripts.seed_masivo --dry-run
docker compose run --rm backend python -m app.scripts.seed_masivo
```

Sólo admite `APP_ENV=development` o `test`. No necesita Bonita ni una API nacional
disponible durante la carga. Escribe en la base configurada para el backend.

## Volumen y configuración

Los valores predeterminados producen:

| Entidad                                           |           Cantidad |
| ------------------------------------------------- | -----------------: |
| Municipios / centros / ONGs                       |   100 / 10 / 1.000 |
| Usuarios (administrador inicial y auditor incluidos) |             1.112 |
| Emergencias                                       |              5.000 |
| Lotes                                             |              9.000 |
| Convocatorias abiertas / cerradas                 |      1.000 / 1.000 |
| Ofertas y versiones                               |  6.000 de cada una |
| Ítems y aportes nacionales                        | 18.000 de cada uno |
| Notificaciones                                    |              5.000 |

También se crean los participantes de cada oferta y 1.000 accesos nacionales
cifrados. Las emergencias alternan `REGISTRADA`, `EN_COORDINACION`, `PUBLICADA`,
`EN_EVALUACION` y `CANCELADA`; sólo los estados correspondientes tienen lotes,
convocatorias y ofertas. Todas las ofertas presentadas tienen un líder confirmado
y desglose completo por recurso nacional.

```bash
docker compose run --rm backend python -m app.scripts.seed_masivo \
  --seed 2026 --municipios 100 --centros 10 --ongs 1000 \
  --emergencias 10000 --lotes-por-emergencia 4 \
  --ofertas-por-convocatoria 5 --batch-size 100
```

`--batch-size` controla cuántas emergencias se procesan juntas (1–1.000); no hace
commits parciales. Reducirlo si se aumentan mucho los lotes u ofertas por escenario.
Todos los conteos deben ser positivos y las ofertas por convocatoria no pueden
superar la cantidad de ONGs. `--seed` admite 0–2.147.483.647; `--help` enumera las
opciones. `--dry-run` valida y muestra la configuración sin conectar a PostgreSQL.

## Repetición e integración nacional

Los conteos son objetivos totales para un mismo `--seed`. Repetir el comando
omite las emergencias existentes y agrega las que falten; aumentar
`--emergencias`, `--ongs`, `--municipios` o `--centros` permite ampliar el conjunto.
No sobrescribe contraseñas, usuarios inactivos, secretos técnicos ni escenarios
editados. Cambiar la cantidad de lotes/ofertas sólo afecta las emergencias nuevas;
usar otro `--seed` para generar un escenario completo con otras proporciones.
Reducir un objetivo conserva las filas existentes.

La unicidad usa índices y UUIDs deterministas, sin depender de `Faker.unique`.
La transacción toma un advisory lock de PostgreSQL por seed para serializar dos
cargas simultáneas. Ante un error, se revierte toda la ejecución y el comando
termina con código 1. El progreso previo al commit no representa datos confirmados;
el resumen final informa filas creadas y emergencias omitidas.
Los triggers de desglose se mantienen activos y se comprueban inmediatamente:
cada versión se presenta después de insertar todos sus participantes y aportes.
Esto evita acumular validaciones repetidas de la misma versión al hacer commit.

Para consultar Mis recursos, ejecutar primero en RescueSyncAPI:

```bash
docker compose build api
docker compose run --rm api python -m app.scripts.seed_masivo \
  --seed 2026 --ongs 1000 --recursos-por-ong 20
```

Usar el mismo `--seed` en ambos proyectos y al menos tantas ONGs nacionales como
locales. El seed nacional exige al menos cuatro recursos por ONG: los primeros
cuatro representan agua, raciones, paramédicos y ambulancias, en ese orden. Los
UUIDs coinciden con las referencias de las ofertas locales y las capacidades base
instaladas por migraciones. Las cargas no leen la base del otro sistema.

Los registros son escenarios sintéticos para medir listados, filtros, consultas
y renderizado. No crean casos BPM, compromisos de stock ni una adjudicación real.
Las emergencias quedan sin vínculo a Bonita; probar el flujo operativo completo
requiere crear emergencias por la aplicación. Las fechas existentes, incluidas
las ventanas de las convocatorias, se conservan al repetir el comando.

## Usuarios para explorar

El administrador es el mismo del seed demo y del arranque normal:
`admin@rescuesync.org` / `administrador123` por defecto. Se obtiene mediante el
bootstrap y respeta `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD`. Debe cambiar la
contraseña temporal en el primer ingreso. Si ya existe un administrador activo,
se conserva su cuenta y su contraseña; repetir o cambiar `--seed` no crea otro
administrador ni restablece credenciales.

Las demás cuentas locales del seed predeterminado usan `CargaMasiva2026!`:

| Rol           | Correo                                          |
| ------------- | ----------------------------------------------- |
| Auditor       | `masivo-2026-auditor@example.test`              |
| Municipio     | `masivo-2026-municipio-1@example.test`          |
| Coordinador   | `masivo-2026-centro_coordinador-1@example.test` |
| ONG           | `masivo-2026-ong-1@example.test`                |

El último número identifica la organización, desde 1. Son credenciales públicas
de fixtures de desarrollo; sus hashes Argon2 se calculan una vez por carga para
evitar miles de operaciones costosas. Para concentrar más filas en las vistas
de un municipio, centro u ONG, disminuir su cantidad al crear un seed nuevo.

## Acceso al catálogo nacional

El seed nacional masivo crea el mismo administrador nacional que el demo. En
`RescueSync/.env`, mantener las credenciales de desarrollo de `.env.example`:

```dotenv
NACIONAL_CATALOGO_LOGIN=admin.nacional.demo@rescuesync.org
NACIONAL_CATALOGO_PASSWORD=admin-nacional-demo123
```

Estas credenciales son independientes de la sesión del administrador local y no
dependen de `--seed`. Con sólo el masivo nacional cargado ya se puede consultar y
crear capacidades desde RescueSync. Si se modificaron estas variables para usar
el administrador de una versión anterior del masivo, volver a los valores de
arriba y aplicar el entorno con
`docker compose up -d --no-deps --force-recreate backend`.

La carga es aditiva y no incluye borrado. Para descartar datos masivos sin perder
otros datos, usar una base o volumen dedicado antes de ejecutar el comando.

Las pruebas de idempotencia, ampliación, credenciales, rollback y restricciones
se ejecutan contra PostgreSQL con
`docker compose run --rm -e APP_ENV=test backend pytest tests/test_seed_masivo.py`.
