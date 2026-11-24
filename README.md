# py_euler_contrib

Python tool that allocates the group STEC to perils (Euler / co-quantile allocation) and builds the N-1 → N bridge (e.g. FY25 → FY26), split into model impact per peril and FX effect. The two years are parameters: `year_n_1` and `year_n`.

The inputs are the outputs of [py_aggregation_cat](../py_aggregation_cat) for years N-1 and N: the code reads the annual loss strips of each entity and risk (`Local_AAL_strips` sheet of the `Gross_MM_reconciliation_<entity>.xlsx` files), converts them to millions of euros and computes:

- **STEC**: AEP200 − mean, where the AEP200 is the 250th largest annual loss out of 50,000 simulations;
- **Contribution of each peril** to the STEC (Euler allocation): `c_i = E[X_i | tail scenarios of S] − E[X_i]`, where `S` is the sum of all perils and entities. By default (`allocation="tvar"`), the tail scenarios are the 250 largest of `S` (co-TVaR, stable); with `allocation="window"`, they are the 250th largest ± `half_window` (co-quantile, noisier). The `c_i` are rescaled so that they sum exactly to the STEC of `S`;
- **Standalone STEC** of each peril, and its **diversification** (standalone − contribution);
- **Shapley attribution** of the change of the STEC between N-1 and N, per peril, at constant FX rate (model impact): it answers "which peril explains the change of the STEC?". The bars of the waterfall use it by default;
- **Bridge**: change in Euler contribution per peril between N-1 and N at constant FX rate, then the effect of the new FX rate.

The two methods answer different questions: **Shapley explains the change** (waterfall), **Euler explains the structure** of the tail of a given year (contribution vs standalone STEC, diversification).

The results are written to an Excel workbook with, for the group and for one entity, a waterfall table with its chart and the full bridge per peril.

---

## Folder structure

```
py_euler_contrib/
├── main.py                  # entry point: run parameters and pipeline launch
├── requirements.txt         # dependencies (numpy, pandas, openpyxl)
├── README.md
├── tests/
│   └── test_euler_contrib.py  # unit and end-to-end tests on synthetic aggregation_cat outputs (unittest)
└── euler_contrib/           # computation package
    ├── __init__.py          # classes and functions exposed by the package
    ├── config.py            # constants (return period, window, scale, aggregation_cat file layout, labels, colours)
    ├── pipeline.py          # orchestration: parameter checks, loading, group and entity bridges, export
    ├── reader.py            # reading the py_aggregation_cat outputs and converting them to euros
    ├── metrics.py           # STEC, peril matrix, Euler contributions, standalone STEC
    ├── shapley.py           # Shapley attribution of the STEC change per peril
    ├── bridge.py            # N-1 -> N bridge per peril and waterfall table
    └── exporter.py          # Excel output (tables and waterfall charts)
```

### Expected input layout

One output folder of `py_aggregation_cat` per year (its `output_dir`), as written by that tool:

```
o_aggregation_cat/
├── FY25/                                   # year N-1 (aggregation_n_1)
│   ├── Gross_MM_reconciliation_FRA.xlsx    # one file per entity: entity = text after the prefix
│   ├── Gross_MM_reconciliation_XL.xlsx
│   ├── Gross_MM_reconciliation_Group.xlsx  # ignored
│   ├── FRA_summary.csv                     # other outputs: ignored
│   └── ...
└── FY26/                                   # year N (aggregation_n)
    └── ...
```

- **Files read**: `Gross_MM_reconciliation_<entity>.xlsx`. `Gross_MM_reconciliation_Group.xlsx` is ignored: it is already in euros and has no detail per entity, which the FX effect needs. All other files of the folder are ignored.
- **Sheet read**: `Local_AAL_strips`, with a `year` column (simulation 1..50,000), one column per risk (e.g. `CF`, `PW`, `TE`), then `Total`. Each risk is a peril of the bridge. `Total` is not used as a peril: it is only checked against the sum of the risks (a warning is printed if they differ). The `Gross_STEC` sheet is not read.
- **Amounts**: local currency, in units (`py_aggregation_cat` has already applied `units`). They are divided by `scale` (10^6 by default) to get millions, then converted with `fx_ref` / `fx_new`.
- All entities of a year must have the same number of simulations. Simulation `i` must be the same scenario for every entity and risk: strips are summed simulation by simulation. This cannot be checked by the code.
- **Entities and perils are dynamic**: entities come from the file names, perils from the columns of `Local_AAL_strips`. Nothing is declared in the code. Entities may have different risks.
- A peril missing from an entity counts as 0 for that entity. A peril present in only one year counts as 0 in the other year.
- **Exchange rates** are set in `main.py` (no input file), with the same entity codes as `units` / `fx_rates` in `py_aggregation_cat`.

