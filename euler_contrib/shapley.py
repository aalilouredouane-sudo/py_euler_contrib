from __future__ import annotations

from math import factorial

import numpy as np
import pandas as pd

from .config import MAX_SHAPLEY_PERILS, RETURN_PERIOD
from .metrics import peril_matrix, rank, stec


def _kth_largest_minus_mean(total: np.ndarray, k: int) -> float:
    """Même valeur que stec(), avec np.partition au lieu d'un tri complet (appelé 2^n fois)."""
    n = len(total)
    return np.partition(total, n - k)[n - k] - total.mean()


def shapley_attribution(prev: pd.DataFrame, curr: pd.DataFrame,
                        rp: int = RETURN_PERIOD) -> pd.Series:
    """Attribution de Shapley de la variation du STEC N-1 -> N, par péril.

    prev, curr : strips N-1 et N au même taux de change (taux de référence).
    v(S) = STEC de la somme où les périls de S ont leur strip N et les autres leur strip N-1,
    donc v(vide) = STEC N-1 et v(tous) = STEC N.
    phi_i = somme sur S ne contenant pas i de |S|! (n - |S| - 1)! / n! x (v(S + i) - v(S)).

    Un péril dont la strip est identique en N-1 et en N vaut 0 et n'entre pas dans
    l'énumération. Contrôle : la somme des phi_i est égale à STEC N - STEC N-1.
    """
    m_prev, m_curr = peril_matrix(prev), peril_matrix(curr)
    perils = m_prev.columns.union(m_curr.columns)   # péril absent une année : strip nulle
    sims = m_prev.index.union(m_curr.index)
    a = m_prev.reindex(index=sims, columns=perils, fill_value=0.0).to_numpy()
    b = m_curr.reindex(index=sims, columns=perils, fill_value=0.0).to_numpy()

    changed = [j for j in range(len(perils)) if not np.array_equal(a[:, j], b[:, j])]
    n = len(changed)
    phi = pd.Series(0.0, index=perils, name="delta_shapley")
    if n == 0:
        return phi
    if n > MAX_SHAPLEY_PERILS:
        raise ValueError(
            f"Shapley: {n} perils changed between N-1 and N, more than MAX_SHAPLEY_PERILS = "
            f"{MAX_SHAPLEY_PERILS} (2^{n} STEC to compute).")

    k = rank(len(sims), rp)
    base = a.sum(axis=1)               # total N-1
    diff = (b - a)[:, changed]         # passage N-1 -> N de chaque péril modifié
    cache: dict[int, float] = {}

    def v(mask: int) -> float:
        """STEC du total où les périls modifiés du masque ont leur strip N."""
        if mask not in cache:
            bits = np.array([(mask >> i) & 1 for i in range(n)], dtype=float)
            cache[mask] = _kth_largest_minus_mean(base + diff @ bits, k)
        return cache[mask]

    weights = [factorial(s) * factorial(n - s - 1) / factorial(n) for s in range(n)]
    for i in range(n):
        bit = 1 << i
        phi.iloc[changed[i]] = sum(
            weights[bin(mask).count("1")] * (v(mask | bit) - v(mask))
            for mask in range(1 << n) if not mask & bit)

    expected = stec(m_curr.sum(axis=1).to_numpy(), rp) - stec(m_prev.sum(axis=1).to_numpy(), rp)
    if not np.isclose(phi.sum(), expected, rtol=1e-9, atol=1e-9):
        raise ValueError(
            f"Shapley check failed: sum(phi) = {phi.sum()} but STEC N - STEC N-1 = {expected}.")
    return phi
