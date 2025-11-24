import math
from typing import Optional

BETA_MIN = 0.5
BETA_MAX = 2.0
MIN_COST_OF_DEBT = 0.02
MAX_COST_OF_DEBT = 0.15
NORMALIZED_RISK_FREE = 0.0325
NORMALIZED_MARKET_PREMIUM = 0.0475
BETA_SHRINKAGE = 0.67
WACC_MIN = 0.06
WACC_MAX = 0.11


def _clamp(value: float, lower: float, upper: float) -> float:
    if value is None or not math.isfinite(value):
        return lower
    return max(lower, min(value, upper))


def compute_unlevered_beta(beta_levered: float, debt_equity: Optional[float], tax_rate: Optional[float]) -> float:
    """Convert observed beta to an asset (unlevered) beta using Hamada's equation."""
    beta = _clamp(beta_levered if beta_levered is not None else 1.0, BETA_MIN, BETA_MAX)
    de_ratio = max(0.0, debt_equity or 0.0)
    tax = _clamp(tax_rate if tax_rate is not None else 0.21, 0.0, 0.5)
    denominator = 1.0 + de_ratio * (1.0 - tax)
    if denominator <= 0:
        return beta
    return _clamp(beta / denominator, BETA_MIN, BETA_MAX)


def compute_relevered_beta(beta_unlevered: float, target_debt_equity: Optional[float], tax_rate: Optional[float]) -> float:
    """Re-lever the asset beta to match a target capital structure."""
    beta = _clamp(beta_unlevered if beta_unlevered is not None else 1.0, BETA_MIN, BETA_MAX)
    de_ratio = max(0.0, target_debt_equity or 0.0)
    tax = _clamp(tax_rate if tax_rate is not None else 0.21, 0.0, 0.5)
    relevered = beta * (1.0 + de_ratio * (1.0 - tax))
    return _clamp(relevered, BETA_MIN, BETA_MAX)


def shrink_beta(beta_raw: Optional[float]) -> float:
    """Blend the observed beta toward 1.0 to avoid extreme inputs."""
    beta = beta_raw if beta_raw is not None else 1.0
    try:
        beta = float(beta)
    except Exception:
        beta = 1.0
    if not math.isfinite(beta):
        beta = 1.0
    shrunk = BETA_SHRINKAGE * beta + (1.0 - BETA_SHRINKAGE) * 1.0
    return _clamp(shrunk, BETA_MIN, BETA_MAX)


def compute_cost_of_equity(beta: float, risk_free_rate: float, market_risk_premium: float) -> float:
    """Standard CAPM cost of equity with guardrails."""
    beta_safe = _clamp(beta, BETA_MIN, BETA_MAX)
    return risk_free_rate + beta_safe * market_risk_premium


def _spread_from_coverage(coverage: Optional[float]) -> float:
    if coverage is None or not math.isfinite(coverage) or coverage <= 0:
        return 0.03
    if coverage >= 8:
        return 0.01
    if coverage >= 5:
        return 0.0125
    if coverage >= 3:
        return 0.0175
    if coverage >= 1.5:
        return 0.025
    return 0.035


def compute_cost_of_debt(
    interest_expense: Optional[float],
    total_debt: Optional[float],
    risk_free_rate: float,
    ebit: Optional[float] = None,
    leverage_ratio: Optional[float] = None,
) -> float:
    """
    Estimate the marginal cost of debt:
    1) Directly from interest expense / debt when available.
    2) Otherwise fall back to risk-free rate plus a spread based on interest coverage / leverage.
    """
    cost = None
    if total_debt is not None and total_debt > 0 and interest_expense is not None:
        interest = abs(interest_expense)
        if interest > 0:
            cost = interest / total_debt
    coverage = None
    if interest_expense not in (None, 0) and ebit is not None:
        interest = abs(interest_expense)
        if interest > 0:
            coverage = ebit / interest
    if cost is None or not math.isfinite(cost) or cost <= 0:
        spread = _spread_from_coverage(coverage)
        if leverage_ratio is not None and leverage_ratio >= 0:
            if leverage_ratio < 0.2:
                spread = min(spread, 0.01)
            elif leverage_ratio < 0.4:
                spread = max(spread, 0.015)
            elif leverage_ratio < 0.7:
                spread = max(spread, 0.02)
            else:
                spread = max(spread, 0.03)
        cost = risk_free_rate + spread
    return _clamp(cost, MIN_COST_OF_DEBT, MAX_COST_OF_DEBT)


def compute_wacc(
    cost_of_equity: float,
    cost_of_debt_after_tax: float,
    equity_value: Optional[float],
    debt_value: Optional[float],
    min_wacc: float = WACC_MIN,
    max_wacc: float = WACC_MAX,
) -> float:
    """Blend cost of capital components while clamping to a reasonable range."""
    E = max(0.0, equity_value or 0.0)
    D = max(0.0, debt_value or 0.0)
    V = E + D
    if V == 0:
        raw = cost_of_equity
    else:
        equity_weight = E / V
        debt_weight = D / V
        equity_weight = _clamp(equity_weight, 0.70, 0.98)
        debt_weight = 1.0 - equity_weight
        raw = equity_weight * cost_of_equity + debt_weight * cost_of_debt_after_tax
    return _clamp(raw, min_wacc, max_wacc)
