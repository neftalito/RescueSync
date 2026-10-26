"""Genera el Gantt de todas las etapas desde los groomings locales en XLSX."""

from __future__ import annotations

import argparse
import html
import json
import math
import random
import re
import subprocess
import sys
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import StrEnum
from functools import cache
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

DEFAULT_TITLE = "RescueSync — Seguimiento de todas las etapas"
DEFAULT_MIN_TASKS_PER_DAY = 1
DEFAULT_MAX_TASKS_PER_DAY = 3
DEFAULT_RANDOMIZE = True
DEFAULT_SEED = 2026
DEFAULT_EXTENDED_HOURS = True
DAY_HOURS = 24
DAY_WIDTH = 192
SIMPLIFIED_DAY_WIDTH = 32
LABEL_WIDTH = 660
ROW_HEIGHT = 62
WORK_START_HOUR = 8
WORK_END_HOUR = 23
WORKDAY_HOURS = WORK_END_HOUR - WORK_START_HOUR
SPREADSHEET_NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NAMESPACE = {"x": SPREADSHEET_NAMESPACE}


class WeekendDays(StrEnum):
    """Determina qué días del fin de semana son elegibles para trabajar."""

    NONE = "none"
    SATURDAY = "saturday"
    SATURDAY_SUNDAY = "saturday-sunday"

    @property
    def days_per_week(self) -> int:
        return {self.NONE: 5, self.SATURDAY: 6, self.SATURDAY_SUNDAY: 7}[self]

    @property
    def description(self) -> str:
        return {
            self.NONE: "lunes a viernes",
            self.SATURDAY: "lunes a sábado",
            self.SATURDAY_SUNDAY: "lunes a domingo",
        }[self]


DEFAULT_WEEKEND_DAYS = WeekendDays.NONE


@dataclass(frozen=True, slots=True)
class ScheduleOptions:
    """Configura los límites diarios y una distribución aleatoria reproducible."""

    min_tasks_per_day: int = DEFAULT_MIN_TASKS_PER_DAY
    max_tasks_per_day: int = DEFAULT_MAX_TASKS_PER_DAY
    randomize: bool = DEFAULT_RANDOMIZE
    seed: int = DEFAULT_SEED
    weekend_days: WeekendDays = DEFAULT_WEEKEND_DAYS
    extended_hours: bool = DEFAULT_EXTENDED_HOURS

    def __post_init__(self) -> None:
        if (
            self.min_tasks_per_day < 1
            or self.max_tasks_per_day < self.min_tasks_per_day
        ):
            raise ValueError("Los límites diarios deben cumplir 1 <= mínimo <= máximo.")


DEFAULT_SCHEDULE_OPTIONS = ScheduleOptions()


@dataclass(frozen=True, slots=True)
class StageWindow:
    """Delimita las semanas de trabajo y el hito indicado en la consigna."""

    number: int
    start: date
    delivery: date

    @property
    def weeks(self) -> int:
        return (self.delivery - self.start).days // 7 + 1

    @property
    def end(self) -> date:
        """Devuelve el domingo que completa visualmente la semana de entrega."""

        return self.delivery + timedelta(days=6 - self.delivery.weekday())


# Hitos: Trabajo integrador 2026.pdf, páginas 4–5. La primera etapa se
# reconstruye con las tres semanas sugeridas en su grooming. Las siguientes
# comienzan el lunes posterior a la semana de la entrega precedente.
STAGES = (
    StageWindow(1, date(2026, 8, 24), date(2026, 9, 10)),
    StageWindow(2, date(2026, 9, 14), date(2026, 10, 1)),
    StageWindow(3, date(2026, 10, 5), date(2026, 10, 22)),
    StageWindow(4, date(2026, 10, 26), date(2026, 11, 5)),
)


@dataclass(frozen=True, slots=True)
class ExcelCell:
    """Conserva el formato necesario para distinguir horas de duraciones Excel."""

    value: str
    style: int


@dataclass(frozen=True, slots=True)
class GroomingTask:
    """Identifica una actividad por etapa y conserva los datos de su grooming."""

    stage: int
    number: int
    epic: str
    title: str
    estimate: float
    actual_hours: float
    suggested_week: int
    source: str

    @property
    def key(self) -> str:
        return f"E{self.stage}-T{self.number}"


@dataclass(frozen=True, slots=True)
class WorkSegment:
    """Representa un tramo diario con inicio en horas del reloj de 00:00 a 24:00."""

    day: date
    start_hour: float
    hours: float


