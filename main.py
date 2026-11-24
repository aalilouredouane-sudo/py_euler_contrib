import importlib.util
import subprocess
import sys
from pathlib import Path

# module importable -> spécification pip
REQUIREMENTS = {
    "numpy": "numpy>=1.24",
    "pandas": "pandas>=2.0",
    "openpyxl": "openpyxl>=3.1",
}


def ensure_dependencies() -> None:
    """Installe les packages manquants avant l'import du package euler_contrib."""
    missing = [spec for mod, spec in REQUIREMENTS.items()
               if importlib.util.find_spec(mod) is None]
    if missing:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])


ensure_dependencies()

from euler_contrib import EulerContribPipeline  # noqa: E402

if __name__ == "__main__":
    year_n_1 = "FY25"   # année N-1 : point de départ du bridge
    year_n = "FY26"     # année N : point d'arrivée du bridge

    EulerContribPipeline(
        year_n_1=year_n_1,
        year_n=year_n,
        # dossiers de sortie de py_aggregation_cat (output_dir), un par année :
        # un Gross_MM_reconciliation_<entité>.xlsx par entité, en devise locale
        aggregation_n_1=Path(f"../o_aggregation_cat/{year_n_1}"),
        aggregation_n=Path(f"../o_aggregation_cat/{year_n}"),
        # taux de change vers l'euro par entité (mêmes clés que units / fx_rates de py_aggregation_cat)
        # taux de référence : convertit N-1 et N (impact modèle)
        fx_ref={"BEL": 1, "CHE": 1.07469103, "DEU": 1, "ESP": 1, "FRA": 1,  # Décembre 25
                "IRL": 1, "ITA": 1, "MEX": 0.04735734, "UK": 1.14527859, "XL": 0.85146239},
        # nouveau taux : convertit N une seconde fois (effet change)
        fx_new={"BEL": 1, "CHE": 1.05440742, "DEU": 1, "ESP": 1, "FRA": 1,  # Septembre 26
                "IRL": 1, "ITA": 1, "MEX": 0.04893397, "UK": 1.16959064, "XL": 0.88039794},
        scale=1e6,                              # pertes de py_aggregation_cat en unités -> millions
        output_path=Path(f"waterfalls_{year_n}.xlsx"),
        entity="XL",                            # entité détaillée en plus du groupe ; None = groupe seul
        rp=200,
        attribution="shapley",                  # barres du waterfall : "shapley" (variation du STEC) ou "euler"
        allocation="tvar",                      # contributions Euler : "tvar" (co-TVaR, stable) ou "window"
        half_window=25,                         # mode "window" uniquement : tester 10, 25, 50
        min_abs=0.5,                            # |delta| (EUR m) sous lequel un péril va dans "Other"
    ).run()