### Input checks

The run stops with an explicit error, rather than producing wrong figures, when:
- an `aggregation_n_1` / `aggregation_n` folder does not exist or contains no `Gross_MM_reconciliation_<entity>.xlsx` file (other than `Group`);
- a file has no `Local_AAL_strips` sheet, no `year` column, or no risk column;
- the entities of a folder do not have the same number of simulations;
- an entity of the strips has no rate in `fx_ref` or `fx_new` (the message lists the missing entities);
- `year_n_1` and `year_n` are equal;
- `entity` is not found in the N-1 or N strips;
- the entity sheet label is `Group` or `Parameters`, or is too long for an Excel sheet name;
- the raw contributions sum to 0, so they cannot be rescaled to the STEC.

A warning is printed, and the run continues, when the `Total` column of `Local_AAL_strips` differs from the sum of the risks.

---

## User guide

1. **Install the dependencies.** Run `pip install -r requirements.txt`. `main.py` also installs any missing packages automatically at startup.
2. **Set the parameters** in [main.py](main.py):

   | Parameter | Purpose |
   |---|---|
   | `year_n_1` | Label of year N-1, e.g. `"FY25"`. Set at the top of the `__main__` block. Used in the column names, the waterfall steps and, in `main.py`, the input folder. |
   | `year_n` | Label of year N, e.g. `"FY26"`. Set at the top of the `__main__` block. Also used in the output file name (`waterfalls_<year_n>.xlsx`). |
   | `aggregation_n_1` | Output folder of `py_aggregation_cat` for N-1. In `main.py`: `../o_aggregation_cat/<year_n_1>`. |
   | `aggregation_n` | Output folder of `py_aggregation_cat` for N. In `main.py`: `../o_aggregation_cat/<year_n>`. |
   | `output_path` | Path of the Excel file to create. If it already exists, it is overwritten. |
   | `entity` | Entity detailed in addition to the group, as in the file name, e.g. `"XL"` (sheets `XL_waterfall`, `XL_detail`). `None` for the group only. |
   | `fx_ref` | Reference exchange rates to euro per entity, e.g. `{"XL": 0.85146239, "FRA": 1}`: value in EUR of 1 unit of local currency (EUR = 1). Keys are the entity codes of `py_aggregation_cat` (same as its `fx_rates`). Used to convert N-1 and N for the model impact. Every entity of the strips must have a rate. |
   | `fx_new` | New exchange rates to euro per entity, same format. Used to convert N a second time for the FX effect. |
   | `rp` | Return period of the STEC, 200 by default. |
   | `attribution` | Bars of the waterfall: `"shapley"` (default) = Shapley attribution of STEC N − STEC N-1 (`delta_shapley`); `"euler"` = change of the Euler contributions (`delta_model`). In both cases the bars sum to STEC N − STEC N-1 at the reference rate, and the `FX` bar is the same. |
   | `allocation` | Tail scenarios used for the Euler contributions: `"tvar"` (default) = the 250 largest scenarios of the total (co-TVaR, stable); `"window"` = the 250th largest ± `half_window` (co-quantile, noisier). |
   | `half_window` | `"window"` mode only: number of scenarios taken on each side of the 1/200 scenario, 25 by default. |
   | `min_abs` | Perils whose model impact is below this value in absolute terms (EUR m) are grouped in `Other` in the waterfall, 0.5 by default. |
   | `scale` | Divisor applied to the losses of `py_aggregation_cat` (in units) to get millions: `1e6` by default. |

3. **Run the computation**: `python main.py`.
4. **Collect the output** at `output_path`:

   | Sheet | Content |
   |---|---|
   | `Group_waterfall` | Waterfall table: `Step`, `Value`, `Base`, `Increase`, `Decrease`, `Total`, rounded to 0.1. Rows: `<year_n_1>`, one row per peril (largest increase first, `delta_shapley` or `delta_model` depending on `attribution`), `Other`, `FX`, `<year_n>`. A stacked column chart (invisible `Base`) is placed in `H2`. |
   | `Group_detail` | Full bridge, one row per peril, rounded to 0.01: `contrib_<year_n_1>`, `contrib_<year_n>`, `delta_model`, `delta_fx`, `delta_shapley` (only if `attribution="shapley"`), `standalone_<year_n_1>`, `divers_<year_n_1>`, `standalone_<year_n>`, `divers_<year_n>` (e.g. `contrib_FY25`). |
   | `<entity>_waterfall`, `<entity>_detail` | Same, for the strips of `entity` only. Not created if `entity=None`. |
   | `Parameters` | Run parameters: date, years, folders, entity, exchange rates (`fx_ref`, `fx_new`), `scale`, `rp`, `half_window`, `allocation`, `attribution`, `min_abs`. |

   In Excel 2016+, a native Waterfall chart can also be built: select `Step` and `Value`, insert a Waterfall chart, then use "Set as total" on the first and last steps (N-1 and N).

