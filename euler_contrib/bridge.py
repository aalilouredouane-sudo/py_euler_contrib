from __future__ import annotations

import pandas as pd

from .config import FX_STEP, HALF_WINDOW, MIN_ABS, OTHER_STEP, RETURN_PERIOD
from .metrics import peril_contributions, standalone_stec

WATERFALL_COLUMNS = ["Step", "Value", "Base", "Increase", "Decrease", "Total"]


def bridge(prev: pd.DataFrame, curr_fx_ref: pd.DataFrame, curr_fx_new: pd.DataFrame,
           year_n_1: str, year_n: str,
           rp: int = RETURN_PERIOD, half_window: int = HALF_WINDOW) -> pd.DataFrame:
    """Bridge N-1 -> N par péril :
    - prev        : strips N-1 au taux de référence
    - curr_fx_ref : strips N au taux de référence (impact modèle)
    - curr_fx_new : strips N au nouveau taux (effet change)
    year_n_1, year_n : libellés des années (ex. "FY25", "FY26"), utilisés dans les noms de colonnes.
    """
    c_prev = peril_contributions(prev, rp, half_window)
    c_curr = peril_contributions(curr_fx_ref, rp, half_window)
    c_curr_fx = peril_contributions(curr_fx_new, rp, half_window)

    prev_col, curr_col = f"contrib_{year_n_1}", f"contrib_{year_n}"
    out = pd.DataFrame({prev_col: c_prev, curr_col: c_curr}).fillna(0.0)
    out["delta_model"] = out[curr_col] - out[prev_col]
    out["delta_fx"] = c_curr_fx.reindex(out.index).fillna(0.0) - out[curr_col]

    # STEC standalone par péril et diversification par péril (= standalone - contribution)
    for name, s in [(year_n_1, prev), (year_n, curr_fx_ref)]:
        out[f"standalone_{name}"] = standalone_stec(s, rp)
        out[f"divers_{name}"] = out[f"standalone_{name}"] - out[f"contrib_{name}"]
    return out.sort_values("delta_model", ascending=False)


def waterfall_table(br: pd.DataFrame, year_n_1: str, year_n: str,
                    min_abs: float = MIN_ABS) -> pd.DataFrame:
    """Tableau du waterfall : N-1 -> une barre par péril -> Other -> FX -> N.

    Colonnes Base / Increase / Decrease / Total pour un histogramme empilé (Base invisible).
    Les périls avec |delta_model| < min_abs sont regroupés dans "Other".
    """
    start = br[f"contrib_{year_n_1}"].sum()
    steps = [(year_n_1, start, True)]
    steps += [(p, v, False) for p, v in br["delta_model"].items() if abs(v) >= min_abs]
    small = br.loc[br["delta_model"].abs() < min_abs, "delta_model"].sum()
    if abs(small) > 1e-9:
        steps.append((OTHER_STEP, small, False))
    steps.append((FX_STEP, br["delta_fx"].sum(), False))
    steps.append((year_n, start + br["delta_model"].sum() + br["delta_fx"].sum(), True))

    rows, cum = [], 0.0
    for name, v, is_total in steps:
        if is_total:
            rows.append((name, v, 0.0, 0.0, 0.0, v))
            cum = v
        else:
            new = cum + v
            rows.append((name, v, min(cum, new), max(v, 0.0), max(-v, 0.0), 0.0))
            cum = new
    return pd.DataFrame(rows, columns=WATERFALL_COLUMNS)