@dataclass(frozen=True, slots=True)
class ScheduledTask:
    """Asocia la actividad con sus tramos diarios de ejecución reconstruida."""

    item: GroomingTask
    segments: tuple[WorkSegment, ...]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Interpreta las rutas de entrada y salida sin requerir acceso a GitHub."""

    repository_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Genera el Gantt de todos los XLSX de docs/groomings en HTML, PNG y PDF."
    )
    parser.add_argument("--title", default=DEFAULT_TITLE, help="Título del Gantt.")
    parser.add_argument(
        "--groomings-dir",
        type=Path,
        default=repository_root / "docs" / "groomings",
        help="Carpeta con los archivos Grooming Etapa N.xlsx.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repository_root / "docs" / "generated",
        help="Directorio para los archivos generados.",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Genera solo el HTML; no requiere Node ni Playwright.",
    )
    parser.add_argument(
        "--min-tasks-per-day",
        type=int,
        default=DEFAULT_MIN_TASKS_PER_DAY,
        help="Mínimo de tareas activas en una jornada con trabajo (por defecto: 1).",
    )
    parser.add_argument(
        "--max-tasks-per-day",
        type=int,
        default=DEFAULT_MAX_TASKS_PER_DAY,
        help="Máximo de tareas activas por jornada (por defecto: 3).",
    )
    parser.add_argument(
        "--randomize",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_RANDOMIZE,
        help="Distribuye aleatoriamente las tareas dentro de sus límites y semanas.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Semilla de la distribución aleatoria (por defecto: 2026).",
    )
    parser.add_argument(
        "--weekend-days",
        type=WeekendDays,
        choices=list(WeekendDays),
        default=DEFAULT_WEEKEND_DAYS,
        help="Días adicionales elegibles: ninguno, sábado o sábado y domingo (por defecto: none).",
    )
    parser.add_argument(
        "--extended-hours",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_EXTENDED_HOURS,
        help="Usa columnas de 24 h; --no-extended-hours restaura la vista simplificada de 32 px.",
    )
    return parser.parse_args(argv)


def _shared_strings(archive: ZipFile) -> list[str]:
    """Lee los textos compartidos, opcionales en los archivos XLSX."""

    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(node.itertext()) for node in root.findall("x:si", NAMESPACE)]


def _cell_value(cell: ElementTree.Element, shared_strings: Sequence[str]) -> str:
    """Obtiene el texto o valor calculado almacenado en una celda."""

    raw_value = cell.findtext("x:v", "", NAMESPACE)
    if cell.attrib.get("t") == "s" and raw_value:
        try:
            index = int(raw_value)
            if index < 0:
                raise ValueError("Índice negativo")
            return shared_strings[index]
        except (IndexError, ValueError) as error:
            raise ValueError(
                "El XLSX contiene un texto compartido inválido."
            ) from error
    inline = cell.find("x:is", NAMESPACE)
    return "".join(inline.itertext()) if inline is not None else raw_value


def _duration_styles(archive: ZipFile) -> set[int]:
    """Reconoce formatos de tiempo para convertir días Excel en horas."""

    root = ElementTree.fromstring(archive.read("xl/styles.xml"))
    custom_formats = {
        int(node.attrib["numFmtId"]): node.attrib["formatCode"]
        for node in root.findall("x:numFmts/x:numFmt", NAMESPACE)
    }
    styles: set[int] = set()
    for index, node in enumerate(root.findall("x:cellXfs/x:xf", NAMESPACE)):
        format_id = int(node.attrib.get("numFmtId", "0"))
        code = re.sub(r'"[^"]*"|\\.', "", custom_formats.get(format_id, "")).lower()
        if format_id in {18, 19, 20, 21, 22, 45, 46, 47} or re.search(
            r"\[h+\]|h+:?m", code
        ):
            styles.add(index)
    return styles


def _normalize_header(text: str) -> str:
    """Tolera diferencias de mayúsculas y acentuación en los encabezados."""

    return " ".join(
        "".join(
            character
            for character in unicodedata.normalize("NFD", text.casefold())
            if not unicodedata.combining(character)
        ).split()
    )


def _hours(cell: ExcelCell, duration_styles: set[int], context: str) -> float:
    """Valida y homogeneiza una duración a horas con dos decimales."""

    try:
        value = float(cell.value)
    except ValueError as error:
        raise ValueError(f"{context} debe contener horas positivas válidas.") from error
    hours = round(value * (24 if cell.style in duration_styles else 1), 2)
    if not math.isfinite(hours) or hours <= 0:
        raise ValueError(f"{context} debe contener horas positivas finitas.")
    return hours


def read_grooming(path: Path, stage: int) -> list[GroomingTask]:
    """Lee tareas y semanas de la primera hoja sin instalar librerías de Excel."""

    try:
        with ZipFile(path) as archive:
            shared_strings = _shared_strings(archive)
            duration_styles = _duration_styles(archive)
            sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except (OSError, BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise RuntimeError(f"No se pudo leer el XLSX {path}: {error}") from error

    required = (
        "id",
        "epica",
        "tarea",
        "estimacion (hs)",
        "horas efectivas",
        "semana sugerida",
    )
    columns: dict[str, str] = {}
    tasks: list[GroomingTask] = []
    seen: set[int] = set()
    for row in sheet.findall("x:sheetData/x:row", NAMESPACE):
        values = {
            "".join(c for c in cell.attrib.get("r", "") if c.isalpha()): ExcelCell(
                _cell_value(cell, shared_strings).strip(),
                int(cell.attrib.get("s", "0")),
            )
            for cell in row.findall("x:c", NAMESPACE)
        }
        if not columns:
            headers = {
                _normalize_header(cell.value): column for column, cell in values.items()
            }
            if all(header in headers for header in required):
                columns = {header: headers[header] for header in required}
            continue
        task_id = values.get(columns["id"], ExcelCell("", 0)).value
        match = re.fullmatch(r"T([1-9][0-9]*)", task_id)
        if match is None:
            continue
        number = int(match[1])
        key = f"E{stage}-T{number}"
        if number in seen:
            raise ValueError(f"{key} está repetida en {path.name}.")
        seen.add(number)
        fields = {
            header: values.get(column, ExcelCell("", 0))
            for header, column in columns.items()
        }
        for header in ("epica", "tarea"):
            if not fields[header].value:
                raise ValueError(f"{key}: falta {header} en {path.name}.")
        try:
            raw_week = float(fields["semana sugerida"].value)
            if not math.isfinite(raw_week) or not raw_week.is_integer():
                raise ValueError("La semana debe ser un entero")
            week = int(raw_week)
        except ValueError as error:
            raise ValueError(
                f"{key}: semana sugerida inválida en {path.name}."
            ) from error
        tasks.append(
            GroomingTask(
                stage,
                number,
                fields["epica"].value,
                fields["tarea"].value,
                _hours(
                    fields["estimacion (hs)"], duration_styles, f"{key}: estimación"
                ),
                _hours(
                    fields["horas efectivas"],
                    duration_styles,
                    f"{key}: horas efectivas",
                ),
                week,
                path.name,
            )
        )
    if not columns:
        raise ValueError(
            f"{path.name} no contiene los encabezados requeridos: {', '.join(required)}."
        )
    if not tasks:
        raise ValueError(f"{path.name} no contiene tareas con horas efectivas.")
    return tasks


def read_groomings(directory: Path) -> list[GroomingTask]:
    """Descubre todos los groomings y conserva los IDs dentro de cada etapa."""

    paths = sorted(
        path for path in directory.glob("*.xlsx") if not path.name.startswith("~$")
    )
    if not paths:
        raise ValueError(f"No se encontraron groomings XLSX en {directory}.")
    stages = {stage.number for stage in STAGES}
    tasks: list[GroomingTask] = []
    for path in paths:
        match = re.fullmatch(
            r"Grooming Etapa ([1-9][0-9]*)\.xlsx", path.name, re.IGNORECASE
        )
        if match is None:
            raise ValueError(
                f"El nombre {path.name} debe respetar Grooming Etapa N.xlsx."
            )
        stage = int(match[1])
        if stage not in stages:
            raise ValueError(
                f"La etapa {stage} no tiene semanas definidas en la consigna."
            )
        tasks.extend(read_grooming(path, stage))
    return sorted(tasks, key=lambda task: (task.stage, task.number))


def _split_hours(
    hours: int,
    day_index: int,
    start: int,
    days: tuple[date, ...],
) -> tuple[WorkSegment, ...] | None:
    """Divide centésimas de hora entre jornadas dentro de la franja 08:00–23:00."""

    segments: list[WorkSegment] = []
    while hours:
        if day_index >= len(days):
            return None
        used = min(hours, WORK_END_HOUR * 100 - start)
        segments.append(WorkSegment(days[day_index], start / 100, used / 100))
        hours -= used
        day_index += 1
        start = WORK_START_HOUR * 100
    return tuple(segments)


def _schedule_week(
    tasks: Sequence[GroomingTask],
    days: tuple[date, ...],
    options: ScheduleOptions,
    rng: random.Random,
) -> tuple[tuple[WorkSegment, ...], ...] | None:
    """Busca una distribución secuencial dentro de los límites diarios elegidos."""

    durations = tuple(round(task.actual_hours * 100) for task in tasks)
    maximum = options.max_tasks_per_day
    if (
        len(tasks) > len(days) * maximum
        or sum(durations) > len(days) * WORKDAY_HOURS * 100
    ):
        return None
    priorities = (
        tuple(rng.sample(range(len(days)), len(days)) for _task in tasks)
        if options.randomize
        else ()
    )

    @cache
    def place(
        index: int,
        cursor: int,
        start: int,
        counts: tuple[int, ...],
    ) -> tuple[tuple[WorkSegment, ...], ...] | None:
        """Prueba días elegibles y retrocede cuando una opción impide terminar."""

        if index == len(tasks):
            return (
                ()
                if all(
                    count == 0 or count >= options.min_tasks_per_day for count in counts
                )
                else None
            )
        if len(tasks) - index > sum(maximum - count for count in counts):
            return None
        preferred = index * (len(days) - 1) // max(1, len(tasks) - 1)
        candidates = sorted(
            range(cursor, len(days)),
            key=lambda day: (
                priorities[index].index(day)
                if options.randomize
                else abs(day - preferred)
            ),
        )
        for day_index in candidates:
            segments = _split_hours(
                durations[index],
                day_index,
                start if day_index == cursor else WORK_START_HOUR * 100,
                days,
            )
            if segments is None:
                continue
            next_counts = list(counts)
            for segment in segments:
                next_counts[days.index(segment.day)] += 1
            if max(next_counts) > maximum:
                continue
            last = segments[-1]
            next_cursor = days.index(last.day)
            next_start = round((last.start_hour + last.hours) * 100)
            if next_start == WORK_END_HOUR * 100:
                next_cursor += 1
                next_start = WORK_START_HOUR * 100
            remaining = place(index + 1, next_cursor, next_start, tuple(next_counts))
            if remaining is not None:
                return (segments, *remaining)
        return None

    placement = place(0, 0, WORK_START_HOUR * 100, (0,) * len(days))
    if placement is None or not options.randomize:
        return placement
    day_ends: dict[date, float] = {}
    for segments in placement:
        for segment in segments:
            day_ends[segment.day] = max(
                day_ends.get(segment.day, WORK_START_HOUR),
                segment.start_hour + segment.hours,
            )
    # Un desplazamiento común conserva el orden y evita solapar tareas del día.
    shifts = {
        day: rng.randrange(round((WORK_END_HOUR - end) * 100) // 25 + 1) / 4
        for day, end in day_ends.items()
    }
    return tuple(
        tuple(
            replace(segment, start_hour=segment.start_hour + shifts[segment.day])
            for segment in segments
        )
        for segments in placement
    )


def build_schedule(
    items: Sequence[GroomingTask],
    options: ScheduleOptions = DEFAULT_SCHEDULE_OPTIONS,
) -> tuple[list[ScheduledTask], list[date]]:
    """Planifica en días habilitados y devuelve semanas completas para la grilla."""

    windows = {stage.number: stage for stage in STAGES}
    seen: set[str] = set()
    for item in items:
        if item.key in seen:
            raise ValueError(f"{item.key} está repetida en los groomings.")
        seen.add(item.key)
        window = windows.get(item.stage)
        if window is None or not 1 <= item.suggested_week <= window.weeks:
            raise ValueError(f"{item.key}: semana sugerida fuera de su etapa.")
        if not math.isfinite(item.actual_hours) or item.actual_hours <= 0:
            raise ValueError(f"{item.key}: horas efectivas inválidas.")
    if not items:
        raise ValueError("No hay tareas para generar el cronograma.")

    scheduled: list[ScheduledTask] = []
    rng = random.Random(options.seed)
    for stage in STAGES:
        for week in range(1, stage.weeks + 1):
            tasks = sorted(
                (
                    task
                    for task in items
                    if task.stage == stage.number and task.suggested_week == week
                ),
                key=lambda task: task.number,
            )
            if not tasks:
                continue
            monday = stage.start + timedelta(weeks=week - 1)
            days = tuple(
                monday + timedelta(days=index)
                for index in range(options.weekend_days.days_per_week)
            )
            placement = _schedule_week(tasks, days, options, rng)
            if placement is None:
                raise ValueError(
                    f"Etapa {stage.number}, semana {week}: las tareas no caben "
                    f"con {options.min_tasks_per_day}–{options.max_tasks_per_day} tareas entre "
                    f"{WORK_START_HOUR:02d}:00 y {WORK_END_HOUR:02d}:00 "
                    f"y días elegibles de {options.weekend_days.description}. "
                    "Revisá los límites diarios o --weekend-days."
                )
            scheduled.extend(
                ScheduledTask(task, segments)
                for task, segments in zip(tasks, placement, strict=True)
            )
    horizon = (STAGES[-1].end - STAGES[0].start).days + 1
    days = [STAGES[0].start + timedelta(days=offset) for offset in range(horizon)]
    return scheduled, days


def format_estimate(hours: float) -> str:
    """Presenta horas con coma decimal y sin ceros innecesarios."""

    return f"{hours:g}".replace(".", ",") + " h"


def format_variance(hours: float) -> str:
    """Expresa el desvío de esfuerzo con signo, sin inferir demoras de calendario."""

    return ("+" if hours >= 0 else "−") + format_estimate(abs(hours))


def _date_label(day: date) -> str:
    return f"{day.day:02d}/{day.month:02d}"


def _time_label(hour: float) -> str:
    """Convierte una hora decimal en la hora y minuto del reloj."""

    hours, minutes = divmod(round(hour * 60), 60)
    return f"{hours:02d}:{minutes:02d}"


def build_html(
    items: Sequence[GroomingTask],
    title: str,
    options: ScheduleOptions = DEFAULT_SCHEDULE_OPTIONS,
) -> tuple[str, int]:
    """Construye el Gantt semanal, los hitos y los desvíos de esfuerzo."""

    scheduled, days = build_schedule(items, options)
    day_width = DAY_WIDTH if options.extended_hours else SIMPLIFIED_DAY_WIDTH
    scale_hours = DAY_HOURS if options.extended_hours else WORKDAY_HOURS
    scale_start = 0 if options.extended_hours else WORK_START_HOUR
    day_indices = {day: index for index, day in enumerate(days)}
    timeline_width = len(days) * day_width
    page_width = LABEL_WIDTH + timeline_width + 64
    total_estimate = sum(item.estimate for item in items)
    total_actual = sum(item.actual_hours for item in items)
    stage_headers: list[str] = []
    week_headers: list[str] = []
    for stage in STAGES:
        stage_days = [day for day in days if stage.start <= day <= stage.end]
        stage_headers.append(
            f'<div class="stage-header stage-{stage.number}" style="width:{len(stage_days) * day_width}px">'
            f"Etapa {stage.number} · semana del {_date_label(stage.delivery)}</div>"
        )
        for week in range(1, stage.weeks + 1):
            monday = stage.start + timedelta(weeks=week - 1)
            week_days = [
                day for day in stage_days if monday <= day < monday + timedelta(weeks=1)
            ]
            week_headers.append(
                f'<div class="week-header" style="width:{len(week_days) * day_width}px">'
                f"S{week} · {_date_label(monday)}–{_date_label(monday + timedelta(days=6))}</div>"
            )
    weekdays = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
    hour_labels = "".join(f"<span>{hour:02d}</span>" for hour in range(0, DAY_HOURS, 4))
    hour_axis = (
        f'<div class="hour-labels">{hour_labels}<small>24</small></div>'
        if options.extended_hours
        else ""
    )
    headers = "".join(
        f'<div class="day-header {"extra-day" if day.weekday() >= 5 else ""}">'
        f"{weekdays[day.weekday()]}<b>{day.day:02d}</b>"
        f"{hour_axis}</div>"
        for day in days
    )
    grid_cells = "".join(
        f'<div class="day-cell {"week-start" if day.weekday() == 0 else ""} '
        f'{"extra-day" if day.weekday() >= 5 else ""}"></div>'
        for day in days
    )
    milestones = "".join(
        f'<div class="milestone" style="left:{day_indices[stage.delivery] * day_width}px">'
        f"<span>E{stage.number} · {_date_label(stage.delivery)}</span></div>"
        for stage in STAGES
    )
    rows: list[str] = []
    summaries: list[str] = []
    for stage in STAGES:
        stage_tasks = [task for task in scheduled if task.item.stage == stage.number]
        estimate = sum(task.item.estimate for task in stage_tasks)
        actual = sum(task.item.actual_hours for task in stage_tasks)
        summaries.append(
            f"<tr><th>Etapa {stage.number}</th><td>Semana del {_date_label(stage.delivery)}</td>"
            f"<td>{len(stage_tasks) if stage_tasks else 'Pendiente de grooming'}</td>"
            f"<td>{format_estimate(estimate) if stage_tasks else '—'}</td>"
            f"<td>{format_estimate(actual) if stage_tasks else '—'}</td>"
            f"<td>{format_variance(actual - estimate) if stage_tasks else '—'}</td></tr>"
        )
        rows.append(
            f'<div class="section-row stage-{stage.number}"><strong>Etapa {stage.number}</strong>'
            f"<span>Semana de entrega: {_date_label(stage.delivery)} · {stage.weeks} semanas</span></div>"
        )
        if not stage_tasks:
            rows.append(
                '<div class="pending-row"><b>Sin grooming de tareas</b> · '
                "Hito de la consigna; actividades pendientes de desglosar y estimar.</div>"
            )
        for task in stage_tasks:
            item = task.item
            bars: list[str] = []
            for segment in task.segments:
                left = (
                    day_indices[segment.day]
                    + (segment.start_hour - scale_start) / scale_hours
                ) * day_width
                width = segment.hours / scale_hours * day_width
                time_range = f"{_time_label(segment.start_hour)}–{_time_label(segment.start_hour + segment.hours)}"
                tooltip = html.escape(
                    f"{item.key}: {item.title} · {_date_label(segment.day)} · {time_range} · "
                    f"{format_estimate(segment.hours)} de {format_estimate(item.actual_hours)} efectivas",
                    quote=True,
                )
                if options.extended_hours:
                    bars.append(
                        f'<span class="bar-time" style="left:{left:.2f}px">{time_range}</span>'
                    )
                bars.append(
                    f'<div class="bar stage-{item.stage}" style="left:{left:.2f}px;width:{width:.2f}px" '
                    f'title="{tooltip}" aria-label="{tooltip}"></div>'
                )
            variance = item.actual_hours - item.estimate
            rows.append(
                f'<div class="task-row"><div class="task-label">'
                f'<div class="task-title"><strong>{item.key}</strong> {html.escape(item.title)}</div>'
                f'<div class="task-meta"><span>{html.escape(item.epic)} · S{item.suggested_week}</span>'
                f"<b>{format_estimate(item.actual_hours)} efectivas</b> · est. {format_estimate(item.estimate)} · "
                f'<em class="{"over" if variance > 0 else "under"}">Δ {format_variance(variance)}</em></div></div>'
                f'<div class="timeline"><div class="day-grid">{grid_cells}</div>{"".join(bars)}</div></div>'
            )
    scale_note = (
        "Escala diaria de 00:00 a 24:00; "
        if options.extended_hours
        else "Vista diaria simplificada; "
    )
    document = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; color: #172033; background: #f3f6fb;
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ width: {page_width}px; padding: 32px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; }}
    .subtitle, .note {{ color: #475467; font-size: 14px; line-height: 1.5; }}
    .summary {{ display: flex; gap: 28px; margin: 18px 0; padding: 14px 18px;
      background: white; border: 1px solid #cfd8e6; border-radius: 8px; font-weight: 700; }}
    .gantt {{ overflow: hidden; border: 1px solid #cfd8e6; border-radius: 8px; background: white; }}
    .calendar, .task-row {{ display: grid; grid-template-columns: {LABEL_WIDTH}px {timeline_width}px; }}
    .calendar {{ position: sticky; top: 0; z-index: 5; border-bottom: 2px solid #aebbd0; }}
    .calendar-label {{ display: flex; flex-direction: column; justify-content: center; gap: 8px;
      padding: 18px; background: #e9eef7; border-right: 1px solid #cfd8e6; font-size: 16px; }}
    .calendar-label small {{ color: #475467; font-size: 12px; }}
    .stage-headers, .week-headers, .calendar-days {{ display: flex; }}
    .stage-header {{ padding: 12px 4px; text-align: center; color: white; font-size: 12px; font-weight: 700; }}
    .week-header {{ padding: 9px 0; text-align: center; background: #e9eef7;
      border-right: 2px solid #aebbd0; font-size: 10px; }}
    .day-header {{ flex: 0 0 {day_width}px; padding: 7px 0 0; text-align: center;
      background: #f3f6fb; border-right: 1px solid #dbe2ee; color: #475467; font-size: 12px; }}
    .day-header b {{ margin-left: 5px; }}
    .simplified .day-header {{ padding-bottom: 7px; font-size: 9px; }}
    .simplified .day-header b {{ display: block; margin-left: 0; margin-top: 2px; }}
    .hour-labels {{ position: relative; display: grid; grid-template-columns: repeat(6, 1fr);
      height: 21px; margin-top: 7px; text-align: left; font-size: 9px; }}
    .hour-labels span {{ padding-left: 2px; border-left: 1px solid #aebbd0; }}
    .hour-labels small {{ position: absolute; right: 2px; top: 0; font-size: 9px; }}
    .gantt-body {{ position: relative; }}
    .section-row {{ position: relative; z-index: 2; display: flex; align-items: center;
      gap: 24px; height: 42px; padding: 0 16px; color: white; font-size: 14px; }}
    .section-row span {{ font-size: 12px; }}
    .task-row {{ height: {ROW_HEIGHT}px; border-bottom: 1px solid #e3e8f0; }}
    .task-label {{ position: relative; z-index: 2; padding: 8px 14px; background: white;
      border-right: 1px solid #cfd8e6; min-width: 0; }}
    .task-title {{ font-size: 12px; line-height: 1.35; }}
    .task-title strong {{ color: #175cd3; margin-right: 6px; }}
    .task-meta {{ display: flex; align-items: center; flex-wrap: wrap; gap: 5px;
      margin-top: 4px; font-size: 10px; color: #475467; }}
    .task-meta > span {{ max-width: 275px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .task-meta em {{ font-style: normal; font-weight: 700; }}
    .over {{ color: #b42318; }} .under {{ color: #027a48; }}
    .timeline {{ position: relative; }}
    .day-grid {{ position: absolute; inset: 0; display: grid;
      grid-template-columns: repeat({len(days)}, {day_width}px); }}
    .day-cell {{ border-right: 1px solid #aebbd0; background-color: #fff; }}
    .extended .day-cell {{ background-origin: border-box;
      background-image:
        repeating-linear-gradient(to right, #cfd8e6 0, #cfd8e6 1px,
          transparent 1px, transparent {day_width / DAY_HOURS:g}px),
        linear-gradient(to right, #e9edf4 0%, #e9edf4 {WORK_START_HOUR / DAY_HOURS * 100:g}%,
          transparent {WORK_START_HOUR / DAY_HOURS * 100:g}%, transparent {WORK_END_HOUR / DAY_HOURS * 100:g}%,
          #e9edf4 {WORK_END_HOUR / DAY_HOURS * 100:g}%, #e9edf4 100%); }}
    .week-start {{ border-left: 2px solid #aebbd0; }}
    .extra-day {{ background-color: #fff2d6; }}
    .bar-time {{ position: absolute; top: 6px; color: #344054; font-size: 10px;
      white-space: nowrap; z-index: 2; }}
    .bar {{ position: absolute; top: 25px; height: 22px; min-width: 2px; z-index: 2;
      border-radius: 3px; box-shadow: 0 1px 3px rgb(16 24 40 / 20%); }}
    .simplified .bar {{ top: 20px; }}
    .stage-1 {{ background: #2563eb; }} .stage-2 {{ background: #7c3aed; }}
    .stage-3 {{ background: #087f8c; }} .stage-4 {{ background: #b45309; }}
    .milestones {{ position: absolute; left: {LABEL_WIDTH}px; top: 0; bottom: 0; pointer-events: none; }}
    .milestone {{ position: absolute; top: 0; bottom: 0; border-left: 1px dashed #b42318; }}
    .milestone span {{ position: absolute; top: 46px; left: 3px; padding: 3px;
      background: #b42318; color: white; white-space: nowrap; font-size: 9px; }}
    .pending-row {{ position: relative; z-index: 2; padding: 18px; color: #475467;
      background: #f8fafc; font-size: 13px; }}
    table {{ width: 1100px; border-collapse: collapse; background: white; margin: 20px 0; font-size: 13px; }}
    th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #dbe2ee; }}
    thead {{ background: #e9eef7; }}
    tfoot {{ background: #e9eef7; font-weight: 700; border-top: 2px solid #aebbd0; }}
    @media print {{ .calendar {{ position: static; }} }}
  </style>
</head>
<body class="{"extended" if options.extended_hours else "simplified"}">
  <main>
    <h1>{html.escape(title)}</h1>
    <p class="subtitle">{_date_label(days[0])}–{_date_label(days[-1])}/2026</p>
    <div class="summary"><span>{len(items)} tareas</span>
      <span>{format_estimate(total_actual)} efectivas</span>
      <span>{format_estimate(total_estimate)} estimadas</span>
      <span>Desvío de esfuerzo: {format_variance(total_actual - total_estimate)}</span></div>
    <p class="note">
      El ancho de cada barra representa horas efectivas. {scale_note}
      tareas entre las {WORK_START_HOUR:02d}:00 y las {WORK_END_HOUR:02d}:00.</p>
    <section class="gantt" aria-label="Gantt consolidado por etapas y semanas">
      <div class="calendar"><div class="calendar-label"><b>Actividades por etapa</b>
        <small>ID de etapa + ID del grooming · estimación, horas efectivas y desvío</small></div>
        <div><div class="stage-headers">{"".join(stage_headers)}</div>
          <div class="week-headers">{"".join(week_headers)}</div>
          <div class="calendar-days">{headers}</div></div></div>
      <div class="gantt-body">{"".join(rows)}<div class="milestones">{milestones}</div></div>
    </section>
    <table aria-label="Horas y desvíos por etapa"><thead><tr><th>Etapa</th><th>Hito de la consigna</th>
      <th>Tareas</th><th>Estimación</th><th>Horas efectivas</th><th>Desvío</th></tr></thead>
      <tbody>{"".join(summaries)}</tbody>
      <tfoot><tr><th scope="row" colspan="2">Totales</th>
        <td>{len(items)}</td><td>{format_estimate(total_estimate)}</td>
        <td>{format_estimate(total_actual)}</td>
        <td>{format_variance(total_actual - total_estimate)}</td></tr></tfoot></table>
  </main>
</body>
</html>
"""
    return document, page_width


