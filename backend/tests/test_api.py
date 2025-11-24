import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from backend import main as backend_main
from backend.dcf_engine_v2 import DCFComputationError


def _make_request(params=None):
    return SimpleNamespace(query_params=params or {})


def _make_ticker():
    financials = pd.DataFrame(
        {
            "2023-12-31": {
                "Total Revenue": 1000,
                "Ebit": 200,
                "Income Before Tax": 190,
                "Income Tax Expense": 40,
                "Interest Expense": -10,
            },
            "2022-12-31": {
                "Total Revenue": 950,
                "Ebit": 180,
                "Income Before Tax": 175,
                "Income Tax Expense": 35,
                "Interest Expense": -9,
            },
        }
    )
    cashflow = pd.DataFrame(
        {
            "2023-12-31": {
                "Capital Expenditures": -80,
                "Free Cash Flow": 120,
                "Total Cash From Operating Activities": 180,
            },
            "2022-12-31": {
                "Capital Expenditures": -75,
                "Free Cash Flow": 110,
                "Total Cash From Operating Activities": 170,
            },
        }
    )
    balance_sheet = pd.DataFrame(
        {
            "2023-12-31": {
                "Total Current Assets": 600,
                "Total Current Liabilities": 300,
                "Property Plant Equipment": 900,
                "Cash": 100,
                "Short Long Term Debt": 55,
                "Long Term Debt": 250,
            },
            "2022-12-31": {
                "Total Current Assets": 560,
                "Total Current Liabilities": 290,
                "Property Plant Equipment": 870,
                "Cash": 90,
                "Short Long Term Debt": 50,
                "Long Term Debt": 240,
            },
        }
    )

    return SimpleNamespace(
        financials=financials,
        cashflow=cashflow,
        balance_sheet=balance_sheet,
        fast_info={"market_cap": 1000, "shares_outstanding": 100},
        info={"beta": 1.2},
    )


def _make_no_fcf_ticker():
    financials = pd.DataFrame(
        {
            "2023-12-31": {
                "Total Revenue": 1000,
                "Ebit": 150,
                "Income Before Tax": 140,
                "Income Tax Expense": 30,
            },
        }
    )
    cashflow = pd.DataFrame(
        {
            "2023-12-31": {
                "Capital Expenditures": float("nan"),
                "Total Cash From Operating Activities": float("nan"),
            },
        }
    )
    balance_sheet = pd.DataFrame(
        {
            "2023-12-31": {
                "Total Current Assets": 500,
                "Total Current Liabilities": 250,
            },
        }
    )
    return SimpleNamespace(
        financials=financials,
        cashflow=cashflow,
        balance_sheet=balance_sheet,
        fast_info={"market_cap": 1000, "shares_outstanding": 100},
        info={"beta": 1.0},
    )


class ApiTests(unittest.TestCase):
    def test_company_endpoint_includes_metrics(self):
        fake_ticker = _make_ticker()
        with patch.object(backend_main.yf, "Ticker", return_value=fake_ticker):
            payload = asyncio.run(backend_main.get_company(_make_request(), "TEST"))
        self.assertEqual(payload["ticker"], "TEST")
        self.assertIn("derived", payload)
        self.assertIn("fcfSeries", payload)
        derived = payload["derived"]
        self.assertNotIn("valuationV2", derived)
        self.assertIn("costOfCapital", derived)
        coc = derived["costOfCapital"]
        for key in [
            "riskFreeRate",
            "marketRiskPremium",
            "betaRaw",
            "betaUnlevered",
            "betaRelevered",
            "costOfEquity",
            "costOfDebt",
            "equityWeight",
            "debtWeight",
            "wacc",
        ]:
            self.assertIn(key, coc)
        self.assertIn("metrics", derived)
        metrics = derived["metrics"]
        self.assertIn("normalizedTaxRate", metrics)
        self.assertIn("baseYearFcffNormalized", metrics)
        self.assertIsInstance(metrics["roicHistory"], list)
        self.assertIsInstance(metrics["investedCapitalHistory"], list)
        self.assertNotIn("valuationV2", derived)

    def test_company_endpoint_includes_v2_when_requested(self):
        fake_ticker = _make_ticker()
        with patch.object(backend_main.yf, "Ticker", return_value=fake_ticker):
            payload = asyncio.run(backend_main.get_company(_make_request({"engine": "v2"}), "TEST"))
        derived = payload["derived"]
        self.assertIn("valuationV2", derived)
        valuation = derived["valuationV2"]
        self.assertIn("fcffForecast", valuation)
        self.assertGreater(len(valuation["fcffForecast"]), 0)
        first_row = valuation["fcffForecast"][0]
        self.assertIn("growth", first_row)
        self.assertIn("fcff", first_row)
        self.assertIn("pvFcff", first_row)
        self.assertIn("enterpriseValue", valuation)
        self.assertIn("impliedSharePrice", valuation)
        self.assertIn("settings", valuation)
        self.assertIn("baseFcffNormalized", valuation["settings"])
        self.assertIn("baseFcffProjectionStart", valuation["settings"])
        self.assertIn("growthShort", valuation["settings"])
        self.assertEqual(valuation["settings"].get("scenarioPreset"), "base")
        self.assertIn("archetype", valuation["settings"])
        self.assertIn("waccUsed", valuation["settings"])
        self.assertNotIn("error", valuation)

    def test_company_endpoint_handles_v2_failure(self):
        fake_ticker = _make_ticker()
        with patch.object(backend_main.yf, "Ticker", return_value=fake_ticker), patch.object(
            backend_main, "run_dcf_v2", side_effect=DCFComputationError("boom")
        ):
            payload = asyncio.run(backend_main.get_company(_make_request({"engine": "v2"}), "TEST"))
        valuation = payload["derived"].get("valuationV2")
        self.assertEqual(valuation["error"], "valuation_unavailable")

    def test_company_endpoint_flags_no_base_fcf(self):
        fake_ticker = _make_no_fcf_ticker()
        with patch.object(backend_main.yf, "Ticker", return_value=fake_ticker):
            payload = asyncio.run(backend_main.get_company(_make_request({"engine": "v2"}), "TEST"))
        valuation = payload["derived"].get("valuationV2")
        self.assertEqual(valuation["error"], "no_base_fcf")

    def test_company_endpoint_scenario_param(self):
        fake_ticker = _make_ticker()
        with patch.object(backend_main.yf, "Ticker", return_value=fake_ticker):
            payload = asyncio.run(
                backend_main.get_company(
                    _make_request({"engine": "v2", "scenario": "optimistic", "growthModel": "High Growth"}),
                    "TEST",
                ),
            )
        valuation = payload["derived"].get("valuationV2")
        self.assertEqual(valuation["settings"].get("scenarioPreset"), "optimistic")


if __name__ == "__main__":
    unittest.main()
