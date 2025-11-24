import unittest

from backend.dcf_engine_v2 import (
    run_dcf_v2,
    DCFComputationError,
    compute_normalized_base_fcff,
    compute_fcf_cagr_5y,
    build_growth_path,
)


class DcfV2Tests(unittest.TestCase):
    def test_run_dcf_v2_outputs_structure(self):
        metrics = {
            "revenueLast": 1_000_000_000,
            "revenueCAGR5Y": 0.08,
            "normalizedTaxRate": 0.21,
            "netDebt": 200_000_000,
            "sharesOutstanding": 1_000_000_000,
            "baseYear": 2023,
            "baseYearFcffNormalized": 140_000_000,
            "fcfSeries": [
                {"label": "2023", "value": 160_000_000},
                {"label": "2022", "value": 150_000_000},
                {"label": "2021", "value": 140_000_000},
            ],
            "roicHistory": [{"year": 2023, "roic": 0.18}, {"year": 2022, "roic": 0.16}],
            "nopatHistory": [
                {"year": 2023, "nopat": 180_000_000},
                {"year": 2022, "nopat": 170_000_000},
            ],
        }
        cost_of_capital = {"wacc": 0.09, "riskFreeRate": 0.04, "marketRiskPremium": 0.055}

        result = run_dcf_v2(metrics, cost_of_capital, horizon_years=5, g_terminal=0.02)

        self.assertIsNotNone(result)
        self.assertIn("fcffForecast", result)
        self.assertEqual(len(result["fcffForecast"]), 5)
        self.assertIn("terminalValue", result)
        self.assertIn("enterpriseValue", result)
        self.assertIn("equityValue", result)
        self.assertIn("impliedSharePrice", result)
        self.assertIn("baseFcff", result)
        self.assertIn("baseFcffNormalized", result["settings"])
        self.assertIn("archetype", result["settings"])

    def test_run_dcf_v2_requires_base_fcf(self):
        metrics = {
            "revenueLast": 0.0,
            "normalizedTaxRate": 0.21,
            "netDebt": 0.0,
            "sharesOutstanding": 1_000_000_000,
            "baseYear": 2023,
            "fcfSeries": [],
        }
        cost_of_capital = {"wacc": 0.09}

        with self.assertRaises(DCFComputationError):
            run_dcf_v2(metrics, cost_of_capital)

    def test_compute_normalized_base_fcff_drops_outliers(self):
        values = [200_000_000, 195_000_000, 205_000_000, 800_000_000]
        normalized = compute_normalized_base_fcff(values, None)
        self.assertTrue(195_000_000 <= normalized <= 205_000_000)

    def test_compute_fcf_cagr(self):
        values = [200.0, 180.0, 150.0, 130.0]
        cagr = compute_fcf_cagr_5y(values)
        self.assertIsNotNone(cagr)
        self.assertGreater(cagr, 0)

    def test_build_growth_path_phases(self):
        growth_path, g_short, g_mid, g_terminal = build_growth_path(
            horizon_years=10,
            g_terminal=0.03,
            fcf_cagr=0.08,
            revenue_cagr=0.05,
            roic_growth=0.06,
        )
        self.assertEqual(len(growth_path), 10)
        self.assertAlmostEqual(growth_path[0], g_short)
        self.assertAlmostEqual(growth_path[-1], g_terminal, places=3)
        self.assertGreaterEqual(growth_path[0], growth_path[-1])

    def test_scenario_presets_adjust_assumptions(self):
        mature_metrics = {
            "revenueLast": 1_000_000_000,
            "revenueCAGR5Y": 0.06,
            "normalizedTaxRate": 0.21,
            "netDebt": 100_000_000,
            "sharesOutstanding": 500_000_000,
            "baseYear": 2023,
            "baseYearFcffNormalized": 120_000_000,
            "fcfSeries": [
                {"label": "2023", "value": 130_000_000},
                {"label": "2022", "value": 120_000_000},
                {"label": "2021", "value": 110_000_000},
            ],
            "roicHistory": [{"year": 2023, "roic": 0.18}, {"year": 2022, "roic": 0.16}],
            "nopatHistory": [
                {"year": 2023, "nopat": 150_000_000},
                {"year": 2022, "nopat": 140_000_000},
            ],
        }
        hyper_metrics = {
            "revenueLast": 10_000_000_000,
            "revenueCAGR5Y": 0.35,
            "normalizedTaxRate": 0.18,
            "netDebt": -500_000_000,
            "sharesOutstanding": 2_000_000_000,
            "baseYear": 2023,
            "baseYearFcffNormalized": 900_000_000,
            "fcfSeries": [
                {"label": "2023", "value": 950_000_000},
                {"label": "2022", "value": 800_000_000},
                {"label": "2021", "value": 600_000_000},
            ],
            "roicHistory": [{"year": 2023, "roic": 0.32}, {"year": 2022, "roic": 0.28}],
            "nopatHistory": [
                {"year": 2023, "nopat": 1_100_000_000},
                {"year": 2022, "nopat": 900_000_000},
            ],
        }
        cost_of_capital = {"wacc": 0.09}
        mature_base = run_dcf_v2(mature_metrics, cost_of_capital, horizon_years=10, scenario="base")
        hyper_base = run_dcf_v2(hyper_metrics, cost_of_capital, horizon_years=10, scenario="base")
        conservative = run_dcf_v2(mature_metrics, cost_of_capital, horizon_years=10, scenario="conservative")
        optimistic = run_dcf_v2(hyper_metrics, cost_of_capital, horizon_years=10, scenario="optimistic")

        self.assertEqual(mature_base["settings"].get("archetype"), "mature")
        self.assertEqual(hyper_base["settings"].get("archetype"), "hypergrowth")
        self.assertGreaterEqual(conservative["settings"]["wacc"], mature_base["settings"]["wacc"])
        self.assertLessEqual(optimistic["settings"]["wacc"], hyper_base["settings"]["wacc"])
        self.assertGreaterEqual(optimistic["settings"].get("horizonYears"), hyper_base["settings"].get("horizonYears"))
        self.assertLessEqual(conservative["settings"]["gTerminal"], mature_base["settings"]["gTerminal"])
        self.assertGreaterEqual(hyper_base["settings"]["gTerminal"], mature_base["settings"]["gTerminal"])


if __name__ == "__main__":
    unittest.main()
