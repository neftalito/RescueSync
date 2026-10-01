"""Genera un Gantt en PNG y PDF desde un proyecto de GitHub."""

from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

DEFAULT_OWNER = "neftalito"
DEFAULT_PROJECT_NUMBER = 6
DEFAULT_TITLE = "RescueSync — Entrega 2"
DAY_WIDTH = 112
LABEL_WIDTH = 600
ROW_HEIGHT = 54
WORKDAY_HOURS = 8.0
SPREADSHEET_NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


@dataclass(frozen=True, slots=True)
class ProjectItem:
    """Representa los datos de planificación necesarios para una barra."""

    number: int
    title: str
    url: str
    status: str
    estimate: float
    actual_hours: float
    start: date
    target: date
    labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TaskPlan:
    """Ubica una tarea en la jornada y declara sus predecesoras."""

    day_index: int
    start_hour: float
    dependencies: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class ScheduledTask:
    """Combina una tarea con su posición validada en el Gantt."""

    item: ProjectItem
    plan: TaskPlan
    row_index: int

    @property
    def start_units(self) -> float:
        """Devuelve el inicio en horas laborables desde el comienzo del plan."""

        return self.plan.day_index * WORKDAY_HOURS + self.plan.start_hour

    @property
    def end_units(self) -> float:
        """Devuelve el fin en horas laborables desde el comienzo del plan."""

        return self.start_units + self.item.actual_hours


# Reconstrucción basada en las restricciones de T1-T21. Cada jornada inicia una
# o dos tareas; las horas del Excel determinan exclusivamente el ancho real.
TASK_PLAN: dict[int, TaskPlan] = {
    2: TaskPlan(0, 0.0),
    15: TaskPlan(0, 3.0, (2,)),
    1: TaskPlan(1, 0.0, (2,)),
    17: TaskPlan(1, 4.0, (15,)),
    3: TaskPlan(2, 0.0, (1,)),
    7: TaskPlan(2, 1.5, (2,)),
    8: TaskPlan(3, 0.0, (7,)),
    4: TaskPlan(3, 2.0, (3, 8)),
    5: TaskPlan(4, 0.0, (3, 8)),
    16: TaskPlan(4, 3.5, (4, 17)),
    9: TaskPlan(5, 0.0, (4,)),
    10: TaskPlan(5, 1.5, (4, 8)),
    11: TaskPlan(6, 0.0, (5, 10)),
    6: TaskPlan(6, 2.5, (5, 8)),
    12: TaskPlan(7, 0.0, (11,)),
    14: TaskPlan(8, 0.0, (6, 12)),
    13: TaskPlan(9, 0.0, (14,)),
    18: TaskPlan(10, 0.0, (9, 10, 12, 13, 16)),
    19: TaskPlan(11, 0.0, (18,)),
    20: TaskPlan(12, 0.0, (19,)),
    21: TaskPlan(13, 0.0, (20,)),
}

