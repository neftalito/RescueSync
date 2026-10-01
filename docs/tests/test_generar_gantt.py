"""Pruebas del generador del Gantt de la Entrega 2."""

from __future__ import annotations

import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from runpy import run_path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GANTT = run_path(REPOSITORY_ROOT / "docs" / "generar_gantt.py", run_name="gantt")


class GanttTests(unittest.TestCase):
    """Verifica horas reales, precedencias y salida HTML."""

    def setUp(self) -> None:
        """Construye las tareas T1-T21 con las duraciones del Excel."""

        self.actual_hours = GANTT["read_actual_hours"](
            REPOSITORY_ROOT / "docs" / "Grooming Etapa Actual.xlsx"
        )
        project_item = GANTT["ProjectItem"]
        self.items = [
            project_item(
                number=number,
                title=f"[T{number}] Tarea {number}",
                url=f"https://github.com/neftalito/RescueSync/issues/{number}",
                status="Done",
                estimate=2.0,
                actual_hours=hours,
                start=date(2026, 9, 14),
                target=date(2026, 10, 2),
                labels=("entrega-2",),
            )
            for number, hours in sorted(self.actual_hours.items())
        ]

    def test_excel_contiene_las_21_tareas_y_5425_horas(self) -> None:
        """Convierte correctamente las duraciones Excel de días a horas."""

        self.assertEqual(len(self.actual_hours), 21)
        self.assertEqual(sum(self.actual_hours.values()), 54.25)
        self.assertEqual(self.actual_hours[3], 1.25)
        self.assertEqual(self.actual_hours[15], 5.0)

    def test_cronograma_respeta_jornadas_y_precedencias(self) -> None:
        """Mantiene una o dos tareas por día y ninguna inicia antes de su bloqueo."""

        scheduled, days = GANTT["build_schedule"](self.items)
        tasks_per_day = Counter(task.plan.day_index for task in scheduled)
        by_number = {task.item.number: task for task in scheduled}

        self.assertEqual(len(days), 15)
        self.assertLessEqual(max(tasks_per_day.values()), 2)
        for task in scheduled:
            for dependency in task.plan.dependencies:
                self.assertLessEqual(
                    by_number[dependency].end_units,
                    task.start_units,
                    f"T{task.item.number} se superpone con T{dependency}",
                )

    def test_html_expone_horas_reales_sin_flechas(self) -> None:
        """Incluye el total y el hito sin superponer flechas en la grilla."""

        document, page_width = GANTT["build_html"](
            self.items, "RescueSync — Entrega 2", 6
        )

        self.assertGreater(page_width, 2000)
        self.assertIn("54,25 h reales", document)
        self.assertNotIn('class="dependency-layer"', document)
        self.assertNotIn("marker-end", document)
        self.assertIn('<div class="milestone">', document)


if __name__ == "__main__":
    unittest.main()
