"""Tests de euler_contrib sur des strips synthétiques, au format des sorties de py_aggregation_cat.

Lancer depuis py_euler_contrib/ :  python -m unittest discover tests -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from euler_contrib import (AggregationReader, EulerContribPipeline, bridge,  # noqa: E402
                           peril_contributions, stec, to_eur, waterfall_table)

N_SIMS = 2000          # rp = 200 -> rang k = 10
PERILS = ["Aviation", "Cyber", "Marine", "Terror"]
ENTITIES = ["FRA", "XL"]
FX_REF = {"FRA": 1.0, "XL": 0.9}
FX_NEW = {"FRA": 1.0, "XL": 0.85}
UNIT = 1e6             # les sorties de py_aggregation_cat sont en unités ; scale = 1e6 -> millions


def make_wide(seed: int, scale: float = 1.0, n: int = N_SIMS) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"SIM": np.arange(1, n + 1)})
    for i, p in enumerate(PERILS):
        df[p] = rng.lognormal(i, 1.0 + 0.2 * i, n) * scale
    return df


def to_long(wide: pd.DataFrame, entity: str) -> pd.DataFrame:
    long = wide.melt(id_vars="SIM", var_name="peril", value_name="loss").rename(columns={"SIM": "sim"})
    long["entity"] = entity
    return long[["sim", "entity", "peril", "loss"]]


def write_agg(folder: Path, entity: str, wide: pd.DataFrame, total_offset: float = 0.0) -> Path:
    """Écrit Gross_MM_reconciliation_<entité>.xlsx comme py_aggregation_cat (montants en unités)."""
    folder.mkdir(parents=True, exist_ok=True)
    strips = wide.rename(columns={"SIM": "year"})
    perils = [c for c in strips.columns if c != "year"]
    strips[perils] = strips[perils] * UNIT
    strips["Total"] = strips[perils].sum(axis=1) + total_offset
    path = folder / f"Gross_MM_reconciliation_{entity}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        pd.DataFrame({"x": [0.0]}).to_excel(w, sheet_name="Gross_STEC")
        strips.to_excel(w, sheet_name="Local_AAL_strips", index=False)
    return path


def write_inputs(root: Path) -> None:
    """root/FY25, root/FY26 : un Gross_MM_reconciliation_<entité>.xlsx par entité, plus un fichier Group."""
    for fy, scale in [("FY25", 1.0), ("FY26", 1.1)]:
        for j, ent in enumerate(ENTITIES):
            write_agg(root / fy, ent, make_wide(seed=10 * j + int(fy[-1]), scale=scale))
        write_agg(root / fy, "Group", make_wide(seed=99, scale=1000.0))  # doit être ignoré


class TestMetrics(unittest.TestCase):
    def test_stec_is_kth_largest_minus_mean(self):
        x = np.arange(1, 2001, dtype=float)        # k = 10 -> 10e plus grande = 1991
        self.assertAlmostEqual(stec(x), 1991 - x.mean())

    def test_contributions_sum_to_group_stec(self):
        strips = pd.concat([to_long(make_wide(1), "A"), to_long(make_wide(2), "B")])
        c = peril_contributions(strips, half_window=5)
        total = strips.groupby("sim")["loss"].sum().to_numpy()
        self.assertAlmostEqual(c.sum(), stec(total), places=6)
        self.assertEqual(sorted(c.index), PERILS)

    def test_proportional_perils_get_proportional_contributions(self):
        # Cyber = 3 x Aviation scénario par scénario -> contribution 3 fois plus grande
        base = np.random.default_rng(0).lognormal(0, 1, N_SIMS)
        wide = pd.DataFrame({"SIM": np.arange(1, N_SIMS + 1), "Aviation": base, "Cyber": 3 * base})
        c = peril_contributions(to_long(wide, "A"), half_window=5)
        self.assertAlmostEqual(c["Cyber"] / c["Aviation"], 3.0, places=6)


class TestBridge(unittest.TestCase):
    def setUp(self):
        self.fy25 = to_long(make_wide(1), "A")
        self.fy26 = to_long(make_wide(2, scale=1.2), "A")
        self.fy26fx = self.fy26.assign(loss=self.fy26["loss"] * 0.9)

    def test_no_change_gives_zero_deltas(self):
        br = bridge(self.fy25, self.fy25, self.fy25, "FY25", "FY26", half_window=5)
        self.assertTrue(np.allclose(br["delta_model"], 0))
        self.assertTrue(np.allclose(br["delta_fx"], 0))

    def test_fx_effect_is_linear(self):
        # tout le portefeuille x 0.9 -> effet change = -10 % du STEC FY26
        br = bridge(self.fy25, self.fy26, self.fy26fx, "FY25", "FY26", half_window=5)
        self.assertAlmostEqual(br["delta_fx"].sum(), -0.1 * br["contrib_FY26"].sum(), places=6)

    def test_diversification_columns(self):
        br = bridge(self.fy25, self.fy26, self.fy26fx, "FY25", "FY26", half_window=5)
        self.assertTrue(np.allclose(br["divers_FY25"], br["standalone_FY25"] - br["contrib_FY25"]))
        self.assertTrue(list(br["delta_model"]) == sorted(br["delta_model"], reverse=True))

    def test_waterfall_ends_on_fy26_at_new_rate(self):
        br = bridge(self.fy25, self.fy26, self.fy26fx, "FY25", "FY26", half_window=5)
        wf = waterfall_table(br, "FY25", "FY26")
        self.assertEqual(wf["Step"].iloc[0], "FY25")
        self.assertEqual(list(wf["Step"].iloc[-2:]), ["FX", "FY26"])
        fy26_at_new_rate = peril_contributions(self.fy26fx, half_window=5).sum()
        self.assertAlmostEqual(wf["Value"].iloc[-1], fy26_at_new_rate, places=6)

    def test_year_labels_are_parameters(self):
        br = bridge(self.fy25, self.fy26, self.fy26fx, "FY26", "FY27", half_window=5)
        for col in ["contrib_FY26", "contrib_FY27", "standalone_FY27", "divers_FY26"]:
            self.assertIn(col, br.columns)
        self.assertFalse(any("FY25" in c for c in br.columns))
        wf = waterfall_table(br, "FY26", "FY27")
        self.assertEqual((wf["Step"].iloc[0], wf["Step"].iloc[-1]), ("FY26", "FY27"))

    def test_peril_only_in_one_year(self):
        # nouveau péril en N, péril disparu en N : compté 0 l'autre année, waterfall toujours cohérent
        prev = self.fy25[self.fy25["peril"] != "Cyber"]
        curr = self.fy26[self.fy26["peril"] != "Marine"]
        br = bridge(prev, curr, curr, "FY25", "FY26", half_window=5)
        self.assertEqual(br.loc["Cyber", "contrib_FY25"], 0.0)
        self.assertEqual(br.loc["Marine", "contrib_FY26"], 0.0)
        wf = waterfall_table(br, "FY25", "FY26")
        self.assertAlmostEqual(wf["Value"].iloc[-1], peril_contributions(curr, half_window=5).sum(), places=6)

    def test_small_deltas_grouped_in_other(self):
        br = pd.DataFrame({"contrib_FY25": [10.0, 5.0, 1.0], "delta_model": [2.0, 0.2, -0.1],
                           "delta_fx": [0.0, 0.0, -1.0]}, index=["Big", "Small1", "Small2"])
        wf = waterfall_table(br, "FY25", "FY26", min_abs=0.5).set_index("Step")
        self.assertEqual(list(wf.index), ["FY25", "Big", "Other", "FX", "FY26"])
        self.assertAlmostEqual(wf.loc["Other", "Value"], 0.1)
        self.assertAlmostEqual(wf.loc["FY26", "Total"], 16.0 + 2.1 - 1.0)
        # barre de baisse : Base = niveau après la baisse
        self.assertAlmostEqual(wf.loc["FX", "Base"], 17.1)
        self.assertAlmostEqual(wf.loc["FX", "Decrease"], 1.0)


class TestReader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_aggregation_outputs(self):
        wide = make_wide(1)
        write_agg(self.root, "XL", wide)
        write_agg(self.root, "Group", make_wide(2))           # ignoré
        (self.root / "XL_summary.csv").write_text("x\n1\n")   # autres sorties ignorées
        strips = AggregationReader(self.root).load()
        self.assertEqual(set(strips["entity"]), {"XL"})
        self.assertEqual(sorted(strips["peril"].unique()), PERILS)   # Total exclu
        expected = to_long(wide, "XL").assign(loss=lambda d: d["loss"] * UNIT)
        got = strips.sort_values(["peril", "sim"]).reset_index(drop=True)
        expected = expected.sort_values(["peril", "sim"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(got, expected, check_dtype=False)

    def test_total_mismatch_warns(self):
        write_agg(self.root, "XL", make_wide(1), total_offset=1.0)
        with self.assertLogs("euler_contrib.reader", level="WARNING"):
            AggregationReader(self.root).load()

    def test_missing_strips_sheet_raises(self):
        pd.DataFrame({"x": [1]}).to_excel(self.root / "Gross_MM_reconciliation_XL.xlsx", sheet_name="Gross_STEC")
        with self.assertRaisesRegex(ValueError, "Local_AAL_strips"):
            AggregationReader(self.root).load()

    def test_different_number_of_simulations_raises(self):
        write_agg(self.root, "FRA", make_wide(1))
        write_agg(self.root, "XL", make_wide(2, n=1000))
        with self.assertRaisesRegex(ValueError, "same number of simulations"):
            AggregationReader(self.root).load()

    def test_missing_folder_or_files_raises(self):
        with self.assertRaises(FileNotFoundError):
            AggregationReader(self.root / "absent").load()
        write_agg(self.root, "Group", make_wide(1))   # seul le fichier Group : rien à lire
        with self.assertRaises(FileNotFoundError):
            AggregationReader(self.root).load()

    def test_fx_conversion_and_missing_rate(self):
        strips = pd.concat([to_long(make_wide(1), "A"), to_long(make_wide(2), "B")])
        out = to_eur(strips, {"A": 0.5, "B": 2.0})
        self.assertTrue(np.allclose(out["loss"], strips["loss"] * strips["entity"].map({"A": 0.5, "B": 2.0})))
        with self.assertRaisesRegex(ValueError, "No exchange rate in fx_new for: B"):
            to_eur(strips, {"A": 0.5}, "fx_new")


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        write_inputs(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def pipeline(self, **kw) -> EulerContribPipeline:
        kw = {"fx_ref": FX_REF, "fx_new": FX_NEW, **kw}
        return EulerContribPipeline("FY25", "FY26", self.root / "FY25", self.root / "FY26",
                                    output_path=self.root / "out" / "waterfalls.xlsx",
                                    half_window=5, **kw)

    def test_end_to_end(self):
        blocks = self.pipeline(entity="XL").run()
        self.assertEqual(list(blocks), ["Group", "XL"])

        wb = load_workbook(self.root / "out" / "waterfalls.xlsx")
        self.assertEqual(wb.sheetnames, ["Group_waterfall", "Group_detail",
                                         "XL_waterfall", "XL_detail", "Parameters"])
        self.assertEqual(len(wb["Group_waterfall"]._charts), 1)
        self.assertEqual(len(wb["XL_waterfall"]._charts), 1)

        # le waterfall groupe finit sur le STEC groupe FY26 au nouveau taux
        fy25, fy26, fy26fx = self.pipeline().load()
        expected = stec(fy26fx.groupby("sim")["loss"].sum().to_numpy())
        wf = pd.read_excel(self.root / "out" / "waterfalls.xlsx", sheet_name="Group_waterfall")
        self.assertAlmostEqual(wf["Value"].iloc[-1], round(expected, 1), places=1)

        # scale : pertes en millions, puis taux de change
        xl = fy25[(fy25["entity"] == "XL") & (fy25["peril"] == "Cyber")].sort_values("sim")
        raw = make_wide(seed=10 * 1 + 5)["Cyber"].to_numpy()
        self.assertTrue(np.allclose(xl["loss"].to_numpy(), raw * FX_REF["XL"]))

        params = pd.read_excel(self.root / "out" / "waterfalls.xlsx", sheet_name="Parameters")
        self.assertEqual(params.set_index("Parameter").loc["half_window", "Value"], "5")
        self.assertEqual(params.set_index("Parameter").loc["year_n", "Value"], "FY26")

    def test_entities_and_perils_are_read_from_files(self):
        # une 3e entité avec ses propres périls : rien à déclarer, elle entre dans le groupe
        for fy in ["FY25", "FY26"]:
            write_agg(self.root / fy, "DEU", make_wide(7)[["SIM", "Aviation"]].assign(Flood=1.0))
        blocks = self.pipeline(entity="DEU", fx_ref={**FX_REF, "DEU": 1.0},
                               fx_new={**FX_NEW, "DEU": 1.0}).run()
        self.assertEqual(sorted(blocks["Group"].index), sorted(PERILS + ["Flood"]))
        self.assertEqual(sorted(blocks["DEU"].index), ["Aviation", "Flood"])

    def test_same_years_raises(self):
        with self.assertRaisesRegex(ValueError, "must differ"):
            EulerContribPipeline("FY26", "FY26", self.root / "FY25", self.root / "FY26",
                                 FX_REF, FX_NEW, self.root / "out.xlsx")

    def test_missing_rate_raises(self):
        with self.assertRaisesRegex(ValueError, "No exchange rate in fx_new for: XL"):
            self.pipeline(fx_new={"FRA": 1.0}).run()

    def test_fx_effect_uses_main_rates(self):
        # mêmes taux en référence et en nouveau -> effet change nul
        blocks = self.pipeline(fx_new=FX_REF).run()
        self.assertTrue(np.allclose(blocks["Group"]["delta_fx"], 0))

    def test_group_only(self):
        blocks = self.pipeline(entity=None).run()
        self.assertEqual(list(blocks), ["Group"])

    def test_unknown_entity_raises(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            self.pipeline(entity="ABS").run()

    def test_bad_entity_label_raises(self):
        with self.assertRaisesRegex(ValueError, "clash"):
            self.pipeline(entity="Group")
        with self.assertRaisesRegex(ValueError, "too long"):
            self.pipeline(entity="x" * 30)


if __name__ == "__main__":
    unittest.main()
