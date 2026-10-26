# Gantt consolidado de RescueSync

Desde la raíz del repositorio:

```bash
python docs/generar_gantt.py
```

El script descubre todos los archivos `Grooming Etapa N.xlsx` de
[`groomings/`](./groomings/) y genera estos archivos en `docs/generated/`,
excluidos de Git:

- `gantt-todas-las-etapas.html`: gráfico autocontenido, con detalles al pasar
  el cursor sobre las barras.
- `gantt-todas-las-etapas.png`: imagen del cronograma completo.
- `gantt-todas-las-etapas.pdf`: documento del cronograma completo.

Lee los títulos, épicas, estimaciones, horas efectivas y semanas sugeridas de
la primera hoja de cada archivo. No requiere GitHub CLI ni acceso a red.
Los IDs incluyen la etapa, por ejemplo `E1-T1` y `E2-T1`, porque ambos groomings
usan la numeración T1. El formato de cada celda determina la conversión a horas:
las horas decimales de E1 se conservan y las duraciones Excel de E2–E4 se
multiplican por 24. Se rechazan horas ausentes, no positivas o no finitas,
actividades duplicadas y semanas fuera del período de su etapa.

## Semanas y ritmo de trabajo

Los hitos provienen de las páginas 4–5 de
[`Trabajo integrador 2026.pdf`](<./Trabajo integrador 2026.pdf>). Cada semana
abarca de lunes a domingo y la grilla siempre muestra sus siete días, con
los nombres `Lun`, `Mar`, `Mié`, `Jue`, `Vie`, `Sáb` y `Dom`.
`--weekend-days` solo determina en qué días se puede planificar trabajo;
no cambia las columnas visibles. Por defecto se trabaja de lunes a viernes.
Los sábados y domingos solo son elegibles cuando se habilitan explícitamente.

| Etapa | Semanas de trabajo reconstruidas | Semana de entrega según consigna |
| --- | --- | --- |
| 1 | 24/8–30/8, 31/8–6/9, 7/9–13/9 | 10/9 |
| 2 | 14/9–20/9, 21/9–27/9, 28/9–4/10 | 1/10 |
| 3 | 5/10–11/10, 12/10–18/10, 19/10–25/10 | 22/10 |
| 4 | 26/10–1/11, 2/11–8/11 | 5/11 |

Todas las fechas corresponden a 2026. La consigna no fija el inicio de E1:
se infiere el 24/8 a partir de sus tres semanas sugeridas. Las etapas
siguientes comienzan el lunes posterior a la semana de la entrega precedente.
La fecha de cada hito identifica la semana de entrega, sin imponer un
vencimiento ese día exacto. El Gantt termina el domingo 8/11, al completar
la semana de la Entrega 4. La Etapa 5 queda fuera del gráfico y del resumen.

Se conserva la semana sugerida de cada actividad y se ordenan las tareas por
su ID dentro de ella. La distribución diaria es aleatoria, respetando el mínimo
y máximo configurados, incluidos ambos extremos, dentro de la franja de
08:00 a 23:00, con hasta quince horas totales por jornada. Por defecto se usan
de una a tres tareas activas por día con trabajo. Una actividad que excede el
tiempo disponible continúa en la siguiente jornada elegible y cuenta como
activa en ambas. Las jornadas no utilizadas pueden quedar libres; el mínimo
se aplica a los días con actividad. No se fuerza a completar la franja ni
se infieren dependencias que el Excel no registra.

En el modo extendido, cada columna diaria mide 192 px y representa las 24 horas, de 00:00 a 24:00,
con divisiones por hora, marcas cada cuatro horas y sombreado fuera de la
franja de trabajo. Cada tramo muestra su hora de inicio y fin en formato
`HH:MM`; el ancho de la barra conserva las horas efectivas del grooming.
Las constantes `DAY_WIDTH`, `WORK_START_HOUR` y `WORK_END_HOUR` permiten ajustar
la escala y la franja. El PNG se exporta a escala CSS para conservar esta
anchura sin duplicar el tamaño de una imagen que abarca once semanas.

