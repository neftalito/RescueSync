#!/usr/bin/env python3
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
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


DEFAULT_OWNER = "neftalito"
DEFAULT_PROJECT_NUMBER = 6
DEFAULT_TITLE = "RescueSync — Entrega 2"
DAY_WIDTH = 72
LABEL_WIDTH = 520
ROW_HEIGHT = 52


@dataclass(frozen=True, slots=True)
class ProjectItem:
    """Representa los datos de planificación necesarios para una barra."""

    number: int
    title: str
    url: str
    status: str
    estimate: float
    start: date
    target: date
    labels: tuple[str, ...]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Interpreta las opciones de consulta y de salida."""

    repository_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description=(
            "Genera docs/generated/gantt-entrega-2.png y .pdf desde GitHub "
            "Projects."
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
        raise ValueError(f"{context} debe ser un objeto JSON.")
    return {str(key): child for key, child in value.items()}


def require_list(value: object, context: str) -> list[object]:
    """Valida que un valor JSON sea una lista."""

    if not isinstance(value, list):
        raise ValueError(f"{context} debe ser una lista JSON.")
    return list(value)


def require_string(value: object, context: str) -> str:
    """Obtiene un texto obligatorio y no vacío desde JSON."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} debe ser un texto no vacío.")
    return value.strip()


def require_number(value: object, context: str) -> float:
    """Obtiene una estimación numérica positiva desde JSON."""

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{context} debe ser un número.")
    number = float(value)
    if number <= 0:
        raise ValueError(f"{context} debe ser mayor que cero.")
    return number


