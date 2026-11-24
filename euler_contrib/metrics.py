from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ALLOCATION, HALF_WINDOW, RETURN_PERIOD


def rank(n_sims: int, rp: int = RETURN_PERIOD) -> int:
    """Rang de la perte au 1/rp : k = n / rp (250 sur 50 000 simulations pour le 1/200)."""
    return int(round(n_sims / rp))


def stec(total: np.ndarray, rp: int = RETURN_PERIOD) -> float:
    """STEC = k-ième plus grande valeur de la strip - moyenne."""
    k = rank(len(total), rp)
    return np.sort(total)[::-1][k - 1] - total.mean()


def peril_matrix(strips: pd.DataFrame) -> pd.DataFrame:
    """Matrice simulations x périls : somme sur les entités, scénario par scénario."""
    return strips.pivot_table(index="sim", columns="peril", values="loss",
                              aggfunc="sum", fill_value=0.0)


def peril_contributions(strips: pd.DataFrame, rp: int = RETURN_PERIOD,
                        half_window: int = HALF_WINDOW, allocation: str = ALLOCATION) -> pd.Series:
    """Contribution de chaque péril au STEC (allocation d'Euler).

    c_i = E[X_i | scénarios de queue de S] - E[X_i], avec :
    - allocation="tvar"   : les k plus grands scénarios de S (co-TVaR, stable) ;
    - allocation="window" : k-ième plus grand +/- half_window (co-quantile, plus bruité).
    Remise à l'échelle pour que la somme des c_i soit exactement le STEC de S.
    """
    m = peril_matrix(strips)
    total = m.sum(axis=1).to_numpy()

    k = rank(len(total), rp)
    order = np.argsort(total)[::-1]
    if allocation == "tvar":
        window = order[:k]                                         # les k plus grands scénarios (co-TVaR)
    else:
        window = order[max(k - 1 - half_window, 0): k + half_window]  # k-ième (indice k - 1) +/- half_window

    contrib = m.iloc[window].mean() - m.mean()
    if contrib.sum() == 0:
        raise ValueError("Raw contributions sum to 0: cannot rescale them to the STEC.")
    return contrib * stec(total, rp) / contrib.sum()


def standalone_stec(strips: pd.DataFrame, rp: int = RETURN_PERIOD) -> pd.Series:
    """STEC de chaque péril pris seul."""
    return peril_matrix(strips).apply(lambda col: stec(col.to_numpy(), rp))