`--no-extended-hours` activa el modo simplificado: recupera las columnas de
32 px, sin escala horaria ni etiquetas junto a las barras. Cada día comprime
la franja de trabajo completa y el horario sigue disponible al pasar el cursor
sobre una barra. `--extended-hours` vuelve al modo extendido, que se usa por
defecto. El switch cambia la presentación; las tareas, días, horarios y totales
son idénticos en ambos modos. Su valor predeterminado se configura con
`DEFAULT_EXTENDED_HOURS`, y `SIMPLIFIED_DAY_WIDTH` permite ajustar el ancho compacto.

Con la aleatoriedad habilitada, las tareas de cada día se desplazan juntas
dentro de la franja en intervalos de quince minutos, conservando el orden y
sin superponerse. Sin aleatoriedad, la primera tarea de cada día empieza a las 08:00.

E4 tiene 21 tareas en dos semanas: 11 están sugeridas para la segunda semana.
A un máximo de tres tareas diarias caben de lunes a viernes. Para usar un máximo
de dos, se puede habilitar el sábado con `--max-tasks-per-day 2 --weekend-days saturday`.
No se agregan días automáticamente. Si las horas o los límites diarios impiden
programar una semana con los días permitidos, se informa un error sin trasladar
tareas a otra semana ni incumplir los límites. También se rechazan mínimos que
no se puedan alcanzar con las tareas disponibles.

Las fechas diarias son una **reconstrucción**, no registros históricos
verificados. Los desvíos mostrados son de esfuerzo: horas efectivas menos
estimadas, por tarea y por etapa. No se calculan atrasos o adelantos de fechas
sin registros reales.

## Requisitos y opciones

La lectura de Excel y la generación de HTML usan solo la biblioteca estándar
de Python. Para PNG y PDF se usa el Playwright del frontend con Chromium:

```bash
cd frontend
npm ci
npx playwright install chromium
```

Para generar solo HTML, sin Node ni navegador:

```bash
python docs/generar_gantt.py --html-only
```

Se pueden cambiar las rutas y el título:

```bash
python docs/generar_gantt.py --groomings-dir docs/groomings --output-dir /tmp/gantt --title "RescueSync — Entrega 4"
```

Los parámetros de distribución tienen valores predeterminados en las constantes
`DEFAULT_*` al comienzo del script y se pueden sobrescribir desde la terminal:

| Parámetro | Valor predeterminado | Efecto |
| --- | --- | --- |
| `--min-tasks-per-day` | `1` | Mínimo de tareas activas en un día con trabajo. |
| `--max-tasks-per-day` | `3` | Máximo de tareas activas en una jornada. |
| `--randomize` / `--no-randomize` | Aleatoriedad habilitada | Activa o desactiva el sorteo de la distribución. |
| `--seed` | `2026` | Misma semilla, entradas y opciones producen los mismos días y horarios; otra semilla permite otra distribución. |
| `--weekend-days` | `none` | `none`: lunes a viernes; `saturday`: lunes a sábado; `saturday-sunday`: lunes a domingo. |
| `--extended-hours` / `--no-extended-hours` | Extendido habilitado | Alterna columnas de 192 px con escala de 24 h y columnas simplificadas de 32 px. |

Ejemplos:

```bash
python docs/generar_gantt.py --min-tasks-per-day 1 --max-tasks-per-day 3 --seed 42 --weekend-days none
python docs/generar_gantt.py --max-tasks-per-day 2 --weekend-days saturday
python docs/generar_gantt.py --weekend-days saturday-sunday --seed 17
python docs/generar_gantt.py --no-randomize
python docs/generar_gantt.py --no-extended-hours
python docs/generar_gantt.py --extended-hours
```

Siempre debe cumplirse `1 <= mínimo <= máximo`. Desactivar la aleatoriedad
distribuye las actividades de forma estable e ignora la semilla. En todos los
modos se validan los límites y la capacidad semanal. Los fines de semana se
destacan en la grilla incluso cuando no se habilita trabajo en ellos.

Las opciones anteriores de GitHub Projects (`--owner`, `--project-number`,
`--input-json`) y del Excel único (`--actual-hours-xlsx`) se reemplazan por
`--groomings-dir`.

Pruebas y verificaciones desde la raíz:

```bash
python -m unittest discover --start-directory docs/tests --verbose
ruff check docs/generar_gantt.py docs/tests
ruff format --check docs/generar_gantt.py docs/tests
```