TASK_GROUPS: dict[int, str] = {
    1: "foundation",
    2: "foundation",
    3: "foundation",
    4: "municipality",
    5: "lots",
    6: "offers",
    7: "security",
    8: "security",
    9: "municipality",
    10: "municipality",
    11: "lots",
    12: "lots",
    13: "offers",
    14: "offers",
    15: "bonita",
    16: "bonita",
    17: "bonita",
    18: "qa",
    19: "qa",
    20: "delivery",
    21: "delivery",
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Interpreta las opciones de consulta y de salida."""

    repository_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description=(
            "Genera docs/generated/gantt-entrega-2.png y .pdf desde GitHub Projects."
        )
    )
    parser.add_argument("--owner", default=DEFAULT_OWNER, help="Dueño del Project.")
    parser.add_argument(
        "--project-number",
        type=int,
        default=DEFAULT_PROJECT_NUMBER,
        help="Número del Project de GitHub.",
    )
    parser.add_argument("--title", default=DEFAULT_TITLE, help="Título del Gantt.")
    parser.add_argument(
        "--actual-hours-xlsx",
        type=Path,
        default=repository_root / "docs" / "Grooming Etapa Actual.xlsx",
        help="Excel con las horas efectivas de T1-T21.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repository_root / "docs" / "generated",
        help="Directorio para los archivos generados.",
    )
    parser.add_argument(
        "--input-json",
        type=Path,
        help="JSON de gh project item-list; evita consultar GitHub.",
    )
    return parser.parse_args(argv)


def require_mapping(value: object, context: str) -> dict[str, object]:
    """Valida un objeto JSON y normaliza sus claves como texto."""

    if not isinstance(value, dict):
        raise TypeError(f"{context} debe ser un objeto JSON.")
    return {str(key): child for key, child in value.items()}


def require_list(value: object, context: str) -> list[object]:
    """Valida que un valor JSON sea una lista."""

    if not isinstance(value, list):
        raise TypeError(f"{context} debe ser una lista JSON.")
    return list(value)


def require_string(value: object, context: str) -> str:
    """Obtiene un texto obligatorio y no vacío desde JSON."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} debe ser un texto no vacío.")
    return value.strip()


def require_number(value: object, context: str) -> float:
    """Obtiene una estimación numérica positiva desde JSON."""

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{context} debe ser un número.")
    number = float(value)
    if number <= 0:
        raise ValueError(f"{context} debe ser mayor que cero.")
    return number