def require_integer(value: object, context: str) -> int:
    """Obtiene un entero desde JSON sin aceptar booleanos."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} debe ser un entero.")
    return value


def parse_iso_date(value: object, context: str) -> date:
    """Valida una fecha de GitHub en formato ISO."""

    raw_date = require_string(value, context)
    try:
        return date.fromisoformat(raw_date)
    except ValueError as error:
        raise ValueError(f"{context} no contiene una fecha ISO válida.") from error


def parse_project_items(payload: object) -> list[ProjectItem]:
    """Convierte la respuesta de gh en elementos de planificación tipados."""

    root = require_mapping(payload, "La respuesta del Project")
    raw_items = require_list(root.get("items"), "items")
    items: list[ProjectItem] = []

    for index, raw_item in enumerate(raw_items, start=1):
        item = require_mapping(raw_item, f"items[{index}]")
        content = require_mapping(item.get("content"), f"items[{index}].content")
        number = require_integer(content.get("number"), f"items[{index}].number")
        start = parse_iso_date(item.get("start date"), f"issue #{number} Start date")
        target = parse_iso_date(
            item.get("target date"), f"issue #{number} Target date"
        )
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
                start=start,
                target=target,
                labels=labels,
            )
        )

    if not items:
        raise ValueError("El Project no contiene items para generar el Gantt.")
    return sorted(items, key=lambda project_item: project_item.number)


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
            raise RuntimeError(f"{input_json} no contiene JSON válido: {error}") from error

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


def date_range(first_day: date, last_day: date) -> list[date]:
    """Devuelve todos los días del intervalo, incluidos sus extremos."""

    days = (last_day - first_day).days + 1
    return [first_day + timedelta(days=offset) for offset in range(days)]


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
    """Presenta horas sin ceros decimales innecesarios."""

    return f"{estimate:g} h"


def build_html(
    items: Sequence[ProjectItem], title: str, project_number: int
) -> tuple[str, int]:
    """Construye un documento HTML autocontenido para el renderizado."""

    first_day = min(item.start for item in items)
    last_day = max(item.target for item in items)
    days = date_range(first_day, last_day)
    timeline_width = len(days) * DAY_WIDTH
    page_width = LABEL_WIDTH + timeline_width + 64
    total_estimate = sum(item.estimate for item in items)
    weekday_names = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
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
            f'<div class="day-header {"weekend" if day.weekday() >= 5 else ""}">'
            f"<strong>{weekday_names[day.weekday()]}</strong>"
            f"<span>{day.day:02d}/{day.month:02d}</span>"
            "</div>"
        )
        for day in days
    )
    rows: list[str] = []
    for item in items:
        start_offset = (item.start - first_day).days
        duration = (item.target - item.start).days + 1
        left = start_offset * DAY_WIDTH + 5
        width = duration * DAY_WIDTH - 10
        grid_cells = "".join(
            f'<div class="day-cell {"weekend" if day.weekday() >= 5 else ""}"></div>'
            for day in days
        )
        visible_title = item.title
        expected_prefix = f"[T{item.number}] "
        if visible_title.startswith(expected_prefix):
            visible_title = visible_title.removeprefix(expected_prefix)
        escaped_url = html.escape(item.url, quote=True)
        escaped_title = html.escape(visible_title)
        escaped_status = html.escape(item.status)
        rows.append(
            "".join(
                (
                    '<div class="task-row">',
                    '<div class="task-label">',
                    f'<a href="{escaped_url}"><strong>T{item.number}</strong> '
                    f"{escaped_title}</a>",
                    '<div class="task-meta">',
                    f'<span class="status {status_class(item.status)}">'
                    f"{escaped_status}</span>",
                    f"<span>{format_estimate(item.estimate)}</span>",
                    "</div></div>",
                    f'<div class="timeline" style="width:{timeline_width}px">',
                    f'<div class="day-grid">{grid_cells}</div>',
                    f'<a class="bar {status_class(item.status)}" href="{escaped_url}" '
                    f'style="left:{left}px;width:{width}px" '
                    f'title="T{item.number}: {html.escape(item.title, quote=True)}">',
                    f"<span>{format_estimate(item.estimate)}</span></a>",
                    "</div></div>",
                )
            )
        )

    period = (
        f"{first_day.day} de {month_names[first_day.month - 1]} de {first_day.year}"
        f" — {last_day.day} de {month_names[last_day.month - 1]} de {last_day.year}"
    )
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
      margin-bottom: 22px;
    }}
    h1 {{ margin: 0 0 6px; color: #121a2a; font-size: 28px; }}
    .subtitle {{ margin: 0; color: #667085; font-size: 14px; }}
    .summary {{
      padding: 10px 14px; border: 1px solid #cfd8e6; border-radius: 10px;
      background: #fff; color: #344054; font-size: 14px; font-weight: 700;
    }}
    .gantt {{ overflow: hidden; border: 1px solid #cfd8e6; border-radius: 12px;
      background: #fff; box-shadow: 0 5px 18px rgb(16 24 40 / 8%); }}
    .calendar, .task-row {{ display: grid; grid-template-columns: {LABEL_WIDTH}px {timeline_width}px; }}
    .calendar {{ min-height: 62px; border-bottom: 2px solid #aebbd0; }}
    .calendar-label {{ display: flex; align-items: center; padding: 0 18px;
      color: #344054; font-size: 13px; font-weight: 800; text-transform: uppercase;
      letter-spacing: .05em; background: #e9eef7; border-right: 1px solid #cfd8e6; }}
    .calendar-days, .day-grid {{ display: grid; grid-template-columns: repeat({len(days)}, {DAY_WIDTH}px); }}
    .day-header {{ display: flex; flex-direction: column; align-items: center;
      justify-content: center; gap: 4px; color: #344054; background: #eef3fa;
      border-right: 1px solid #dbe2ee; font-size: 12px; }}
    .day-header span {{ color: #667085; }}
    .weekend {{ background: #f7f1f1; }}
    .task-row {{ min-height: {ROW_HEIGHT}px; border-bottom: 1px solid #e3e8f0; }}
    .task-row:last-child {{ border-bottom: 0; }}
    .task-label {{ display: flex; align-items: center; justify-content: space-between;
      gap: 12px; padding: 8px 14px; border-right: 1px solid #cfd8e6; }}
    .task-label > a {{ overflow: hidden; color: #27364d; font-size: 13px;
      text-decoration: none; text-overflow: ellipsis; white-space: nowrap; }}
    .task-label strong {{ color: #175cd3; }}
    .task-meta {{ display: flex; flex: none; align-items: center; gap: 8px;
      color: #667085; font-size: 11px; }}
    .status {{ padding: 3px 7px; border-radius: 999px; color: #fff; font-weight: 700; }}
    .timeline {{ position: relative; min-height: {ROW_HEIGHT}px; }}
    .day-grid {{ position: absolute; inset: 0; }}
    .day-cell {{ border-right: 1px solid #edf0f5; }}
    .bar {{ position: absolute; top: 10px; height: 32px; display: flex;
      align-items: center; justify-content: center; min-width: 22px; overflow: hidden;
      border-radius: 7px; color: #fff; font-size: 11px; font-weight: 800;
      text-decoration: none; box-shadow: 0 2px 4px rgb(16 24 40 / 18%); }}
    .backlog {{ background: #667085; }}
    .ready {{ background: #175cd3; }}
    .in-progress {{ background: #dc6803; }}
    .in-review {{ background: #6938ef; }}
    .done {{ background: #067647; }}
    .other {{ background: #475467; }}
    footer {{ display: flex; justify-content: space-between; margin-top: 14px;
      color: #667085; font-size: 11px; }}
  </style>
</head>
<body>
  <main>
    <div class="heading">
      <div><h1>{html.escape(title)}</h1><p class="subtitle">{period}</p></div>
      <div class="summary">{len(items)} tareas · {format_estimate(total_estimate)}</div>
    </div>
    <section class="gantt" aria-label="Diagrama de Gantt">
      <div class="calendar">
        <div class="calendar-label">Issue y estimación</div>
        <div class="calendar-days">{header_cells}</div>
      </div>
      {''.join(rows)}
    </section>
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
    playwright_module = repository_root / "frontend" / "node_modules" / "playwright" / "index.mjs"
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
    """Consulta el Project, valida sus campos y produce ambos formatos."""

    args = parse_args(argv)
    try:
        payload = load_project_payload(args.owner, args.project_number, args.input_json)
        items = parse_project_items(payload)
        document, page_width = build_html(items, args.title, args.project_number)
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        png_path = output_dir / "gantt-entrega-2.png"
        pdf_path = output_dir / "gantt-entrega-2.pdf"
        with tempfile.TemporaryDirectory(prefix="rescuesync-gantt-") as temp_dir:
            html_path = Path(temp_dir) / "gantt.html"
            html_path.write_text(document, encoding="utf-8")
            render_with_playwright(html_path, png_path, pdf_path, page_width)
    except (RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"PNG generado: {png_path}")
    print(f"PDF generado: {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
