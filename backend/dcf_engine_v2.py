import logging
import math
import re
from enum import Enum
from statistics import median
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


class DCFComputationError(RuntimeError):
    """Raised when the v2 DCF engine cannot build a valuation."""
    pass


class ScenarioPreset(str, Enum):
    CONSERVATIVE = "conservative"
    BASE = "base"
    OPTIMISTIC = "optimistic"


def get_scenario_config(preset: str, archetype: str) -> Dict[str, Any]:
    """Return scenario assumptions tuned for the given archetype."""
    try:
        preset_enum = ScenarioPreset(preset.lower())
    except Exception:
        preset_enum = ScenarioPreset.BASE

    hyper = archetype == "hypergrowth"

    if hyper:
        if preset_enum == ScenarioPreset.CONSERVATIVE:
            return {
                "name": preset_enum.value,
                "wacc_shift": 0.005,
                "wacc_min": 0.072,
                "wacc_max": 0.09,
                "g_terminal_min": 0.028,
                "g_terminal_max": 0.034,
                "horizon_override": 10,
                "base_fcff_forward_tilt": 0.15,
                "high_growth_years": 8,
                "rev_phase1_min": 0.18,
                "rev_phase1_max": 0.30,
                "rev_terminal": 0.055,
                "margin_uplift": 0.02,
            }
        if preset_enum == ScenarioPreset.OPTIMISTIC:
            return {
                "name": preset_enum.value,
                "wacc_shift": -0.01,
                "wacc_min": 0.06,
                "wacc_max": 0.08,
                "g_terminal_min": 0.032,
                "g_terminal_max": 0.05,
                "horizon_override": 15,
                "base_fcff_forward_tilt": 0.5,
                "high_growth_years": 12,
                "rev_phase1_min": 0.28,
                "rev_phase1_max": 0.45,
                "rev_terminal": 0.08,
                "margin_uplift": 0.08,
            }
        return {
            "name": preset_enum.value,
            "wacc_shift": 0.0,
            "wacc_min": 0.065,
            "wacc_max": 0.085,
            "g_terminal_min": 0.03,
            "g_terminal_max": 0.04,
            "horizon_override": 12,
            "base_fcff_forward_tilt": 0.3,
            "high_growth_years": 10,
            "rev_phase1_min": 0.24,
            "rev_phase1_max": 0.4,
            "rev_terminal": 0.07,
            "margin_uplift": 0.05,
        }

    # Mature / steady names
    if preset_enum == ScenarioPreset.CONSERVATIVE:
        return {
            "name": preset_enum.value,
            "wacc_shift": 0.01,
            "wacc_min": 0.08,
            "wacc_max": 0.11,
            "g_terminal_min": 0.02,
            "g_terminal_max": 0.027,
            "horizon_override": 8,
            "base_fcff_forward_tilt": 0.0,
            "high_growth_years": 4,
            "rev_phase1_min": 0.05,
            "rev_phase1_max": 0.08,
            "rev_terminal": 0.03,
            "margin_uplift": 0.0,
        }
    if preset_enum == ScenarioPreset.OPTIMISTIC:
        return {
            "name": preset_enum.value,
            "wacc_shift": -0.01,
            "wacc_min": 0.06,
            "wacc_max": 0.09,
            "g_terminal_min": 0.028,
            "g_terminal_max": 0.035,
            "horizon_override": 12,
            "base_fcff_forward_tilt": 0.4,
            "high_growth_years": 6,
            "rev_phase1_min": 0.08,
            "rev_phase1_max": 0.12,
            "rev_terminal": 0.035,
            "margin_uplift": 0.03,
        }
    return {
        "name": preset_enum.value,
        "wacc_shift": 0.0,
        "wacc_min": 0.07,
        "wacc_max": 0.10,
        "g_terminal_min": 0.025,
        "g_terminal_max": 0.033,
        "horizon_override": None,
        "base_fcff_forward_tilt": 0.25,
        "high_growth_years": 5,
        "rev_phase1_min": 0.06,
        "rev_phase1_max": 0.09,
        "rev_terminal": 0.032,
        "margin_uplift": 0.01,
    }


def _clamp(value: float, lower: float, upper: float) -> float:
    if value is None or not math.isfinite(value):
        return lower
    return max(lower, min(value, upper))


def _safe_float(value: Optional[float], default: float) -> float:
    try:
        if value is None:
            return default
        numeric = float(value)
        if not math.isfinite(numeric):
            return default
        return numeric
    except Exception:
        return default


