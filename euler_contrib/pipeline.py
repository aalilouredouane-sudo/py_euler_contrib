from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .bridge import bridge
from .config import (ALLOCATION, ALLOCATIONS, ATTRIBUTION, ATTRIBUTIONS, GROUP_LABEL,
                     HALF_WINDOW, MIN_ABS, PARAMETERS_SHEET, RETURN_PERIOD, SCALE)
from .exporter import ExcelExporter
from .reader import AggregationReader, to_eur

SHEET_SUFFIXES = ("_waterfall", "_detail")


class EulerContribPipeline:
    def __init__(self, year_n_1: str, year_n: str, aggregation_n_1: Path, aggregation_n: Path,
                 fx_ref: dict[str, float], fx_new: dict[str, float], output_path: Path,
                 entity: str | None = "XL", scale: float = SCALE,
                 rp: int = RETURN_PERIOD, half_window: int = HALF_WINDOW,
                 allocation: str = ALLOCATION, attribution: str = ATTRIBUTION,
                 min_abs: float = MIN_ABS):
        self.year_n_1 = year_n_1
        self.year_n = year_n
        self.aggregation_n_1 = aggregation_n_1  # dossier de sorties py_aggregation_cat de N-1
        self.aggregation_n = aggregation_n      # idem pour N
        self.fx_ref = fx_ref   # taux de référence par entité (N-1 et impact modèle)
        self.fx_new = fx_new   # nouveau taux par entité (effet change)
        self.output_path = output_path
        self.entity = entity
        self.rp = rp
        self.half_window = half_window
        self.allocation = allocation  # "tvar" (co-TVaR) ou "window" (k-ième +/- half_window)
        self.attribution = attribution  # barres du waterfall : "shapley" ou "euler"
        self.min_abs = min_abs
        self.scale = scale  # diviseur des pertes : 1e6 -> millions
        self._check_parameters()

    @property
    def entity_label(self) -> str:
        """Nom des onglets de l'entité (code py_aggregation_cat, ex. 'XL')."""
        return self.entity

    def _check_parameters(self) -> None:
        if self.year_n_1 == self.year_n:
            raise ValueError(f"year_n_1 and year_n must differ (both are '{self.year_n}').")
        if self.allocation not in ALLOCATIONS:
            raise ValueError(f"allocation must be one of {ALLOCATIONS}, got '{self.allocation}'.")
        if self.attribution not in ATTRIBUTIONS:
            raise ValueError(f"attribution must be one of {ATTRIBUTIONS}, got '{self.attribution}'.")
        if self.entity is None:
            return
        if self.entity_label in (GROUP_LABEL, PARAMETERS_SHEET):
            raise ValueError(f"Entity '{self.entity}' would clash with the '{self.entity_label}' sheets.")
        longest = max(len(s) for s in SHEET_SUFFIXES)
        if len(self.entity_label) + longest > 31:
            raise ValueError(
                f"Entity label '{self.entity_label}' is too long for an Excel sheet name "
                f"(max {31 - longest} characters).")

    def load(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Strips en EUR : N-1 au taux de référence, N au taux de référence, N au nouveau taux."""
        print(f"Loading {self.year_n_1} strips from {self.aggregation_n_1}")
        prev_loc = self._read(self.aggregation_n_1)
        print(f"Loading {self.year_n} strips from {self.aggregation_n}")
        curr_loc = self._read(self.aggregation_n)
        return (to_eur(prev_loc, self.fx_ref, "fx_ref"),
                to_eur(curr_loc, self.fx_ref, "fx_ref"),
                to_eur(curr_loc, self.fx_new, "fx_new"))

    def _read(self, folder: Path) -> pd.DataFrame:
        strips = AggregationReader(folder).load()
        strips["loss"] = strips["loss"] / self.scale
        return strips

    def run(self) -> dict[str, pd.DataFrame]:
        prev, curr, curr_fx = self.load()
        kw = dict(year_n_1=self.year_n_1, year_n=self.year_n,
                  rp=self.rp, half_window=self.half_window, allocation=self.allocation,
                  attribution=self.attribution)

        print(f"Bridge for {GROUP_LABEL}")
        blocks = {GROUP_LABEL: bridge(prev, curr, curr_fx, **kw)}
        if self.entity is not None:
            for name, s in [(self.year_n_1, prev), (self.year_n, curr)]:
                if self.entity not in set(s["entity"]):
                    raise ValueError(f"Entity '{self.entity}' not found in the {name} strips.")
            sub = lambda s: s[s["entity"] == self.entity]
            print(f"Bridge for {self.entity}")
            blocks[self.entity_label] = bridge(sub(prev), sub(curr), sub(curr_fx), **kw)

        ExcelExporter(self.output_path, self.year_n_1, self.year_n, self.min_abs,
                      self.attribution).export(
            blocks, self._parameters_table())
        print(f"Excel file created: {self.output_path}")
        return blocks

    def _parameters_table(self) -> pd.DataFrame:
        rows = {
            "run_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "year_n_1": self.year_n_1,
            "year_n": self.year_n,
            "aggregation_n_1": str(self.aggregation_n_1),
            "aggregation_n": str(self.aggregation_n),
            "scale": self.scale,
            "fx_ref": ", ".join(f"{e}: {r}" for e, r in self.fx_ref.items()),
            "fx_new": ", ".join(f"{e}: {r}" for e, r in self.fx_new.items()),
            "output_file": str(self.output_path),
            "entity": self.entity or "",
            "rp": self.rp,
            "half_window": self.half_window,
            "allocation": self.allocation,
            "attribution": self.attribution,
            "min_abs": self.min_abs,
        }
        return pd.DataFrame({"Parameter": list(rows), "Value": [str(v) for v in rows.values()]})
