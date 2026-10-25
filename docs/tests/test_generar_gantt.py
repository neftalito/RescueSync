"""Verifica el cronograma consolidado de los groomings de RescueSync."""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from collections import Counter
from dataclasses import replace
from datetime import date
from itertools import pairwise
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree
from zipfile import ZipFile

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GANTT = run_path(REPOSITORY_ROOT / "docs" / "generar_gantt.py", run_name="gantt")
GROOMINGS = REPOSITORY_ROOT / "docs" / "groomings"


class GanttTests(unittest.TestCase):
    """Comprueba fuentes, unidades, capacidad diaria y semanas de entrega."""

    def setUp(self) -> None:
        self.tasks = GANTT["read_groomings"](GROOMINGS)

    def test_incluye_todas_las_etapas_sin_confundir_ids_repetidos(self) -> None:
        self.assertEqual(
            Counter(task.stage for task in self.tasks), {1: 19, 2: 21, 3: 21, 4: 21}
        )
        by_key = {task.key: task for task in self.tasks}
        self.assertEqual(len(by_key), 82)
        self.assertNotEqual(by_key["E1-T1"].title, by_key["E2-T1"].title)

    def test_convierte_horas_decimales_y_duraciones_excel(self) -> None:
        expected = {1: (26, 25.65), 2: (46, 54.25), 3: (106, 80.5), 4: (82, 28.5)}
        for stage, (estimate, actual) in expected.items():
            with self.subTest(stage=stage):
                tasks = [task for task in self.tasks if task.stage == stage]
                self.assertAlmostEqual(sum(task.estimate for task in tasks), estimate)
                self.assertAlmostEqual(sum(task.actual_hours for task in tasks), actual)
        self.assertAlmostEqual(sum(task.actual_hours for task in self.tasks), 188.9)

    def test_respeta_semanas_y_un_maximo_de_dos_tareas_activas_por_dia(self) -> None:
        options = GANTT["ScheduleOptions"](
            max_tasks_per_day=2, weekend_days=GANTT["WeekendDays"].SATURDAY
        )
        scheduled, days = GANTT["build_schedule"](self.tasks, options)
        counts = Counter(segment.day for task in scheduled for segment in task.segments)
        used_hours = Counter()
        windows = {window.number: window for window in GANTT["STAGES"]}
        for task in scheduled:
            start = windows[task.item.stage].start.toordinal()
            first_day = start + (task.item.suggested_week - 1) * 7
            self.assertAlmostEqual(
                sum(s.hours for s in task.segments), task.item.actual_hours
            )
            for segment in task.segments:
                self.assertLessEqual(first_day, segment.day.toordinal())
                self.assertLess(segment.day.toordinal(), first_day + 7)
                self.assertIn(segment.day, days)
                self.assertLessEqual(segment.start_hour + segment.hours, 8)
                used_hours[segment.day] += segment.hours
        self.assertEqual(len(scheduled), 82)
        self.assertLessEqual(max(counts.values()), 2)
        self.assertLessEqual(max(used_hours.values()), 8)
        self.assertIn(date(2026, 11, 7), counts)

    def test_minimo_y_maximo_se_respetan_en_jornadas_con_trabajo(self) -> None:
        options = GANTT["ScheduleOptions"](
            min_tasks_per_day=2, max_tasks_per_day=3, seed=17
        )
        scheduled, _days = GANTT["build_schedule"](self.tasks[:6], options)
        counts = Counter(segment.day for task in scheduled for segment in task.segments)
        self.assertTrue(all(2 <= count <= 3 for count in counts.values()))

    def test_semilla_reproduce_el_sorteo_y_otras_semillas_lo_cambian(self) -> None:
        options = GANTT["ScheduleOptions"](seed=42)
        first, _days = GANTT["build_schedule"](self.tasks, options)
        repeated, _days = GANTT["build_schedule"](self.tasks, options)
        changed, _days = GANTT["build_schedule"](self.tasks, replace(options, seed=43))
        self.assertEqual(first, repeated)
        self.assertNotEqual(first, changed)
        counts = Counter(segment.day for task in first for segment in task.segments)
        self.assertTrue(all(1 <= count <= 3 for count in counts.values()))
        self.assertGreater(len(set(counts.values())), 1)

    def test_sin_aleatoriedad_la_semilla_no_cambia_el_resultado(self) -> None:
        options = GANTT["ScheduleOptions"](randomize=False, seed=42)
        self.assertEqual(
            GANTT["build_schedule"](self.tasks, options),
            GANTT["build_schedule"](self.tasks, replace(options, seed=43)),
        )

    def test_solo_son_elegibles_los_fines_de_semana_habilitados(self) -> None:
        for weekend in GANTT["WeekendDays"]:
            with self.subTest(weekend=weekend):
                count = weekend.days_per_week
                tasks = [
                    replace(task, actual_hours=8, suggested_week=1)
                    for task in self.tasks[:count]
                ]
                options = GANTT["ScheduleOptions"](
                    max_tasks_per_day=1, weekend_days=weekend
                )
                scheduled, days = GANTT["build_schedule"](tasks, options)
                worked = {
                    segment.day.weekday()
                    for task in scheduled
                    for segment in task.segments
                }
                self.assertEqual(worked, set(range(count)))
                self.assertEqual({day.weekday() for day in days}, set(range(7)))
                self.assertEqual(days[-1], date(2026, 11, 8))

    def test_no_habilita_sabados_automaticamente_si_falta_capacidad(self) -> None:
        options = GANTT["ScheduleOptions"](max_tasks_per_day=2)
        tasks = [
            task for task in self.tasks if task.stage == 4 and task.suggested_week == 2
        ]
        with self.assertRaisesRegex(ValueError, "Etapa 4.*semana 2.*weekend-days"):
            GANTT["build_schedule"](tasks, options)

    def test_rechaza_limites_invalidos_y_minimo_imposible(self) -> None:
        for minimum, maximum in ((0, 3), (-1, 2), (3, 2)):
            with (
                self.subTest(minimum=minimum, maximum=maximum),
                self.assertRaisesRegex(ValueError, "mínimo"),
            ):
                GANTT["ScheduleOptions"](
                    min_tasks_per_day=minimum, max_tasks_per_day=maximum
                )
        options = GANTT["ScheduleOptions"](min_tasks_per_day=2, max_tasks_per_day=3)
        with self.assertRaisesRegex(ValueError, "Etapa 1.*semana 1"):
            GANTT["build_schedule"](self.tasks[:1], options)

    def test_cli_genera_html_sin_navegador_con_parametros(self) -> None:
        with TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPOSITORY_ROOT / "docs" / "generar_gantt.py"),
                    "--html-only",
                    "--output-dir",
                    directory,
                    "--min-tasks-per-day",
                    "1",
                    "--max-tasks-per-day",
                    "3",
                    "--seed",
                    "42",
                    "--weekend-days",
                    "saturday-sunday",
                ],
                cwd=directory,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            document = (Path(directory) / "gantt-todas-las-etapas.html").read_text()
            self.assertIn("82 tareas", document)
            self.assertIn("Sáb", document)
            self.assertIn("Dom", document)
            self.assertNotIn("semilla", document)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_jornada_larga_se_distribuye_sin_perder_horas(self) -> None:
        scheduled, _days = GANTT["build_schedule"](self.tasks)
        task = next(task for task in scheduled if task.item.key == "E3-T37")
        self.assertEqual(len(task.segments), 2)
        self.assertEqual(sum(segment.hours for segment in task.segments), 8.5)

    def test_los_tramos_no_se_superponen_en_una_jornada(self) -> None:
        scheduled, days = GANTT["build_schedule"](self.tasks)
        for day in days:
            segments = sorted(
                (s for task in scheduled for s in task.segments if s.day == day),
                key=lambda segment: segment.start_hour,
            )
            for previous, current in pairwise(segments):
                self.assertLessEqual(
                    previous.start_hour + previous.hours, current.start_hour
                )

    def test_hitos_de_las_cuatro_etapas_sin_etapa_5(self) -> None:
        self.assertEqual(
            [stage.delivery for stage in GANTT["STAGES"]],
            [
                date(2026, 9, 10),
                date(2026, 10, 1),
                date(2026, 10, 22),
                date(2026, 11, 5),
            ],
        )
        _scheduled, days = GANTT["build_schedule"](self.tasks)
        self.assertEqual(days[0], date(2026, 8, 24))
        self.assertEqual(days[-1], date(2026, 11, 8))
        document, _width = GANTT["build_html"](self.tasks, "RescueSync")
        for text in (
            "188,9 h",
            "−71,1 h",
        ):
            self.assertIn(text, document)
        self.assertIn('class="week-header', document)
        self.assertEqual(document.count('class="task-row"'), 82)
        for text in (
            "Etapa 5",
            "stage-5",
            "E5 ·",
            "19/11",
            "Fechas reconstruidas",
            "Días elegibles:",
            "semilla",
            "Fuentes:",
            "<footer>",
            "Etapas y semanas de entrega según Trabajo integrador 2026.pdf",
        ):
            self.assertNotIn(text, document)

    def test_muestra_semanas_completas_y_dias_con_tres_letras(self) -> None:
        scheduled, days = GANTT["build_schedule"](self.tasks)
        self.assertEqual(len(days), 77)
        for previous, current in pairwise(days):
            self.assertEqual((current - previous).days, 1)
        self.assertTrue(
            all(
                segment.day.weekday() < 5
                for task in scheduled
                for segment in task.segments
            )
        )
        document, _width = GANTT["build_html"](self.tasks, "RescueSync")
        headers = re.findall(r'<div class="day-header[^"]*">([^<]+)<b>', document)
        self.assertEqual(
            headers, ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"] * 11
        )

    def test_rechaza_semana_invalida_duplicados_y_trabajo_imposible(self) -> None:
        cases = [
            (
                [replace(self.tasks[0], suggested_week=4), *self.tasks[1:]],
                "E1-T1.*semana",
            ),
            ([*self.tasks, self.tasks[0]], "E1-T1.*repetida"),
            (
                [replace(self.tasks[0], actual_hours=49), *self.tasks[1:]],
                "Etapa 1.*semana 1",
            ),
        ]
        for tasks, message in cases:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(ValueError, message),
            ):
                GANTT["build_schedule"](tasks)

    def test_html_escapa_textos_de_los_groomings(self) -> None:
        tasks = [
            replace(self.tasks[0], title='<script>alert("x")</script>'),
            *self.tasks[1:],
        ]
        document, _width = GANTT["build_html"](tasks, "<RescueSync>")
        self.assertNotIn('<script>alert("x")</script>', document)
        self.assertIn("&lt;script&gt;", document)
        self.assertIn("&lt;RescueSync&gt;", document)

    def test_lee_inline_strings_sin_tabla_de_textos_compartidos(self) -> None:
        namespace = GANTT["SPREADSHEET_NAMESPACE"]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "Grooming Etapa 1.xlsx"
            with (
                ZipFile(GROOMINGS / path.name) as original,
                ZipFile(path, "w") as output,
            ):
                shared = GANTT["_shared_strings"](original)
                for name in original.namelist():
                    if name == "xl/sharedStrings.xml":
                        continue
                    content = original.read(name)
                    if name == "xl/worksheets/sheet1.xml":
                        root = ElementTree.fromstring(content)
                        for cell in root.iter(f"{{{namespace}}}c"):
                            if cell.get("t") == "s":
                                value = GANTT["_cell_value"](cell, shared)
                                cell.remove(cell.find(f"{{{namespace}}}v"))
                                cell.set("t", "inlineStr")
                                inline = ElementTree.SubElement(
                                    cell, f"{{{namespace}}}is"
                                )
                                ElementTree.SubElement(
                                    inline, f"{{{namespace}}}t"
                                ).text = value
                        content = ElementTree.tostring(root)
                    output.writestr(name, content)
            tasks = GANTT["read_groomings"](Path(directory))
            self.assertEqual(len(tasks), 19)
            self.assertAlmostEqual(sum(task.actual_hours for task in tasks), 25.65)

    def test_rechaza_horas_ausentes_o_no_finitas(self) -> None:
        for raw_value in ("", "nan", "inf", "-1", "0"):
            with self.subTest(raw_value=raw_value), TemporaryDirectory() as directory:
                path = Path(directory) / "Grooming Etapa 1.xlsx"
                with (
                    ZipFile(GROOMINGS / path.name) as original,
                    ZipFile(path, "w") as output,
                ):
                    for name in original.namelist():
                        content = original.read(name)
                        if name == "xl/worksheets/sheet1.xml":
                            root = ElementTree.fromstring(content)
                            ns = {"x": GANTT["SPREADSHEET_NAMESPACE"]}
                            cell = root.find('.//x:c[@r="F4"]/x:v', ns)
                            self.assertIsNotNone(cell)
                            cell.text = raw_value
                            content = ElementTree.tostring(root)
                        output.writestr(name, content)
                with self.assertRaisesRegex(ValueError, "E1-T1.*horas efectivas"):
                    GANTT["read_groomings"](Path(directory))

    def test_rechaza_carpeta_sin_groomings(self) -> None:
        with (
            TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "No se encontraron"),
        ):
            GANTT["read_groomings"](Path(directory))


if __name__ == "__main__":
    unittest.main()