5. **Check the figures** before presenting:
   - the STEC per entity × risk must match the `Gross_STEC` sheet of `py_aggregation_cat` (divided by `scale`, in local currency), and the group STEC must match the reference Excel file (see [Checks in Python](#checks-in-python));
   - in `"window"` mode, test the stability of the contributions with `half_window` = 10, 25 and 50.
   - a peril whose strip is identical between N-1 and N can still see its Euler contribution move: it is a reallocation of the group tail, not a change of risk. Its Shapley attribution is exactly 0, which is why the waterfall uses Shapley by default.
   - with Shapley, unchanged perils are 0, so they fall below `min_abs` and do not get a bar (they are visible at 0 in `delta_shapley` of the `_detail` sheet).

6. **Run the tests** (optional, no extra dependency): from `py_euler_contrib/`, run `python -m unittest discover tests -v`. They write synthetic `Gross_MM_reconciliation_<entity>.xlsx` files in a temporary folder and check:
   - `stec` (k-th largest value − mean), and that the contributions add up to the group STEC; the `"tvar"` allocation uses the `k` largest scenarios;
   - Shapley: the attributions sum to STEC N − STEC N-1, unchanged perils are 0, the two-peril formula, a single changed peril takes all the change, new and removed perils, and the waterfall keeps the same `FX` bar and end value as with Euler;
   - that two proportional perils get proportional contributions;
   - the bridge: zero deltas when nothing changes, an FX effect of −10 % when all rates fall by 10 %, the diversification columns;
   - the exchange rates: conversion per entity, error when an entity has no rate, no FX effect when `fx_new` = `fx_ref`;
   - the waterfall: grouping into `Other`, `Base` / `Decrease` of a negative step, and a last step equal to the N STEC at the new rate, year labels taken from the parameters, perils present in only one year;
   - reading: entity taken from the file name, `Group` file and `Total` column ignored, warning when `Total` differs from the sum of the risks, division by `scale`, and the input errors;
   - the full run: sheet names, one chart per `_waterfall` sheet, the `Parameters` sheet, group-only mode, a new entity with its own perils picked up without any code change.

### Checks in Python

```python
from pathlib import Path
from euler_contrib import EulerContribPipeline, stec

p = EulerContribPipeline("FY25", "FY26", Path("../o_aggregation_cat/FY25"), Path("../o_aggregation_cat/FY26"),
                         fx_ref={"XL": 0.85146239, "FRA": 1},
                         fx_new={"XL": 0.88039794, "FRA": 1},
                         output_path=Path("waterfalls_FY26.xlsx"))
prev, curr, curr_fx = p.load()                                  # N-1, N, N at new rate
curr.groupby(["entity", "peril"]).loss.apply(lambda s: stec(s.to_numpy()))  # STEC per entity x risk (EUR m)
stec(curr.groupby("sim").loss.sum().to_numpy())                              # group STEC
```

---

## Code description

### `main.py`
Entry point. It checks that `numpy`, `pandas` and `openpyxl` are installed and installs any that are missing. It then builds an `EulerContribPipeline` with the run parameters and calls `.run()`.

### `euler_contrib/config.py`
Global constants:
- `RETURN_PERIOD = 200`, `HALF_WINDOW = 25`, `ALLOCATION = "tvar"`, `ATTRIBUTION = "shapley"`, `MIN_ABS = 0.5`: default values of `rp`, `half_window`, `allocation`, `attribution` and `min_abs`. `ALLOCATIONS` and `ATTRIBUTIONS` list the accepted values.
- `MAX_SHAPLEY_PERILS = 16`: maximum number of perils that change between N-1 and N (Shapley computes 2^n STEC; about 1 s for 12 perils at 50,000 simulations).
- `SCALE = 1e6`: default value of `scale`.
- `AGG_FILE_PREFIX`, `AGG_GROUP_ENTITY`, `AGG_STRIPS_SHEET`, `AGG_SIM_COL`, `AGG_TOTAL_COL`: layout of the `py_aggregation_cat` outputs (`Gross_MM_reconciliation_`, `Group`, `Local_AAL_strips`, `year`, `Total`).
- `OTHER_STEP`, `FX_STEP`: names of the `Other` and `FX` waterfall steps.
- `LONG_COLUMNS`: columns of the long format used internally (`sim`, `entity`, `peril`, `loss`).
- Labels `Group` and `Parameters`, and the colours of the waterfall chart.

### `euler_contrib/pipeline.py` — `EulerContribPipeline`
Orchestrates the full run:
- `_check_parameters` runs at construction: `year_n_1` and `year_n` must differ; `allocation` must be `"tvar"` or `"window"`; `attribution` must be `"shapley"` or `"euler"`; the entity sheet label must not be `Group` or `Parameters` and must fit in an Excel sheet name.
- `load()` reads the N-1 and N outputs of `py_aggregation_cat`, divides the losses by `scale` and returns three sets of strips in euros: N-1 at the `fx_ref` rate, N at the `fx_ref` rate (model impact) and N at the `fx_new` rate (FX effect).
- `run()`:
  1. builds the group bridge from the strips of all entities;
  2. if `entity` is set, checks that it exists, then builds its bridge from its strips only;
  3. writes the workbook with `ExcelExporter` and returns the bridges, by sheet label.

### `euler_contrib/reader.py` — `AggregationReader`, `to_eur`
- `AggregationReader.files` lists the `Gross_MM_reconciliation_<entity>.xlsx` files of a folder in alphabetical order, without the `Group` file and Excel lock files (`~$…`).
- `AggregationReader.read_file` reads the `Local_AAL_strips` sheet, checks `Total` against the sum of the risks, and puts the risks in long format (`sim`, `entity`, `peril`, `loss`).
- `AggregationReader.load` concatenates all entities and checks that they have the same number of simulations.
- `to_eur` multiplies each loss by the rate of its entity in a rates dictionary (`fx_ref` or `fx_new`), and raises an error listing the entities without a rate.

### `euler_contrib/metrics.py`
- `rank` gives the rank of the 1/rp loss: `k = round(n / rp)`, i.e. 250 for 50,000 simulations and RP 200.
- `stec` returns the k-th largest value of a strip minus its mean.
- `peril_matrix` builds the simulations × perils matrix, summing the entities simulation by simulation.
- `peril_contributions` sorts the simulations by total loss and takes the `k` largest (`allocation="tvar"`), or the scenarios of rank `k − half_window` to `k + half_window − 1` (`allocation="window"`, the 1/200 scenario is at index `k − 1`). The raw contribution of a peril is its mean over these scenarios minus its overall mean. The contributions are then multiplied by `STEC / sum of contributions`, so that they add up to the STEC.
- `standalone_stec` returns the STEC of each peril taken alone.

### `euler_contrib/shapley.py`
- `shapley_attribution(prev, curr)` takes the N-1 and N strips at the reference rate and builds their simulations × perils matrices (a peril missing one year has a zero strip).
- `v(S)` is the STEC of the total where the perils of `S` have their N strip and the others their N-1 strip, so `v(∅)` = STEC N-1 and `v(all)` = STEC N.
- `φ_i = Σ over S without i of |S|! (n − |S| − 1)! / n! × (v(S ∪ {i}) − v(S))`, computed over all subsets with bit masks; each `v(S)` is computed once (cache).
- A peril whose strip is identical in N-1 and N gets 0 and is left out of the enumeration.
- Check: an error is raised if `Σ φ_i` differs from STEC N − STEC N-1. An error is also raised if more than `MAX_SHAPLEY_PERILS` perils changed.

### `euler_contrib/bridge.py`
- `bridge` computes the contributions for the three sets of strips and returns, per peril: `contrib_<N-1>`, `contrib_<N>`, `delta_model = contrib_<N> − contrib_<N-1>`, `delta_fx = contribution of N at the new rate − contrib_<N>`, then the standalone STEC and the diversification for N-1 and N. The year labels `year_n_1` and `year_n` are passed as arguments. If `attribution="shapley"`, it adds `delta_shapley` (see `shapley.py`). Rows are sorted by decreasing `delta_model`. A peril present in only one year counts as 0 in the other.
- `waterfall_table` turns a bridge into the steps of the waterfall: `<year_n_1>`, one step per peril with `|delta| ≥ min_abs` (`delta_shapley` or `delta_model` depending on `attribution`, sorted by decreasing value), `Other` (sum of the smaller ones, omitted if 0), `FX` (`Σ delta_fx`, the same in both modes), then `<year_n> = <year_n_1> + Σ delta + Σ delta_fx`. For each step, `Base` is the invisible part of the stacked column and `Increase` / `Decrease` / `Total` the visible part.

### `euler_contrib/exporter.py` — `ExcelExporter`
Writes, for each bridge, the `<name>_waterfall` and `<name>_detail` sheets, then the `Parameters` sheet. It then reopens the workbook with `openpyxl` and adds to each `_waterfall` sheet a stacked column chart: `Base` without fill, increases in orange, decreases in blue, totals in dark blue.