def _extract_fcf_values(fcf_series: Optional[List[Dict[str, Any]]]) -> List[float]:
    values: List[float] = []
    if not isinstance(fcf_series, list):
        return values
    for entry in fcf_series:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("value")
        try:
            val = float(raw)
        except Exception:
            continue
        if math.isfinite(val):
            values.append(val)
    return values


def compute_normalized_base_fcff(values: List[float], base_candidate: Optional[float]) -> Optional[float]:
    valid: List[float] = [v for v in values if v is not None and math.isfinite(v) and v > 0]
    candidate = base_candidate if base_candidate is not None and math.isfinite(base_candidate) and base_candidate > 0 else None
    if candidate is not None:
        valid.append(candidate)
    if len(valid) < 2:
        return candidate
    recent = valid[:5]
    med = median(recent)
    if med == 0:
        trimmed = recent
    else:
        trimmed = [v for v in recent if abs(v - med) / abs(med) <= 0.5]
    if not trimmed:
        trimmed = recent
    weights = list(range(len(trimmed), 0, -1))
    normalized = sum(v * w for v, w in zip(trimmed, weights)) / sum(weights)
    if normalized <= 0:
        return candidate
    return normalized


def compute_fcf_cagr_5y(values: List[float]) -> Optional[float]:
    usable = [v for v in values if v is not None and math.isfinite(v) and v > 0]
    if len(usable) < 2:
        return None
    oldest_index = min(len(usable) - 1, 4)
    recent = usable[0]
    oldest = usable[oldest_index]
    years = oldest_index
    if oldest <= 0 or recent <= 0 or years <= 0:
        return None
    return (recent / oldest) ** (1 / years) - 1


def classify_company_archetype(metrics: Dict[str, Any], base_fcff: float, fcf_values: List[float]) -> str:
    growth_hint = str(metrics.get("growthModel") or "").lower()
    if "high" in growth_hint or "hyper" in growth_hint:
        return "hypergrowth"
    if "mature" in growth_hint or "stable" in growth_hint:
        return "mature"

    revenue_cagr = _safe_optional(metrics.get("revenueCAGR5Y"))
    fcf_cagr = compute_fcf_cagr_5y(fcf_values)
    revenue_last = _safe_optional(metrics.get("revenueLast"))

    if revenue_last and revenue_last >= 5_000_000_000:
        if revenue_cagr and revenue_cagr >= 0.25:
            return "hypergrowth"
    if fcf_cagr and fcf_cagr >= 0.25:
        return "hypergrowth"
    if revenue_cagr and revenue_cagr >= 0.30:
        return "hypergrowth"
    return "mature"


def build_growth_path(
    horizon_years: int,
    g_terminal: float,
    fcf_cagr: Optional[float],
    revenue_cagr: Optional[float],
    roic_growth: Optional[float],
) -> Tuple[List[float], float, float, float]:
    horizon = max(1, horizon_years)
    candidates = [
        value
        for value in (fcf_cagr, revenue_cagr, roic_growth)
        if value is not None and math.isfinite(value) and value > 0
    ]
    if candidates:
        g_short_raw = median(candidates)
        if g_short_raw < 0.02:
            g_short = 0.01
        else:
            g_short = _clamp(g_short_raw, 0.04, 0.12)
    else:
        g_short = 0.02
    g_mid = _clamp((g_short + g_terminal) / 2.0, 0.03, 0.08)

    phase1_end = min(horizon, max(1, int(round(0.3 * horizon))))
    phase2_end = min(horizon, max(phase1_end + 1, int(round(0.7 * horizon))))

    growth_rates: List[float] = []
    for year in range(1, horizon + 1):
        if year <= phase1_end:
            rate = g_short
        elif year <= phase2_end:
            span = max(1, phase2_end - phase1_end)
            progress = (year - phase1_end) / span
            rate = g_short + (g_mid - g_short) * progress
        else:
            span = max(1, horizon - phase2_end)
            progress = (year - phase2_end) / span
            rate = g_mid + (g_terminal - g_mid) * progress
        growth_rates.append(rate)

    return growth_rates, g_short, g_mid, g_terminal


