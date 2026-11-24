from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.chart import BarChart, Reference

from .bridge import waterfall_table
from .config import (ATTRIBUTION, COLOR_DECREASE, COLOR_INCREASE, COLOR_TOTAL, MIN_ABS,
                     PARAMETERS_SHEET)


class ExcelExporter:
    """Écrit un classeur : pour chaque bloc (Group, entité), un onglet <nom>_waterfall
    (tableau + graphique empilé) et un onglet <nom>_detail (bridge complet par péril),
    puis une feuille de paramètres."""

    def __init__(self, output_path: Path, year_n_1: str, year_n: str, min_abs: float = MIN_ABS,
                 attribution: str = ATTRIBUTION):
        self.output_path = output_path
        self.year_n_1 = year_n_1
        self.year_n = year_n
        self.min_abs = min_abs
        self.attribution = attribution

    def export(self, blocks: dict[str, pd.DataFrame], parameters: pd.DataFrame) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(self.output_path, engine="openpyxl") as writer:
            for name, br in blocks.items():
                waterfall_table(br, self.year_n_1, self.year_n, self.min_abs,
                                self.attribution).round(1).to_excel(
                    writer, sheet_name=f"{name}_waterfall", index=False)
                br.round(2).to_excel(writer, sheet_name=f"{name}_detail")
            parameters.to_excel(writer, sheet_name=PARAMETERS_SHEET, index=False)

        wb = load_workbook(self.output_path)
        for name in blocks:
            self._add_chart(wb[f"{name}_waterfall"], name)
        wb.save(self.output_path)

    @staticmethod
    def _add_chart(ws, name: str) -> None:
        """Histogramme empilé Base / Increase / Decrease / Total, avec Base invisible."""
        n = ws.max_row
        ch = BarChart()
        ch.type = "col"
        ch.grouping = "stacked"
        ch.overlap = 100
        ch.title = f"{name} STEC bridge (EUR m)"
        ch.legend = None
        ch.height, ch.width = 9, 18
        ch.add_data(Reference(ws, min_col=3, max_col=6, min_row=1, max_row=n), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=1, min_row=2, max_row=n))
        base, inc, dec, tot = ch.series
        base.graphicalProperties.noFill = True
        base.graphicalProperties.line.noFill = True
        for s, col in [(inc, COLOR_INCREASE), (dec, COLOR_DECREASE), (tot, COLOR_TOTAL)]:
            s.graphicalProperties.solidFill = col
            s.graphicalProperties.line.solidFill = col
        ws.add_chart(ch, "H2")
