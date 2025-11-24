import unittest

import pandas as pd

from backend import main as backend_main


def _financials_template():
    return pd.DataFrame(
        {
            "2023-12-31": {
                "Income Tax Expense": 210,
                "Income Before Tax": 1000,
                "Ebit": 300,
                "Depreciation": 70,
            },
            "2022-12-31": {
                "Income Tax Expense": 180,
                "Income Before Tax": 900,
                "Ebit": 270,
                "Depreciation": 65,
            },
            "2021-12-31": {
                "Income Tax Expense": 150,
                "Income Before Tax": 800,
                "Ebit": 250,
                "Depreciation": 60,
            },
        }
    )


def _balance_sheet_template():
    return pd.DataFrame(
        {
            "2023-12-31": {
                "Property Plant Equipment": 1000,
                "Total Current Assets": 600,
                "Total Current Liabilities": 400,
                "Cash": 50,
            },
            "2022-12-31": {
                "Property Plant Equipment": 900,
                "Total Current Assets": 550,
                "Total Current Liabilities": 380,
                "Cash": 45,
            },
            "2021-12-31": {
                "Property Plant Equipment": 850,
                "Total Current Assets": 500,
                "Total Current Liabilities": 360,
                "Cash": 40,
            },
        }
    )


def _cashflow_template():
    return pd.DataFrame(
        {
            "2023-12-31": {
                "Capital Expenditures": -120,
                "Free Cash Flow": 250,
            },
            "2022-12-31": {
                "Capital Expenditures": -110,
                "Free Cash Flow": 230,
            },
        }
    )


class MetricsLayerTests(unittest.TestCase):
    def test_normalize_tax_rate_averages_recent_values(self):
        financials = _financials_template()
        normalized = backend_main.normalize_tax_rate(financials, fallback_rate=0.21)
        self.assertAlmostEqual(normalized, 0.20, places=2)

    def test_compute_roic_uses_prior_year_invested_capital(self):
        financials = _financials_template()
        balance_sheet = _balance_sheet_template()
        invested = backend_main.compute_invested_capital(financials, balance_sheet)
        roic = backend_main.compute_roic(
            financials,
            balance_sheet,
            tax_rate=0.20,
            invested_capital_history=invested,
        )
        self.assertIn(2023, roic)
        expected_nopat = 300 * (1 - 0.20)
        expected_invested_prev = invested[2022]
        self.assertAlmostEqual(roic[2023], expected_nopat / expected_invested_prev, places=3)

    def test_compute_base_year_fcff_handles_components_and_fallback(self):
        financials = pd.DataFrame(
            {
                "2023-12-31": {
                    "Ebit": 400,
                    "Depreciation": 80,
                    "Income Tax Expense": 100,
                    "Income Before Tax": 400,
                },
                "2022-12-31": {
                    "Ebit": 360,
                    "Depreciation": 75,
                    "Income Tax Expense": 90,
                    "Income Before Tax": 360,
                },
            }
        )
        cashflow = pd.DataFrame(
            {
                "2023-12-31": {
                    "Capital Expenditures": -120,
                    "Free Cash Flow": 250,
                },
                "2022-12-31": {
                    "Capital Expenditures": -110,
                    "Free Cash Flow": 230,
                },
            }
        )
        balance_sheet = pd.DataFrame(
            {
                "2023-12-31": {
                    "Total Current Assets": 500,
                    "Total Current Liabilities": 300,
                },
                "2022-12-31": {
                    "Total Current Assets": 470,
                    "Total Current Liabilities": 290,
                },
            }
        )
        fallback_series = backend_main.get_fcf_series(financials, cashflow)
        normalized_rate = backend_main.normalize_tax_rate(financials, fallback_rate=0.25)
        fcff = backend_main.compute_base_year_fcff(
            financials,
            cashflow,
            balance_sheet,
            normalized_rate,
            fallback_series=fallback_series,
        )
        self.assertAlmostEqual(fcff, 240.0, places=2)


if __name__ == "__main__":
    unittest.main()