def render_with_playwright(
    html_path: Path, png_path: Path, pdf_path: Path, page_width: int
) -> None:
    """Renderiza el HTML con Chromium mediante el Playwright del frontend."""

    repository_root = Path(__file__).resolve().parent.parent
    playwright_module = (
        repository_root / "frontend" / "node_modules" / "playwright" / "index.mjs"
    )
    if not playwright_module.exists():
        raise RuntimeError(
            "No se encontró Playwright. Ejecutá npm install dentro de frontend."
        )

    renderer = f"""
import {{ chromium }} from {json.dumps(playwright_module.as_uri())};
const [htmlUrl, pngPath, pdfPath, rawWidth] = process.argv.slice(1);
const width = Number(rawWidth);
const browser = await chromium.launch({{ headless: true }});
try {{
  const page = await browser.newPage({{
    viewport: {{ width, height: 1000 }},
    deviceScaleFactor: 1,
  }});
  await page.goto(htmlUrl, {{ waitUntil: "load" }});
  await page.screenshot({{ path: pngPath, fullPage: true }});
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.pdf({{
    path: pdfPath,
    width: `${{width}}px`,
    height: `${{height}}px`,
    printBackground: true,
    margin: {{ top: "0px", right: "0px", bottom: "0px", left: "0px" }},
  }});
}} finally {{
  await browser.close();
}}
"""
    command = [
        "node",
        "--input-type=module",
        "--eval",
        renderer,
        html_path.as_uri(),
        str(png_path),
        str(pdf_path),
        str(page_width),
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode == 0:
        return

    detail = result.stderr.strip() or result.stdout.strip()
    if "Executable doesn't exist" in detail:
        raise RuntimeError(
            "No está instalado Chromium para Playwright. Ejecutá: "
            "cd frontend && npx playwright install chromium"
        )
    raise RuntimeError(f"Playwright no pudo generar los archivos: {detail}")


def main(argv: Sequence[str] | None = None) -> int:
    """Consolida los groomings y genera el Gantt sin consultar servicios externos."""

    args = parse_args(argv)
    try:
        options = ScheduleOptions(
            args.min_tasks_per_day,
            args.max_tasks_per_day,
            args.randomize,
            args.seed,
            args.weekend_days,
            args.extended_hours,
        )
        items = read_groomings(args.groomings_dir)
        document, page_width = build_html(items, args.title, options)
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        html_path = output_dir / "gantt-todas-las-etapas.html"
        html_path.write_text(document, encoding="utf-8")
        print(f"HTML generado: {html_path}")
        if not args.html_only:
            png_path = output_dir / "gantt-todas-las-etapas.png"
            pdf_path = output_dir / "gantt-todas-las-etapas.pdf"
            render_with_playwright(html_path, png_path, pdf_path, page_width)
            print(f"PNG generado: {png_path}")
            print(f"PDF generado: {pdf_path}")
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