def require_integer(value: object, context: str) -> int:
    """Obtiene un entero desde JSON sin aceptar booleanos."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{context} debe ser un entero.")
    return value


def parse_iso_date(value: object, context: str) -> date:
    """Valida una fecha de GitHub en formato ISO."""

    raw_date = require_string(value, context)
    try:
        return date.fromisoformat(raw_date)
    except ValueError as error:
        raise ValueError(f"{context} no contiene una fecha ISO válida.") from error


def _shared_strings(archive: ZipFile) -> list[str]:
    """Lee la tabla de textos compartidos de un archivo XLSX."""

    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    namespace = {"x": SPREADSHEET_NAMESPACE}
    return ["".join(node.itertext()) for node in root.findall("x:si", namespace)]


def _cell_value(cell: ElementTree.Element, shared_strings: Sequence[str]) -> str:
    """Obtiene el valor almacenado o calculado de una celda."""

    namespace = {"x": SPREADSHEET_NAMESPACE}
    value_node = cell.find("x:v", namespace)
    raw_value = "" if value_node is None else value_node.text or ""
    if cell.attrib.get("t") == "s" and raw_value:
        try:
            return shared_strings[int(raw_value)]
        except (IndexError, ValueError) as error:
            raise ValueError(
                "El XLSX contiene un texto compartido inválido."
            ) from error
    inline = cell.find("x:is", namespace)
    if inline is not None:
        return "".join(inline.itertext())
    return raw_value


def _column_name(cell_reference: str) -> str:
    """Separa la columna alfabética de una referencia como F13."""

    return "".join(character for character in cell_reference if character.isalpha())


def read_actual_hours(path: Path) -> dict[int, float]:
    """Lee las horas efectivas del grooming sin dependencias adicionales."""

    namespace = {"x": SPREADSHEET_NAMESPACE}
    try:
        with ZipFile(path) as archive:
            shared_strings = _shared_strings(archive)
            sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except (OSError, BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise RuntimeError(f"No se pudo leer el XLSX {path}: {error}") from error

    rows: list[dict[str, str]] = []
    for row in sheet.findall(".//x:sheetData/x:row", namespace):
        values: dict[str, str] = {}
        for cell in row.findall("x:c", namespace):
            reference = cell.attrib.get("r", "")
            values[_column_name(reference)] = _cell_value(cell, shared_strings)
        rows.append(values)

    header_index = next(
        (
            index
            for index, values in enumerate(rows)
            if values.get("A") == "ID" and values.get("F") == "Horas efectivas"
        ),
        None,
    )
    if header_index is None:
        raise ValueError(
            "El XLSX debe contener las columnas ID y Horas efectivas en A y F."
        )

    actual_hours: dict[int, float] = {}
    for values in rows[header_index + 1 :]:
        task_id = values.get("A", "").strip()
        if not task_id.startswith("T") or not task_id[1:].isdigit():
            continue
        task_number = int(task_id[1:])
        raw_duration = values.get("F", "").strip()
        try:
            hours = round(float(raw_duration) * 24, 2)
        except ValueError as error:
            raise ValueError(
                f"{task_id} no contiene horas efectivas válidas."
            ) from error
        if hours <= 0:
            raise ValueError(f"{task_id} debe tener horas efectivas mayores que cero.")
        if task_number in actual_hours:
            raise ValueError(f"{task_id} está repetida en el XLSX.")
        actual_hours[task_number] = hours

    if not actual_hours:
        raise ValueError("El XLSX no contiene horas efectivas para ninguna tarea.")
    return actual_hours


def parse_project_items(
    payload: object, included_numbers: set[int] | None = None
) -> list[ProjectItem]:
    """Convierte la respuesta de GitHub en tareas tipadas del grooming."""

    root = require_mapping(payload, "La respuesta del Project")
    raw_items = require_list(root.get("items"), "items")
    items: list[ProjectItem] = []

    for index, raw_item in enumerate(raw_items, start=1):
        item = require_mapping(raw_item, f"items[{index}]")
        content_value = item.get("content")
        if not isinstance(content_value, dict):
            continue
        content = {str(key): child for key, child in content_value.items()}
        raw_number = content.get("number")
        if isinstance(raw_number, bool) or not isinstance(raw_number, int):
            continue
        number = require_integer(raw_number, f"items[{index}].number")
        if included_numbers is not None and number not in included_numbers:
            continue
        start = parse_iso_date(item.get("start date"), f"issue #{number} Start date")
        target = parse_iso_date(item.get("target date"), f"issue #{number} Target date")
        if target < start:
            raise ValueError(f"El issue #{number} termina antes de su fecha de inicio.")

        raw_labels = require_list(item.get("labels", []), f"issue #{number} labels")
        labels = tuple(
            require_string(label, f"issue #{number} label") for label in raw_labels
        )
        items.append(
            ProjectItem(
                number=number,
                title=require_string(content.get("title"), f"issue #{number} title"),
                url=require_string(content.get("url"), f"issue #{number} url"),
                status=require_string(item.get("status"), f"issue #{number} status"),
                estimate=require_number(
                    item.get("estimate"), f"issue #{number} Estimate"
                ),
                actual_hours=require_number(
                    item.get("estimate"), f"issue #{number} Estimate"
                ),
                start=start,
                target=target,
                labels=labels,
            )
        )

    if not items:
        raise ValueError("El Project no contiene items para generar el Gantt.")
    if included_numbers is not None:
        found_numbers = {item.number for item in items}
        missing_numbers = sorted(included_numbers - found_numbers)
        if missing_numbers:
            formatted = ", ".join(f"T{number}" for number in missing_numbers)
            raise ValueError(f"Faltan tareas del grooming en el Project: {formatted}.")
    return sorted(items, key=lambda project_item: project_item.number)


def apply_actual_hours(
    items: Sequence[ProjectItem], actual_hours: dict[int, float]
) -> list[ProjectItem]:
    """Incorpora a cada issue la duración efectiva informada en el Excel."""

    missing_numbers = sorted({item.number for item in items} - actual_hours.keys())
    if missing_numbers:
        formatted = ", ".join(f"T{number}" for number in missing_numbers)
        raise ValueError(f"Faltan horas efectivas en el XLSX para: {formatted}.")
    return [replace(item, actual_hours=actual_hours[item.number]) for item in items]


def load_project_payload(
    owner: str, project_number: int, input_json: Path | None
) -> object:
    """Carga datos desde un archivo o consulta GitHub mediante gh."""

    if input_json is not None:
        try:
            return json.loads(input_json.read_text(encoding="utf-8"))
        except OSError as error:
            raise RuntimeError(f"No se pudo leer {input_json}: {error}") from error
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"{input_json} no contiene JSON válido: {error}"
            ) from error

    if shutil.which("gh") is None:
        raise RuntimeError("No se encontró gh. Instalá GitHub CLI antes de continuar.")

    command = [
        "gh",
        "project",
        "item-list",
        str(project_number),
        "--owner",
        owner,
        "--limit",
        "200",
        "--format",
        "json",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"gh no pudo consultar el Project: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("gh devolvió una respuesta JSON inválida.") from error


def business_days(first_day: date, last_day: date) -> list[date]:
    """Devuelve los días laborables del intervalo, incluidos sus extremos."""

    total_days = (last_day - first_day).days + 1
    return [
        first_day + timedelta(days=offset)
        for offset in range(total_days)
        if (first_day + timedelta(days=offset)).weekday() < 5
    ]


def build_schedule(
    items: Sequence[ProjectItem],
) -> tuple[list[ScheduledTask], list[date]]:
    """Ordena el árbol y valida período, jornadas y precedencias."""

    items_by_number = {item.number: item for item in items}
    expected_numbers = set(TASK_PLAN)
    if set(items_by_number) != expected_numbers:
        missing = sorted(expected_numbers - items_by_number.keys())
        extra = sorted(items_by_number.keys() - expected_numbers)
        details: list[str] = []
        if missing:
            details.append("faltan " + ", ".join(f"T{number}" for number in missing))
        if extra:
            details.append("sobran " + ", ".join(f"T{number}" for number in extra))
        raise ValueError("El cronograma no coincide con T1-T21: " + "; ".join(details))

    days = business_days(
        min(item.start for item in items), max(item.target for item in items)
    )
    ordered_numbers = sorted(
        TASK_PLAN,
        key=lambda number: (
            TASK_PLAN[number].day_index,
            TASK_PLAN[number].start_hour,
            number,
        ),
    )
    scheduled = [
        ScheduledTask(items_by_number[number], TASK_PLAN[number], row_index)
        for row_index, number in enumerate(ordered_numbers)
    ]
    scheduled_by_number = {task.item.number: task for task in scheduled}
    for task in scheduled:
        if task.plan.day_index >= len(days):
            raise ValueError(f"T{task.item.number} queda fuera de las tres semanas.")
        day_end = (task.plan.day_index + 1) * WORKDAY_HOURS
        if task.plan.start_hour < 0 or task.end_units > day_end:
            raise ValueError(
                f"T{task.item.number} no cabe en la jornada con "
                f"{format_estimate(task.item.actual_hours)} reales."
            )
        for dependency in task.plan.dependencies:
            predecessor = scheduled_by_number.get(dependency)
            if predecessor is None:
                raise ValueError(
                    f"T{task.item.number} depende de T{dependency}, que no existe."
                )
            if predecessor.end_units > task.start_units:
                raise ValueError(
                    f"T{task.item.number} comienza antes de terminar T{dependency}."
                )
    return scheduled, days


def status_class(status: str) -> str:
    """Asigna una clase visual estable a los estados conocidos."""

    normalized = status.casefold().replace(" ", "-")
    return {
        "backlog": "backlog",
        "ready": "ready",
        "in-progress": "in-progress",
        "in-review": "in-review",
        "done": "done",
    }.get(normalized, "other")


def format_estimate(estimate: float) -> str:
    """Presenta horas con coma decimal y sin ceros innecesarios."""

    return f"{estimate:g}".replace(".", ",") + " h"


def format_variance(hours: float) -> str:
    """Presenta el desvío con signo explícito."""

    sign = "+" if hours >= 0 else "−"
    return sign + format_estimate(abs(hours))


def task_geometry(task: ScheduledTask) -> tuple[float, float]:
    """Calcula inicio y ancho de una barra en píxeles."""

    left = (
        task.plan.day_index * DAY_WIDTH
        + task.plan.start_hour / WORKDAY_HOURS * DAY_WIDTH
    )
    width = task.item.actual_hours / WORKDAY_HOURS * DAY_WIDTH
    return left, width


def build_html(
    items: Sequence[ProjectItem], title: str, project_number: int
) -> tuple[str, int]:
    """Construye un documento HTML autocontenido para el renderizado."""

    scheduled, days = build_schedule(items)
    first_day = days[0]
    last_day = days[-1]
    timeline_width = len(days) * DAY_WIDTH
    page_width = LABEL_WIDTH + timeline_width + 64
    total_estimate = sum(item.estimate for item in items)
    total_actual = sum(item.actual_hours for item in items)
    weekday_names = ("Lun", "Mar", "Mié", "Jue", "Vie")
    month_names = (
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    )

    header_cells = "".join(
        (
            '<div class="day-header">'
            f"<strong>{weekday_names[day.weekday()]}</strong>"
            f"<span>{day.day:02d}/{day.month:02d}</span>"
            "<small>8 h</small>"
            "</div>"
        )
        for day in days
    )
    rows: list[str] = []
    for task in scheduled:
        item = task.item
        left, width = task_geometry(task)
        grid_cells = "".join('<div class="day-cell"></div>' for _day in days)
        visible_title = item.title
        expected_prefix = f"[T{item.number}] "
        if visible_title.startswith(expected_prefix):
            visible_title = visible_title.removeprefix(expected_prefix)
        escaped_url = html.escape(item.url, quote=True)
        escaped_title = html.escape(visible_title)
        escaped_status = html.escape(item.status)
        dependencies = (
            "dep. " + ", ".join(f"T{number}" for number in task.plan.dependencies)
            if task.plan.dependencies
            else "inicio"
        )
        group = TASK_GROUPS[item.number]
        bar_label = format_estimate(item.actual_hours) if width >= 40 else ""
        rows.append(
            "".join(
                (
                    '<div class="task-row">',
                    '<div class="task-label">',
                    '<div class="task-copy">',
                    (
                        f'<a href="{escaped_url}"><strong>T{item.number}</strong> '
                        f"{escaped_title}</a>"
                    ),
                    '<div class="task-meta">',
                    f'<span class="group-dot {group}"></span>',
                    f"<b>{format_estimate(item.actual_hours)} reales</b>",
                    f"<span>estimado {format_estimate(item.estimate)}</span>",
                    f"<span>{dependencies}</span>",
                    f'<span class="sr-only">Estado {escaped_status}</span>',
                    "</div></div></div>",
                    f'<div class="timeline" style="width:{timeline_width}px">',
                    f'<div class="day-grid">{grid_cells}</div>',
                    (
                        f'<a class="bar {group}" href="{escaped_url}" '
                        f'style="left:{left:.2f}px;width:{width:.2f}px" '
                        f'title="T{item.number}: '
                        f"{html.escape(item.title, quote=True)} · "
                        f'{format_estimate(item.actual_hours)} reales">'
                    ),
                    f"<span>{bar_label}</span></a>",
                    "</div></div>",
                )
            )
        )

    period = (
        f"{first_day.day} de {month_names[first_day.month - 1]} de {first_day.year}"
        f" — {last_day.day} de {month_names[last_day.month - 1]} de {last_day.year}"
    )
    body_height = len(scheduled) * ROW_HEIGHT
    milestone_left = LABEL_WIDTH + (len(days) - 0.5) * DAY_WIDTH
    document = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: #172033;
      background: #f3f6fb;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
    }}
    main {{ width: {page_width}px; padding: 32px; background: #f3f6fb; }}
    .heading {{
      display: flex; align-items: flex-end; justify-content: space-between;
      gap: 24px; margin-bottom: 22px;
    }}
    h1 {{ margin: 0 0 6px; color: #121a2a; font-size: 28px; }}
    .subtitle {{ margin: 0; color: #667085; font-size: 14px; }}
    .summary {{
      display: flex; gap: 14px; padding: 10px 14px;
      border: 1px solid #cfd8e6; border-radius: 10px;
      background: #fff; color: #344054; font-size: 14px; font-weight: 700;
    }}
    .summary .variance {{ color: #b42318; }}
    .gantt {{ overflow: hidden; border: 1px solid #cfd8e6; border-radius: 12px;
      background: #fff; box-shadow: 0 5px 18px rgb(16 24 40 / 8%); }}
    .calendar, .task-row {{ display: grid; grid-template-columns: {LABEL_WIDTH}px {timeline_width}px; }}
    .calendar {{ min-height: 62px; border-bottom: 2px solid #aebbd0; }}
    .calendar-label {{ display: flex; flex-direction: column; justify-content: center;
      padding: 0 18px; color: #344054; background: #e9eef7;
      border-right: 1px solid #cfd8e6; }}
    .calendar-label strong {{ font-size: 13px; text-transform: uppercase;
      letter-spacing: .05em; }}
    .calendar-label span {{ margin-top: 4px; color: #667085; font-size: 10px; }}
    .calendar-days, .day-grid {{ display: grid; grid-template-columns: repeat({len(days)}, {DAY_WIDTH}px); }}
    .day-header {{ display: flex; align-items: center;
      justify-content: center; gap: 5px; color: #344054; background: #eef3fa;
      border-right: 1px solid #dbe2ee; font-size: 11px; }}
    .day-header span {{ color: #667085; }}
    .day-header small {{ color: #98a2b3; font-size: 9px; }}
    .gantt-body {{ position: relative; height: {body_height}px; }}
    .task-row {{ height: {ROW_HEIGHT}px; border-bottom: 1px solid #e3e8f0; }}
    .task-label {{ position: relative; z-index: 4; display: flex; align-items: center;
      min-width: 0; padding: 7px 14px; background: #fff;
      border-right: 1px solid #cfd8e6; }}
    .task-copy {{ min-width: 0; width: 100%; }}
    .task-copy > a {{ display: block; overflow: hidden; color: #27364d; font-size: 12px;
      text-decoration: none; text-overflow: ellipsis; white-space: nowrap; }}
    .task-copy strong {{ color: #175cd3; }}
    .task-meta {{ display: flex; align-items: center; gap: 8px; margin-top: 3px;
      color: #667085; font-size: 10px; }}
    .task-meta b {{ color: #344054; }}
    .group-dot {{ width: 8px; height: 8px; border-radius: 50%; }}
    .timeline {{ position: relative; min-height: {ROW_HEIGHT}px; }}
    .day-grid {{ position: absolute; inset: 0; z-index: 0; }}
    .day-cell {{ border-right: 1px solid #e3e8f0;
      background: linear-gradient(to right, transparent 49.5%, #f1f3f7 50%,
        transparent 50.5%); }}
    .day-cell:nth-child(5n+1) {{ box-shadow: inset 2px 0 #cbd5e3; }}
    .bar {{ position: absolute; z-index: 3; top: 10px; height: 34px; display: flex;
      align-items: center; justify-content: center; min-width: 8px; overflow: hidden;
      border: 2px solid rgb(255 255 255 / 90%); border-radius: 7px; color: #fff;
      font-size: 10px; font-weight: 800; text-decoration: none;
      box-shadow: 0 2px 5px rgb(16 24 40 / 25%); }}
    .foundation {{ background: #2563eb; }}
    .security {{ background: #7c3aed; }}
    .bonita {{ background: #d97706; }}
    .municipality {{ background: #0891b2; }}
    .lots {{ background: #059669; }}
    .offers {{ background: #db2777; }}
    .qa {{ background: #dc2626; }}
    .delivery {{ background: #475467; }}
    .milestone {{ position: absolute; z-index: 2; top: 0; bottom: 0;
      left: {milestone_left}px; border-left: 2px dashed #b42318; }}
    .milestone span {{ position: absolute; top: 7px; left: 6px; padding: 3px 6px;
      border-radius: 5px; color: #fff; background: #b42318; font-size: 9px;
      font-weight: 800; text-transform: uppercase; }}
    .legend {{ display: flex; align-items: center; gap: 14px; margin-top: 13px;
      color: #475467; font-size: 10px; }}
    .legend span {{ display: inline-flex; align-items: center; gap: 5px; }}
    .legend i {{ width: 9px; height: 9px; border-radius: 3px; }}
    .sr-only {{ position: absolute; width: 1px; height: 1px; padding: 0;
      margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0);
      white-space: nowrap; border: 0; }}
    footer {{ display: flex; justify-content: space-between; margin-top: 14px;
      color: #667085; font-size: 11px; }}
  </style>
</head>
<body>
  <main>
    <div class="heading">
      <div><h1>{html.escape(title)} · ejecución real</h1>
        <p class="subtitle">{period} · 15 días hábiles · precedencias de T1–T21</p>
      </div>
      <div class="summary">
        <span>{len(items)} tareas</span>
        <span>{format_estimate(total_actual)} reales</span>
        <span>estimado {format_estimate(total_estimate)}</span>
        <span class="variance">desvío {format_variance(total_actual - total_estimate)}</span>
      </div>
    </div>
    <section class="gantt" aria-label="Diagrama de Gantt de horas reales">
      <div class="calendar">
        <div class="calendar-label"><strong>Ruta de ejecución y dependencias</strong>
          <span>El ancho de cada barra representa sus horas efectivas</span>
        </div>
        <div class="calendar-days">{header_cells}</div>
      </div>
      <div class="gantt-body">
        {"".join(rows)}
        <div class="milestone"><span>Entrega</span></div>
      </div>
    </section>
    <div class="legend">
      <b>Ramas:</b>
      <span><i class="foundation"></i>Fundación</span>
      <span><i class="security"></i>Seguridad</span>
      <span><i class="bonita"></i>Bonita</span>
      <span><i class="municipality"></i>Emergencias</span>
      <span><i class="lots"></i>Lotes</span>
      <span><i class="offers"></i>Ofertas</span>
      <span><i class="qa"></i>QA</span>
      <span><i class="delivery"></i>Entrega</span>
    </div>
    <footer><span>Escala: 1 jornada = 8 h; sólo días hábiles.</span>
      <span>Fuente: Grooming Etapa Actual.xlsx y GitHub Project #{project_number}.</span>
    </footer>
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
    deviceScaleFactor: 2,
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
    """Valida el Project y el Excel, y produce ambos formatos."""

    args = parse_args(argv)
    try:
        actual_hours = read_actual_hours(args.actual_hours_xlsx)
        payload = load_project_payload(args.owner, args.project_number, args.input_json)
        items = parse_project_items(payload, set(actual_hours))
        items = apply_actual_hours(items, actual_hours)
        document, page_width = build_html(items, args.title, args.project_number)
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        png_path = output_dir / "gantt-entrega-2.png"
        pdf_path = output_dir / "gantt-entrega-2.pdf"
        with tempfile.TemporaryDirectory(prefix="rescuesync-gantt-") as temp_dir:
            html_path = Path(temp_dir) / "gantt.html"
            html_path.write_text(document, encoding="utf-8")
            render_with_playwright(html_path, png_path, pdf_path, page_width)
    except (RuntimeError, TypeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"PNG generado: {png_path}")
    print(f"PDF generado: {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
