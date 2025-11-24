import unittest

from backend.cost_of_capital import (
    NORMALIZED_RISK_FREE,
    NORMALIZED_MARKET_PREMIUM,
    compute_unlevered_beta,
    compute_relevered_beta,
    compute_cost_of_equity,
    compute_cost_of_debt,
    compute_wacc,
    shrink_beta,
)


class CostOfCapitalTests(unittest.TestCase):
    def test_unlevered_and_relevered_beta_behave(self):
        beta_u = compute_unlevered_beta(beta_levered=1.4, debt_equity=0.8, tax_rate=0.25)
        self.assertLess(beta_u, 1.4)
        beta_r = compute_relevered_beta(beta_u, target_debt_equity=0.8, tax_rate=0.25)
        self.assertAlmostEqual(beta_r, 1.4, places=2)

    def test_cost_of_equity_uses_capm(self):
        result = compute_cost_of_equity(beta=1.2, risk_free_rate=0.04, market_risk_premium=0.055)
        self.assertAlmostEqual(result, 0.04 + 1.2 * 0.055, places=6)

    def test_cost_of_debt_prefers_observed_interest(self):
        cost = compute_cost_of_debt(interest_expense=-40, total_debt=500, risk_free_rate=0.04, ebit=200)
        self.assertAlmostEqual(cost, 40 / 500, places=6)

    def test_cost_of_debt_fallback_uses_spread(self):
        cost = compute_cost_of_debt(
            interest_expense=None,
            total_debt=400,
            risk_free_rate=0.04,
            ebit=150,
            leverage_ratio=0.5,
        )
        self.assertGreaterEqual(cost, 0.05)

    def test_wacc_with_weights_and_clamp(self):
        wacc = compute_wacc(0.10, 0.04, equity_value=800, debt_value=200)
        expected = 0.8 * 0.10 + 0.2 * 0.04
        self.assertAlmostEqual(wacc, expected, places=6)

        wacc_extreme = compute_wacc(0.02, 0.01, equity_value=0, debt_value=0)
        self.assertGreaterEqual(wacc_extreme, 0.06)

    def test_shrink_beta_trends_toward_one(self):
        beta = shrink_beta(2.0)
        self.assertLess(beta, 2.0)
        beta_default = shrink_beta(None)
        self.assertGreater(beta_default, 0.5)


if __name__ == "__main__":
    unittest.main()
