from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .config import (AGG_FILE_PREFIX, AGG_GROUP_ENTITY, AGG_SIM_COL, AGG_STRIPS_SHEET,
                     AGG_TOTAL_COL, LONG_COLUMNS)

logger = logging.getLogger(__name__)


class AggregationReader:
    """Lit un dossier de sorties de py_aggregation_cat (une année).

    Un fichier Gross_MM_reconciliation_<entité>.xlsx par entité ; feuille Local_AAL_strips :
    colonne `year` (simulation 1..50 000), une colonne par risque (= péril), puis `Total`.
    Le fichier Gross_MM_reconciliation_Group.xlsx est ignoré.
    """

    def __init__(self, folder: Path):
        self.folder = folder

    def files(self) -> dict[str, Path]:
        """Entité -> fichier, par ordre alphabétique de nom de fichier."""
        if not self.folder.is_dir():
            raise FileNotFoundError(f"py_aggregation_cat output folder not found: {self.folder}")
        files = {f.stem[len(AGG_FILE_PREFIX):]: f
                 for f in sorted(self.folder.glob(f"{AGG_FILE_PREFIX}*.xlsx"))
                 if not f.name.startswith("~$")}  # fichiers de verrouillage Excel
        files.pop(AGG_GROUP_ENTITY, None)
        if not files:
            raise FileNotFoundError(
                f"{self.folder}: no {AGG_FILE_PREFIX}<entity>.xlsx file (output of py_aggregation_cat).")
        return files

    @staticmethod
    def read_file(path: Path, entity: str) -> pd.DataFrame:
        """Strips d'une entité au format long : sim, entity, peril, loss."""
        print(f"  Reading {path}")
        try:
            df = pd.read_excel(path, sheet_name=AGG_STRIPS_SHEET)
        except ValueError as e:
            raise ValueError(f"{path}: no sheet '{AGG_STRIPS_SHEET}'.") from e
        if AGG_SIM_COL not in df.columns:
            raise ValueError(f"{path}: missing column '{AGG_SIM_COL}'. Found {list(df.columns)}.")
        perils = [c for c in df.columns if c not in (AGG_SIM_COL, AGG_TOTAL_COL)]
        if not perils:
            raise ValueError(f"{path}: no risk column in '{AGG_STRIPS_SHEET}'.")
        if AGG_TOTAL_COL in df.columns:
            total = df[perils].sum(axis=1)
            if not np.allclose(total, df[AGG_TOTAL_COL], rtol=1e-9, atol=1e-6):
                logger.warning("%s: column '%s' differs from the sum of the risks %s.",
                               path, AGG_TOTAL_COL, perils)
        long = (df.melt(id_vars=AGG_SIM_COL, value_vars=perils, var_name="peril", value_name="loss")
                .rename(columns={AGG_SIM_COL: "sim"}))
        long["entity"] = entity
        return long

    def load(self) -> pd.DataFrame:
        out = pd.concat([self.read_file(f, e) for e, f in self.files().items()], ignore_index=True)
        n = out.groupby("entity")["sim"].nunique()
        if n.nunique() != 1:
            raise ValueError(
                f"{self.folder}: the entities do not have the same number of simulations: {n.to_dict()}")
        return out[LONG_COLUMNS]


def to_eur(strips: pd.DataFrame, rates: dict[str, float], name: str = "fx") -> pd.DataFrame:
    """Convertit des strips en devise locale en EUR.

    rates : taux par entité, en EUR pour 1 unité de devise locale (EUR = 1),
            ex. {"XL": 0.85, "FRA": 1}. Clés = entités de py_aggregation_cat.
    name  : nom du jeu de taux, pour les messages d'erreur (ex. "fx_ref").
    """
    missing = sorted(set(strips["entity"]) - set(rates))
    if missing:
        raise ValueError(f"No exchange rate in {name} for: {', '.join(missing)}")
    out = strips.copy()
    out["loss"] = out["loss"] * out["entity"].map(rates)
    return out