def build_hypergrowth_revenue_path(
    horizon: int,
    high_growth_years: int,
    phase1_growth: float,
    terminal_growth: float,
) -> List[float]:
    horizon = max(1, horizon)
    phase1_years = min(high_growth_years, horizon)
    phase1_growth = _clamp(phase1_growth, 0.10, 0.60)
    terminal_growth = _clamp(terminal_growth, 0.03, 0.10)
    growth_rates: List[float] = []
    for year in range(1, horizon + 1):
        if year <= phase1_years:
            rate = phase1_growth
        else:
            span = max(1, horizon - phase1_years)
            progress = (year - phase1_years) / span
            rate = phase1_growth + (terminal_growth - phase1_growth) * progress
        growth_rates.append(rate)
    return growth_rates


def build_hypergrowth_margin_path(start_margin: float, terminal_margin: float, horizon: int) -> List[float]:
    horizon = max(1, horizon)
    start = _clamp(start_margin, 0.02, 0.45)
    terminal = _clamp(terminal_margin, 0.05, 0.50)
    if horizon == 1:
        return [terminal]
    path: List[float] = []
    for idx in range(horizon):
        progress = idx / (horizon - 1)
        path.append(start + (terminal - start) * progress)
    return path


def _clean_number(value: Optional[float]) -> Optional[float]:
    # Production failures showed ValueError: "Out of range float values are not JSON compliant"
    # when NaNs bubbled up from the FCFF path, so every numeric payload goes through this gate.
    if value is None:
        return None
    try:
        numeric = float(value)
    except Exception:
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _safe_optional(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except Exception:
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _label_to_year(label: Any) -> Optional[int]:
    if isinstance(label, (int, float)):
        try:
            return int(label)
        except Exception:
            return None
    if isinstance(label, str):
        match = re.search(r"\d{4}", label)
        if match:
            try:
                return int(match.group(0))
            except Exception:
                return None
    return None


def compute_normalized_base_fcff(values: List[float], base_candidate: Optional[float]) -> Optional[float]:
    """Normalize the base FCFF using recent history with outlier trimming."""
    valid: List[float] = [v for v in values if v is not None and math.isfinite(v) and v > 0]
    candidate = base_candidate if base_candidate is not None and math.isfinite(base_candidate) and base_candidate > 0 else None
    if candidate is not None:
        valid.append(candidate)
    if len(valid) < 2:
        return candidate
    recent = valid[:5]
    med = median(recent)
    if med == 0:
        trimmed = recent
    else:
        trimmed = [v for v in recent if abs(v - med) / abs(med) <= 0.5]
    if not trimmed:
        trimmed = recent
    weights = list(range(len(trimmed), 0, -1))
    normalized = sum(v * w for v, w in zip(trimmed, weights)) / sum(weights)
    if normalized <= 0:
        return candidate
    return normalized


def compute_fcf_cagr_5y(values: List[float]) -> Optional[float]:
    """Estimate a simple FCF CAGR using up to ~5 years of positive history."""
    usable = [v for v in values if v is not None and math.isfinite(v) and v > 0]
    if len(usable) < 2:
        return None
    oldest_index = min(len(usable) - 1, 4)
    recent = usable[0]
    oldest = usable[oldest_index]
    years = oldest_index
    if oldest <= 0 or recent <= 0 or years <= 0:
        return None
    return (recent / oldest) ** (1 / years) - 1


def compute_reinvestment_rate(nopat_history: Optional[List[Dict[str, Any]]], fcf_series: Optional[List[Dict[str, Any]]]) -> Optional[float]:
    """Approximate reinvestment as 1 - FCFF/NOPAT across overlapping years."""
    if not nopat_history or not fcf_series:
        return None
    fcff_by_year: Dict[int, float] = {}
    for entry in fcf_series:
        if not isinstance(entry, dict):
            continue
        year = _label_to_year(entry.get("label") or entry.get("year"))
        value = entry.get("value")
        if year is None or value is None:
            continue
        try:
            numeric = float(value)
        except Exception:
            continue
        if math.isfinite(numeric):
            fcff_by_year[year] = numeric
    reinvestments: List[float] = []
    for entry in nopat_history:
        if not isinstance(entry, dict):
            continue
        year = entry.get("year")
        nopat = entry.get("nopat")
        if year is None or nopat is None:
            continue
        fcff = fcff_by_year.get(year)
        if fcff is None:
            continue
        try:
            nopat_val = float(nopat)
            fcff_val = float(fcff)
        except Exception:
            continue
        if nopat_val <= 0 or fcff_val <= 0:
            continue
        rate = 1.0 - (fcff_val / nopat_val)
        rate = _clamp(rate, 0.0, 0.6)
        reinvestments.append(rate)
        if len(reinvestments) >= 5:
            break
    if not reinvestments:
        return None
    return sum(reinvestments) / len(reinvestments)


def compute_normalized_roic(roic_history: Optional[List[Dict[str, Any]]]) -> Optional[float]:
    if not roic_history:
        return None
    values: List[float] = []
    for entry in roic_history:
        val = None
        if isinstance(entry, dict):
            val = entry.get("roic")
        else:
            val = entry
        try:
            numeric = float(val)
        except Exception:
            continue
        if not math.isfinite(numeric) or numeric <= 0 or numeric > 1.0:
            continue
        values.append(numeric)
        if len(values) >= 5:
            break
    if not values:
        return None
    values_sorted = sorted(values)
    if len(values_sorted) >= 3:
        trimmed = values_sorted[1:-1]
    else:
        trimmed = values_sorted
    if not trimmed:
        trimmed = values_sorted
    avg = sum(trimmed) / len(trimmed)
    return _clamp(avg, 0.05, 0.40)


def compute_roic_implied_growth(normalized_roic: Optional[float], reinvestment_rate: Optional[float]) -> Optional[float]:
    if normalized_roic is None or reinvestment_rate is None:
        return None
    growth = normalized_roic * reinvestment_rate
    return _clamp(growth, 0.0, 0.15)


def resolve_terminal_growth(
    g_terminal_input: Optional[float],
    revenue_cagr: Optional[float],
    min_val: float = 0.015,
    max_val: float = 0.035,
) -> float:
    if g_terminal_input is not None and math.isfinite(g_terminal_input):
        return _clamp(g_terminal_input, min_val, max_val)
    rev = revenue_cagr if revenue_cagr is not None and math.isfinite(revenue_cagr) else 0.03
    rev = _clamp(rev, 0.0, 0.06)
    auto = 0.02 + 0.5 * rev
    return _clamp(auto, min_val, max_val)


def project_fcff(
    base_fcff: float,
    growth_path: List[float],
    wacc: float,
    g_terminal: float,
    base_year: Optional[int],
) -> Tuple[List[Dict[str, float]], Dict[str, float], float]:
    horizon = len(growth_path)
    if horizon == 0:
        return [], {"fcffTerminal": 0.0, "gTerminal": g_terminal, "tv": 0.0, "pvTv": 0.0}, 0.0

    wacc_safe = max(wacc, 0.01)
    g_terminal = _clamp(g_terminal, 0.015, 0.025)
    fcff_current = base_fcff
    forecast: List[Dict[str, float]] = []
    pv_sum = 0.0

    for idx, growth in enumerate(growth_path, start=1):
        fcff_current = fcff_current * (1.0 + growth)
        discount_factor = 1.0 / math.pow(1.0 + wacc_safe, idx)
        pv_fcff = fcff_current * discount_factor
        pv_sum += pv_fcff
        year_label = base_year + idx if isinstance(base_year, int) else idx
        forecast.append(
            {
                "year": year_label,
                "growth": _clean_number(growth),
                "fcff": _clean_number(fcff_current),
                "discountFactor": _clean_number(discount_factor),
                "pvFcff": _clean_number(pv_fcff),
                "revenue": None,
                "fcffMargin": None,
            }
        )

    last_fcff = forecast[-1]["fcff"] if forecast else base_fcff
    denom = max(wacc_safe - g_terminal, 0.03)
    terminal_value = (last_fcff or 0.0) * (1.0 + g_terminal) / denom
    pv_terminal = terminal_value / math.pow(1.0 + wacc_safe, horizon)
    terminal_summary = {
        "fcffTerminal": _clean_number(last_fcff),
        "gTerminal": _clean_number(g_terminal),
        "terminalReinvestmentRate": None,
        "tv": _clean_number(terminal_value),
        "pvTv": _clean_number(pv_terminal),
    }

    return forecast, terminal_summary, pv_sum


def project_fcff_hypergrowth(
    base_revenue: float,
    revenue_growth_path: List[float],
    margin_path: List[float],
    wacc: float,
    g_terminal: float,
    base_year: Optional[int],
) -> Tuple[List[Dict[str, float]], Dict[str, float], float, Dict[str, Optional[float]]]:
    if base_revenue is None or base_revenue <= 0:
        raise DCFComputationError("Invalid revenue for hypergrowth projection")
    horizon = len(revenue_growth_path)
    if horizon == 0:
        return [], {"fcffTerminal": 0.0, "gTerminal": g_terminal, "tv": 0.0, "pvTv": 0.0}, 0.0, {}

    wacc_safe = max(wacc, 0.01)
    g_terminal = _clamp(g_terminal, 0.02, 0.05)
    forecast: List[Dict[str, float]] = []
    pv_sum = 0.0
    revenue = base_revenue

    for idx, growth in enumerate(revenue_growth_path):
        revenue = revenue * (1.0 + growth)
        margin = margin_path[idx]
        fcff_value = revenue * margin
        discount_factor = 1.0 / math.pow(1.0 + wacc_safe, idx + 1)
        pv_fcff = fcff_value * discount_factor
        pv_sum += pv_fcff
        year_label = base_year + idx + 1 if isinstance(base_year, int) else idx + 1
        forecast.append(
            {
                "year": year_label,
                "growth": _clean_number(growth),
                "fcff": _clean_number(fcff_value),
                "discountFactor": _clean_number(discount_factor),
                "pvFcff": _clean_number(pv_fcff),
                "revenue": _clean_number(revenue),
                "fcffMargin": _clean_number(margin),
            }
        )

    last_fcff = forecast[-1]["fcff"] if forecast else base_revenue * margin_path[0]
    spread = max(wacc_safe - g_terminal, 0.025)
    terminal_value = (last_fcff or 0.0) * (1.0 + g_terminal) / spread
    pv_terminal = terminal_value / math.pow(1.0 + wacc_safe, horizon)
    terminal_summary = {
        "fcffTerminal": _clean_number(last_fcff),
        "gTerminal": _clean_number(g_terminal),
        "terminalReinvestmentRate": None,
        "tv": _clean_number(terminal_value),
        "pvTv": _clean_number(pv_terminal),
    }
    meta = {
        "fcffMarginStart": _clean_number(margin_path[0] if margin_path else None),
        "fcffMarginTerminal": _clean_number(margin_path[-1] if margin_path else None),
        "growthPhase1Rev": _clean_number(revenue_growth_path[0] if revenue_growth_path else None),
        "growthPhase2Rev": _clean_number(revenue_growth_path[-1] if revenue_growth_path else None),
    }
    return forecast, terminal_summary, pv_sum, meta


def run_dcf_v2(
    metrics: Dict[str, Any],
    cost_of_capital: Dict[str, Any],
    horizon_years: int = 10,
    g_terminal: Optional[float] = None,
    scenario: str = ScenarioPreset.BASE.value,
) -> Optional[Dict[str, Any]]:
    metrics = metrics or {}
    cost_of_capital = cost_of_capital or {}

    fcf_series_raw = metrics.get("fcfSeries")
    fcf_values = _extract_fcf_values(fcf_series_raw)
    base_candidate = _safe_optional(metrics.get("baseYearFcffNormalized"))
    if base_candidate is None:
        base_candidate = _safe_optional(metrics.get("baseFcf"))
    base_fcff = compute_normalized_base_fcff(fcf_values, base_candidate)
    if base_fcff is None:
        raise DCFComputationError("no_base_fcf")

    wacc = _safe_float(cost_of_capital.get("wacc"), 0.08)
    if wacc <= 0:
        wacc = 0.08

    revenue_last = _safe_optional(metrics.get("revenueLast"))
    archetype = classify_company_archetype(metrics, base_fcff, fcf_values)
    config = get_scenario_config(scenario, archetype)
    revenue_cagr = _safe_optional(metrics.get("revenueCAGR5Y"))
    fcf_cagr = compute_fcf_cagr_5y(fcf_values)
    reinvestment_rate = compute_reinvestment_rate(metrics.get("nopatHistory"), fcf_series_raw)
    normalized_roic = compute_normalized_roic(metrics.get("roicHistory"))
    roic_growth = compute_roic_implied_growth(normalized_roic, reinvestment_rate)

    wacc = _clamp(
        wacc + config["wacc_shift"],
        config["wacc_min"],
        config["wacc_max"],
    )

    base_horizon = metrics.get("horizonYears")
    try:
        base_horizon = int(base_horizon)
    except Exception:
        base_horizon = None
    effective_horizon = config["horizon_override"] or base_horizon or horizon_years
    g_terminal_used = resolve_terminal_growth(
        g_terminal,
        revenue_cagr,
        config["g_terminal_min"],
        config["g_terminal_max"],
    )

    use_hyper = archetype == "hypergrowth" and revenue_last and revenue_last > 0
    hyper_meta: Dict[str, Optional[float]] = {}
    base_fcff_projection = base_fcff
    g_short = None
    g_mid = None

    if use_hyper:
        try:
            rev_growth_hint = revenue_cagr if revenue_cagr is not None else config["rev_phase1_min"]
            phase1_growth = _clamp(
                rev_growth_hint,
                config["rev_phase1_min"],
                config["rev_phase1_max"],
            )
            revenue_growth_path = build_hypergrowth_revenue_path(
                effective_horizon,
                config["high_growth_years"],
                phase1_growth,
                config["rev_terminal"],
            )
            g_short = revenue_growth_path[0] if revenue_growth_path else None
            g_mid = (revenue_growth_path[0] + revenue_growth_path[-1]) / 2.0 if revenue_growth_path else None
            tilt_fraction = config.get("base_fcff_forward_tilt", 0.0) or 0.0
            if tilt_fraction > 0 and g_short is not None:
                base_fcff_projection = base_fcff * (1.0 + tilt_fraction * g_short)
                base_fcff_projection = base_fcff_projection / (1.0 + g_short)
            margin_start = base_fcff_projection / revenue_last if revenue_last else None
            if margin_start is None or margin_start <= 0:
                raise DCFComputationError("no_base_fcf")
            margin_terminal = margin_start + config.get("margin_uplift", 0.0)
            margin_path = build_hypergrowth_margin_path(margin_start, margin_terminal, len(revenue_growth_path))
            forecast, terminal_summary, pv_sum, hyper_meta = project_fcff_hypergrowth(
                revenue_last,
                revenue_growth_path,
                margin_path,
                wacc,
                g_terminal_used,
                metrics.get("baseYear"),
            )
        except DCFComputationError:
            use_hyper = False

    if not use_hyper:
        growth_path, g_short, g_mid, g_terminal_used = build_growth_path(
            effective_horizon,
            g_terminal_used,
            fcf_cagr,
            revenue_cagr,
            roic_growth,
        )
        tilt_fraction = config.get("base_fcff_forward_tilt", 0.0) or 0.0
        base_fcff_projection = base_fcff
        if tilt_fraction > 0 and g_short is not None:
            base_fcff_projection = base_fcff * (1.0 + tilt_fraction * g_short)
            base_fcff_projection = base_fcff_projection / (1.0 + g_short)
        forecast, terminal_summary, pv_sum = project_fcff(
            base_fcff_projection,
            growth_path,
            wacc,
            g_terminal_used,
            metrics.get("baseYear"),
        )
        hyper_meta = {
            "fcffMarginStart": None,
            "fcffMarginTerminal": None,
            "growthPhase1Rev": None,
            "growthPhase2Rev": None,
        }

    enterprise_value = pv_sum + (terminal_summary.get("pvTv") or 0.0)
    net_debt = _safe_float(metrics.get("netDebt"), 0.0)
    equity_value = enterprise_value - net_debt
    shares = _safe_float(metrics.get("sharesOutstanding"), 0.0)
    implied_share_price = equity_value / shares if shares > 0 else None

    valuation = {
        "settings": {
            "horizonYears": effective_horizon,
            "horizonYearsUsed": effective_horizon,
            "gTerminal": g_terminal_used,
            "gTerminalUsed": g_terminal_used,
            "engineVersion": "v2",
            "wacc": wacc,
            "waccUsed": wacc,
            "growthShort": g_short,
            "growthMid": g_mid,
            "baseFcffNormalized": base_fcff,
            "baseFcffProjectionStart": base_fcff_projection,
            "scenarioPreset": config["name"],
            "archetype": archetype,
            "revenueCAGR5YUsed": revenue_cagr,
            "fcffMarginStart": hyper_meta.get("fcffMarginStart"),
            "fcffMarginTerminal": hyper_meta.get("fcffMarginTerminal"),
            "growthPhase1Rev": hyper_meta.get("growthPhase1Rev"),
            "growthPhase2Rev": hyper_meta.get("growthPhase2Rev"),
        },
        "fcffForecast": forecast,
        "terminalValue": terminal_summary,
        "enterpriseValue": enterprise_value,
        "equityValue": equity_value,
        "impliedSharePrice": implied_share_price,
        "baseFcff": base_fcff,
    }

    return valuation
