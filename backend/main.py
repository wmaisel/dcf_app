import logging
import os
import re
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd
import math
from statistics import mean
from typing import Optional, List, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from curl_cffi import requests as curl_requests
except Exception:  # pragma: no cover - optional dependency
    curl_requests = None

from .cost_of_capital import (
    NORMALIZED_MARKET_PREMIUM,
    NORMALIZED_RISK_FREE,
    compute_unlevered_beta,
    compute_relevered_beta,
    compute_cost_of_equity,
    compute_cost_of_debt,
    compute_wacc,
    shrink_beta,
)
from .dcf_engine_v2 import run_dcf_v2, DCFComputationError, ScenarioPreset

logger = logging.getLogger(__name__)

FUND_CACHE_TTL = int(os.environ.get("FUNDAMENTALS_CACHE_TTL", "900"))
_FUNDAMENTALS_CACHE: Dict[str, Dict[str, pd.DataFrame]] = {}


def _cache_enabled() -> bool:
    if FUND_CACHE_TTL <= 0:
        return False
    if os.environ.get("ENABLE_FUNDAMENTALS_CACHE", "1") == "0":
        return False
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return True


_DEFAULT_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


def _build_yf_session():
    # Use curl_cffi by default because Yahoo now requires it. Only fall back to
    # requests.Session when curl_cffi isn't available (tests, minimal envs).
    if curl_requests is not None:
        session = curl_requests.Session(impersonate="chrome")
        session.headers.update(_DEFAULT_YF_HEADERS)
    else:
        session = requests.Session()
        session.headers.update(_DEFAULT_YF_HEADERS)
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET", "POST"]),
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
    return session


_YF_SESSION = _build_yf_session()


def _get_yf_ticker(ticker: str) -> yf.Ticker:
    """
    Prefer our hardened session but fall back to yfinance defaults when Yahoo
    rejects custom clients (the curl_cffi requirement introduced in late 2024).
    """
    try:
        return yf.Ticker(ticker, session=_YF_SESSION)
    except Exception as exc:
        logger.warning("Custom session rejected for %s: %s; falling back to default session", ticker, exc)
        return yf.Ticker(ticker)


_TICKER_RE = re.compile(r"^[A-Z0-9\.\-]+$")


def _normalize_ticker(raw: str) -> str:
    value = (raw or "").upper().strip()
    value = value.strip("{}[]() ")
    if not value or not _TICKER_RE.match(value):
        raise HTTPException(status_code=400, detail="Invalid ticker symbol")
    return value


_QUOTE_SUMMARY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}
_QUOTE_SUMMARY_MODULES = ",".join(
    [
        "incomeStatementHistory",
        "incomeStatementHistoryQuarterly",
        "balanceSheetHistory",
        "balanceSheetHistoryQuarterly",
        "cashflowStatementHistory",
        "cashflowStatementHistoryQuarterly",
    ]
)
_QUOTE_SUMMARY_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
_QUOTE_SUMMARY_SESSION = None


def _get_quote_summary_session():
    global _QUOTE_SUMMARY_SESSION
    if _QUOTE_SUMMARY_SESSION is not None:
        return _QUOTE_SUMMARY_SESSION
    if curl_requests is not None:
        session = curl_requests.Session()
    else:  # pragma: no cover - curl_cffi should be available via yfinance, but keep fallback
        session = requests.Session()
        adapter = HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.3))
        session.mount("https://", adapter)
        session.mount("http://", adapter)
    session.headers.update(_QUOTE_SUMMARY_HEADERS)
    _QUOTE_SUMMARY_SESSION = session
    return session


def _quote_summary_history_to_df(history: Optional[List[Dict[str, Any]]]) -> pd.DataFrame:
    if not history:
        return pd.DataFrame()
    rows: Dict[str, Dict[pd.Timestamp, float]] = {}
    for entry in history:
        if not isinstance(entry, dict):
            continue
        end_date = entry.get("endDate")
        timestamp = None
        if isinstance(end_date, dict):
            timestamp = end_date.get("raw") or end_date.get("fmt")
        elif isinstance(end_date, (int, float, str)):
            timestamp = end_date
        if timestamp is None:
            continue
        try:
            col = pd.to_datetime(timestamp, unit="s", utc=True)
        except Exception:
            try:
                col = pd.to_datetime(timestamp, utc=True)
            except Exception:
                continue
        for key, value in entry.items():
            if key == "endDate":
                continue
            raw_value = None
            if isinstance(value, dict):
                raw_value = value.get("raw")
            elif isinstance(value, (int, float)):
                raw_value = value
            if raw_value is None:
                continue
            rows.setdefault(key, {})[col] = raw_value
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame.from_dict(rows, orient="index")
    df = df[sorted(df.columns, reverse=True)]
    df.index = [_normalize_statement_label(idx) for idx in df.index]
    return df


def _cache_statements(ticker: str, frames: Dict[str, Optional[pd.DataFrame]]) -> None:
    if not _cache_enabled():
        return
    try:
        _FUNDAMENTALS_CACHE[ticker] = {
            key: value.copy(deep=True) if isinstance(value, pd.DataFrame) else value
            for key, value in frames.items()
        }
        _FUNDAMENTALS_CACHE[ticker]["timestamp"] = time.time()
    except Exception:
        logger.debug("Unable to cache statements for %s", ticker)


def _get_cached_statements(ticker: str) -> Optional[Dict[str, Optional[pd.DataFrame]]]:
    if not _cache_enabled():
        return None
    cached = _FUNDAMENTALS_CACHE.get(ticker)
    if not cached:
        return None
    ts = cached.get("timestamp")
    if ts is None or (time.time() - ts) > FUND_CACHE_TTL:
        _FUNDAMENTALS_CACHE.pop(ticker, None)
        return None
    return {
        key: value.copy(deep=True) if isinstance(value, pd.DataFrame) else value
        for key, value in cached.items()
        if key in {"financials", "cashflow", "balance"}
    }


def _normalize_statement_label(label: str) -> str:
    if not label:
        return label
    label = str(label)
    label = re.sub(r"([a-z])([A-Z])", r"\1 \2", label)
    label = label.replace("_", " ")
    label = label.title()
    replacements = {
        "Ebit": "EBIT",
        "Ebitda": "EBITDA",
        "Eps": "EPS",
        "Ii": "II",
    }
    for src, dest in replacements.items():
        label = label.replace(src, dest)
    return label.strip()


def _fetch_financials_via_quote_summary(ticker: str, ticker_obj: Optional[yf.Ticker] = None) -> Dict[str, pd.DataFrame]:
    params = {
        "modules": _QUOTE_SUMMARY_MODULES,
        "lang": "en-US",
        "region": "US",
    }
    payload = None
    if ticker_obj is not None:
        try:
            payload = ticker_obj._data.get_raw_json(
                _QUOTE_SUMMARY_URL.format(ticker=ticker),
                params=params,
                timeout=15,
            )
        except Exception as exc:
            logger.warning(
                "Quote summary fallback via yfinance session failed for %s: %s",
                ticker,
                exc,
            )
    if payload is None:
        session = _get_quote_summary_session()
        url = _QUOTE_SUMMARY_URL.format(ticker=ticker)
        try:
            response = session.get(url, params=params, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # pragma: no cover - network
            logger.warning("Quote summary fallback failed for %s: %s", ticker, exc)
            return {}
    result = payload.get("quoteSummary", {}).get("result")
    if not result:
        return {}
    node = result[0]
    income_history = node.get("incomeStatementHistory", {}).get("incomeStatementHistory")
    balance_history = node.get("balanceSheetHistory", {}).get("balanceSheetStatements")
    cash_history = node.get("cashflowStatementHistory", {}).get("cashflowStatements")
    return {
        "financials": _quote_summary_history_to_df(income_history),
        "balance": _quote_summary_history_to_df(balance_history),
        "cashflow": _quote_summary_history_to_df(cash_history),
    }


ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174,https://wmaisel.github.io",
)


def _parse_origins(raw: str) -> List[str]:
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI()


@app.get("/debug/yf/{ticker}")
def debug_yf(ticker: str):
    tk = _get_yf_ticker(ticker)
    f = tk.financials
    c = tk.cashflow
    b = tk.balance_sheet
    return {
        "ticker": ticker,
        "financials_empty": f is None or f.empty,
        "cashflow_empty": c is None or c.empty,
        "balance_sheet_empty": b is None or b.empty,
        "financials_rows": None if f is None else list(f.index[:5]),
        "cashflow_rows": None if c is None else list(c.index[:5]),
    }

def _is_finite_number(value: Optional[float]) -> bool:
    return value is not None and isinstance(value, (int, float)) and math.isfinite(value)


def _clamp(value: float, lower: float, upper: float) -> float:
    if value is None or not math.isfinite(value):
        return lower
    return max(lower, min(value, upper))

# Allow your Vite frontend (local + GitHub Pages) to call this API
origins = _parse_origins(ALLOWED_ORIGINS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_row(df: Optional[pd.DataFrame], label: str) -> Optional[pd.Series]:
    """
    Safely return a row Series from a DataFrame by label, or None.
    """
    try:
        if df is None or df.empty:
            return None
        if label in df.index:
            row = df.loc[label]
            if isinstance(row, pd.Series):
                return row
        return None
    except Exception:
        return None


def last_value(series: Optional[pd.Series]) -> Optional[float]:
    """
    Safely get the most recent (first) value from a Series as float, or None.
    """
    try:
        if series is None or series.empty:
            return None
        return float(series.iloc[0])
    except Exception:
        return None


def last_non_na_value(series: Optional[pd.Series]) -> Optional[float]:
    try:
        if series is None:
            return None
        non_na = series.dropna()
        if non_na.empty:
            return None
        return float(non_na.iloc[0])
    except Exception:
        return None


def get_ebit_series(financials: Optional[pd.DataFrame]) -> Optional[pd.Series]:
    if financials is None or financials.empty:
        return None

    candidate_labels = [
        "Ebit",
        "EBIT",
        "Operating Income",
        "OperatingIncome",
        "Operating Income (EBIT)",
    ]

    for label in candidate_labels:
        series = get_row(financials, label)
        if series is not None and not series.dropna().empty:
            return series

    gross_profit = get_row(financials, "Gross Profit")
    if gross_profit is None:
        return None

    rd = get_row(financials, "Research Development")
    sga = get_row(financials, "Selling General Administrative")

    rd_series = rd if isinstance(rd, pd.Series) else None
    sga_series = sga if isinstance(sga, pd.Series) else None

    if rd_series is None:
        rd_series = pd.Series(0.0, index=gross_profit.index)
    if sga_series is None:
        sga_series = pd.Series(0.0, index=gross_profit.index)

    try:
        proxy = gross_profit - rd_series - sga_series
        if not proxy.dropna().empty:
            return proxy
    except Exception:
        pass

    return None


def get_fcf_series(financials: Optional[pd.DataFrame], cashflow: Optional[pd.DataFrame]) -> Optional[pd.Series]:
    """
    Return a pandas Series of Free Cash Flow by year, most recent first.
    """
    if cashflow is None or cashflow.empty:
        return None

    fcf_direct = get_row(cashflow, "Free Cash Flow")
    if fcf_direct is not None and not fcf_direct.dropna().empty:
        return fcf_direct

    ocf = get_row(cashflow, "Total Cash From Operating Activities")
    if ocf is None or ocf.dropna().empty:
        ocf = get_row(cashflow, "Operating Cash Flow")

    capex = get_row(cashflow, "Capital Expenditures")

    if ocf is None or capex is None:
        return None

    try:
        fcf_manual = ocf - capex
        if not fcf_manual.dropna().empty:
            return fcf_manual
    except Exception:
        return None

    return None


def series_to_json_list(series: Optional[pd.Series]) -> List[Dict]:
    """
    Convert a pandas Series into a list of dicts sorted most recent first.
    """
    out: List[Dict] = []
    if series is None:
        return out

    try:
        non_na = series.dropna()
        for label, value in non_na.items():
            out.append({"label": str(label), "value": float(value)})
    except Exception:
        return []

    return out


def _extract_year_from_label(label: Any) -> Optional[int]:
    if label is None:
        return None
    if hasattr(label, "year"):
        try:
            return int(label.year)
        except Exception:
            return None
    if isinstance(label, (int, float)):
        try:
            return int(label)
        except Exception:
            return None
    try:
        text = str(label)
    except Exception:
        return None
    match = re.search(r"\d{4}", text)
    if match:
        try:
            return int(match.group(0))
        except Exception:
            return None
    return None


def _series_value(series: Optional[pd.Series], label: Any) -> Optional[float]:
    if series is None or label is None:
        return None
    try:
        value = series.get(label)
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def normalize_tax_rate(financials: Optional[pd.DataFrame], fallback_rate: float = 0.21, max_years: int = 5) -> float:
    tax_series = get_row(financials, "Income Tax Expense")
    pretax_series = get_row(financials, "Income Before Tax")
    rates: List[float] = []

    if tax_series is not None and pretax_series is not None:
        for label in tax_series.index:
            if len(rates) >= max_years:
                break
            tax_value = _series_value(tax_series, label)
            pretax_value = _series_value(pretax_series, label)
            if tax_value is None or pretax_value is None or pretax_value == 0:
                continue
            if pretax_value <= 0:
                continue
            rate = tax_value / pretax_value
            if math.isfinite(rate):
                rate = max(0.0, min(rate, 0.35))
                rates.append(rate)

    if rates:
        return mean(rates)
    return fallback_rate


def compute_invested_capital(financials: Optional[pd.DataFrame], balance_sheet: Optional[pd.DataFrame]) -> Dict[int, float]:
    if balance_sheet is None or balance_sheet.empty:
        return {}

    net_ppe_series = get_row(balance_sheet, "Property Plant Equipment")
    if net_ppe_series is None or net_ppe_series.dropna().empty:
        net_ppe_series = get_row(balance_sheet, "Property Plant Equipment Net")

    current_assets = get_row(balance_sheet, "Total Current Assets")
    current_liabilities = get_row(balance_sheet, "Total Current Liabilities")
    cash_series = get_row(balance_sheet, "Cash")
    if cash_series is None or cash_series.dropna().empty:
        cash_series = get_row(balance_sheet, "Cash And Cash Equivalents")

    operating_wc_series = None
    try:
        if current_assets is not None and current_liabilities is not None:
            operating_wc_series = current_assets - current_liabilities
    except Exception:
        operating_wc_series = None

    invested_capital: Dict[int, float] = {}
    for label in list(balance_sheet.columns):
        year = _extract_year_from_label(label)
        if year is None:
            continue

        net_ppe_val = _series_value(net_ppe_series, label)
        wc_val = _series_value(operating_wc_series, label)
        cash_val = _series_value(cash_series, label)

        if net_ppe_val is None and wc_val is None:
            continue

        invested = (net_ppe_val or 0.0) + (wc_val or 0.0)
        if cash_val is not None:
            invested -= cash_val

        invested_capital[year] = invested

    return invested_capital


def compute_nopat_history(financials: Optional[pd.DataFrame], tax_rate: float) -> Dict[int, float]:
    ebit_series = get_ebit_series(financials)
    if ebit_series is None:
        return {}

    nopat_history: Dict[int, float] = {}
    non_na = ebit_series.dropna()
    if non_na.empty:
        return {}

    for label, value in non_na.items():
        year = _extract_year_from_label(label)
        if year is None:
            continue
        try:
            ebit = float(value)
        except Exception:
            continue
        nopat = ebit * (1.0 - tax_rate)
        nopat_history[year] = nopat

    return nopat_history


def compute_roic(
    financials: Optional[pd.DataFrame],
    balance_sheet: Optional[pd.DataFrame],
    tax_rate: float,
    invested_capital_history: Optional[Dict[int, float]] = None,
) -> Dict[int, float]:
    if invested_capital_history is None:
        invested_capital_history = compute_invested_capital(financials, balance_sheet)

    if not invested_capital_history:
        return {}

    ebit_series = get_ebit_series(financials)
    if ebit_series is None:
        return {}

    roic_history: Dict[int, float] = {}
    non_na = ebit_series.dropna()
    if non_na.empty:
        return {}

    for label, value in non_na.items():
        year = _extract_year_from_label(label)
        if year is None:
            continue
        previous_year = year - 1
        invested_prev = invested_capital_history.get(previous_year)
        if invested_prev is None or invested_prev == 0:
            continue
        try:
            ebit_val = float(value)
        except Exception:
            continue
        nopat_val = ebit_val * (1.0 - tax_rate)
        roic_val = nopat_val / invested_prev
        if math.isfinite(roic_val):
            roic_history[year] = roic_val

    return roic_history


def _working_capital_delta(balance_sheet: Optional[pd.DataFrame], label: Any) -> Optional[float]:
    current_assets = get_row(balance_sheet, "Total Current Assets")
    current_liabilities = get_row(balance_sheet, "Total Current Liabilities")
    if current_assets is None or current_liabilities is None:
        return None

    try:
        wc_series = current_assets - current_liabilities
    except Exception:
        return None

    if wc_series is None or wc_series.empty:
        return None

    try:
        loc = wc_series.index.get_loc(label)
    except Exception:
        return None

    if isinstance(loc, slice):
        return None

    current_value = _series_value(wc_series, label)
    previous_value = None
    if loc + 1 < len(wc_series):
        previous_value = _series_value(wc_series, wc_series.index[loc + 1])

    if current_value is None or previous_value is None:
        return None

    return current_value - previous_value


def compute_base_year_fcff(
    financials: Optional[pd.DataFrame],
    cashflow: Optional[pd.DataFrame],
    balance_sheet: Optional[pd.DataFrame],
    tax_rate: float,
    fallback_series: Optional[pd.Series] = None,
) -> Optional[float]:
    ebit_series = get_ebit_series(financials)
    if ebit_series is None:
        return last_non_na_value(fallback_series)

    non_na = ebit_series.dropna()
    if non_na.empty:
        return last_non_na_value(fallback_series)

    latest_label = non_na.index[0]
    try:
        ebit_latest = float(non_na.iloc[0])
    except Exception:
        return last_non_na_value(fallback_series)

    nopat = ebit_latest * (1.0 - tax_rate)

    da_series = None
    for candidate in ("Depreciation And Amortization", "Depreciation", "Depreciation Amortization"):
        da_series = get_row(financials, candidate)
        if da_series is not None and not da_series.dropna().empty:
            break
    da_value = _series_value(da_series, latest_label) or 0.0

    capex_series = get_row(cashflow, "Capital Expenditures")
    capex_value_raw = _series_value(capex_series, latest_label)
    capex_outflow = None
    if capex_value_raw is not None:
        capex_outflow = abs(capex_value_raw)

    delta_wc = _working_capital_delta(balance_sheet, latest_label)

    if capex_outflow is None or delta_wc is None:
        return last_non_na_value(fallback_series)

    fcff = nopat + da_value - capex_outflow - delta_wc
    return fcff


def _history_dict_to_list(history: Dict[int, float], value_key: str) -> List[Dict[str, float]]:
    out: List[Dict[str, float]] = []
    for year in sorted(history.keys(), reverse=True):
        value = history[year]
        if value is None:
            continue
        try:
            numeric_value = float(value)
        except Exception:
            continue
        if not math.isfinite(numeric_value):
            continue
        out.append({"year": year, value_key: numeric_value})
    return out


@app.get("/")
async def root():
    return {"message": "DCF backend is running. See /api/company/{ticker} for data."}


@app.get("/api/company/{ticker}")
async def get_company(request: Request, ticker: str):
    ticker_clean = _normalize_ticker(ticker)
    cached_frames = _get_cached_statements(ticker_clean)
    financials = cached_frames.get("financials") if cached_frames else None
    cashflow = cached_frames.get("cashflow") if cached_frames else None
    balance = cached_frames.get("balance") if cached_frames else None

    try:
        tk = _get_yf_ticker(ticker_clean)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ticker")

    if financials is None:
        financials = tk.financials
    if cashflow is None:
        cashflow = tk.cashflow
    if balance is None:
        balance = tk.balance_sheet

    missing_sections = []
    for name, frame in (
        ("financials", financials),
        ("cashflow", cashflow),
        ("balance_sheet", balance),
    ):
        if frame is None or frame.empty:
            missing_sections.append(name)

    if missing_sections:
        fallback_frames = _fetch_financials_via_quote_summary(ticker_clean, tk)
        if fallback_frames:
            if (financials is None or financials.empty) and not fallback_frames["financials"].empty:
                financials = fallback_frames["financials"]
            if (cashflow is None or cashflow.empty) and not fallback_frames["cashflow"].empty:
                cashflow = fallback_frames["cashflow"]
            if (balance is None or balance.empty) and not fallback_frames["balance"].empty:
                balance = fallback_frames["balance"]
        missing_sections = []
        for name, frame in (
            ("financials", financials),
            ("cashflow", cashflow),
            ("balance_sheet", balance),
        ):
            if frame is None or frame.empty:
                missing_sections.append(name)

    if missing_sections:
        logger.warning("Ticker %s missing sections after fallback: %s", ticker_clean, ",".join(missing_sections))
        raise HTTPException(status_code=502, detail="Upstream data unavailable. Please retry later.")
    if cached_frames is None:
        _cache_statements(
            ticker_clean,
            {
                "financials": financials,
                "cashflow": cashflow,
                "balance": balance,
            },
        )

    revenue_series = get_row(financials, "Total Revenue")
    ebit_series = get_ebit_series(financials)

    revenue_last = last_non_na_value(revenue_series) or 0.0
    ebit_last = last_non_na_value(ebit_series) or 0.0
    ebit_margin_last = ebit_last / revenue_last if revenue_last > 0 else None
    margin_history: List[float] = []
    if revenue_series is not None and ebit_series is not None:
        for label in revenue_series.index:
            rev_val = _series_value(revenue_series, label)
            ebit_val = _series_value(ebit_series, label)
            if rev_val is None or rev_val == 0 or ebit_val is None:
                continue
            margin_history.append(ebit_val / rev_val)
            if len(margin_history) >= 5:
                break

    revenue_cagr_5y = None
    if revenue_series is not None:
        non_na = revenue_series.dropna()
        if len(non_na) >= 2:
            n_points = min(5, len(non_na))
            recent = float(non_na.iloc[0])
            oldest = float(non_na.iloc[n_points - 1])
            years = n_points - 1
            if oldest > 0 and years > 0:
                revenue_cagr_5y = (recent / oldest) ** (1 / years) - 1

    capex_series = get_row(cashflow, "Capital Expenditures")
    capex_to_sales = None
    if capex_series is not None and revenue_last > 0:
        capex_last = last_value(capex_series)
        if capex_last is not None:
            capex_to_sales = capex_last / revenue_last
    ocf_series = get_row(cashflow, "Total Cash From Operating Activities")
    if ocf_series is None or ocf_series.dropna().empty:
        ocf_series = get_row(cashflow, "Operating Cash Flow")

    current_assets_series = get_row(balance, "Total Current Assets")
    current_liabilities_series = get_row(balance, "Total Current Liabilities")
    delta_wc_to_sales = None
    if (
        current_assets_series is not None
        and current_liabilities_series is not None
        and revenue_last > 0
    ):
        wc_series = current_assets_series - current_liabilities_series
        non_na_wc = wc_series.dropna()
        if len(non_na_wc) >= 2:
            delta_wc = float(non_na_wc.iloc[0] - non_na_wc.iloc[1])
            delta_wc_to_sales = delta_wc / revenue_last

    tax_rate = None
    tax_expense_series = get_row(financials, "Income Tax Expense")
    pretax_series = get_row(financials, "Income Before Tax")
    if tax_expense_series is not None and pretax_series is not None:
        tax_last = last_value(tax_expense_series)
        pretax_last = last_value(pretax_series)
        if pretax_last and pretax_last > 0:
            tr = tax_last / pretax_last
            if 0 <= tr <= 0.5:
                tax_rate = tr

    normalized_tax_rate = normalize_tax_rate(
        financials,
        fallback_rate=tax_rate if tax_rate is not None else 0.21,
    )

    info = getattr(tk, "fast_info", {}) or {}
    legacy_info = getattr(tk, "info", {}) or {}

    market_cap = float(info.get("market_cap") or legacy_info.get("marketCap") or 0.0)
    if not math.isfinite(market_cap) or market_cap < 0:
        market_cap = 0.0
    shares_outstanding = float(info.get("shares_outstanding") or legacy_info.get("sharesOutstanding") or 0.0)
    beta_raw = legacy_info.get("beta") or info.get("beta")
    beta_raw = float(beta_raw) if beta_raw is not None else 1.0

    short_debt_series = get_row(balance, "Short Long Term Debt")
    long_debt_series = get_row(balance, "Long Term Debt")
    total_debt = 0.0
    for s in (short_debt_series, long_debt_series):
        v = last_value(s)
        if v is not None:
            total_debt += v

    cash_series = get_row(balance, "Cash")
    cash_last = last_value(cash_series) or 0.0
    net_debt = total_debt - cash_last

    interest_expense_series = get_row(financials, "Interest Expense")
    interest_expense_last = last_non_na_value(interest_expense_series) or 0.0
    risk_free = NORMALIZED_RISK_FREE
    market_premium = NORMALIZED_MARKET_PREMIUM
    debt_equity_ratio = 0.0
    if market_cap > 0:
        debt_equity_ratio = total_debt / market_cap if market_cap > 0 else 0.0
    elif total_debt > 0:
        debt_equity_ratio = 5.0

    beta_unlevered = compute_unlevered_beta(beta_raw, debt_equity_ratio, normalized_tax_rate)
    beta_relevered = compute_relevered_beta(beta_unlevered, debt_equity_ratio, normalized_tax_rate)
    beta_adjusted = shrink_beta(beta_relevered)
    cost_of_equity = compute_cost_of_equity(beta_adjusted, risk_free, market_premium)
    cost_of_debt = compute_cost_of_debt(
        interest_expense_last,
        total_debt,
        risk_free,
        ebit_last,
        leverage_ratio=debt_equity_ratio,
    )
    cost_of_debt_after_tax = cost_of_debt * (1.0 - normalized_tax_rate)

    V = market_cap + total_debt
    if V > 0:
        equity_weight = market_cap / V
    else:
        equity_weight = 1.0
    equity_weight = _clamp(equity_weight, 0.70, 0.98)
    debt_weight = 1.0 - equity_weight

    wacc_auto = compute_wacc(
        cost_of_equity,
        cost_of_debt_after_tax,
        market_cap,
        total_debt,
    )

    growth_model = "Mature Stable"
    if revenue_cagr_5y is not None:
        if revenue_cagr_5y >= 0.10:
            growth_model = "High Growth"
        elif revenue_cagr_5y >= 0.04:
            growth_model = "Established Growth"

    fcf_series = get_fcf_series(financials, cashflow)
    fcf_list = series_to_json_list(fcf_series)

    invested_capital_history = compute_invested_capital(financials, balance)
    roic_history = compute_roic(
        financials,
        balance,
        normalized_tax_rate,
        invested_capital_history,
    )
    nopat_history = compute_nopat_history(financials, normalized_tax_rate)
    base_year_fcff = compute_base_year_fcff(
        financials,
        cashflow,
        balance,
        normalized_tax_rate,
        fallback_series=fcf_series,
    )
    base_fcf_value = base_year_fcff if _is_finite_number(base_year_fcff) else None
    if base_fcf_value is None:
        recent_reported_fcf = last_non_na_value(fcf_series)
        if _is_finite_number(recent_reported_fcf):
            base_fcf_value = recent_reported_fcf
    if base_fcf_value is None:
        ocf_last = last_non_na_value(ocf_series)
        capex_last = last_non_na_value(capex_series)
        if _is_finite_number(ocf_last) and _is_finite_number(capex_last):
            base_fcf_value = ocf_last - capex_last

    base_year = None
    try:
        first_col = financials.columns[0]
        base_year = int(str(first_col)[:4])
    except Exception:
        base_year = None

    derived = {
        "revenueCAGR5Y": revenue_cagr_5y,
        "revenueLast": revenue_last,
        "ebitLast": ebit_last,
        "ebitMarginLast": ebit_margin_last,
        "capexToSales": capex_to_sales,
        "deltaWCToSales": delta_wc_to_sales,
        "taxRate": tax_rate,
        "netDebt": net_debt,
        "marketCap": market_cap,
        "sharesOutstanding": shares_outstanding,
        "beta": beta_relevered,
        "riskFreeRate": risk_free,
        "marketPremium": market_premium,
        "costOfEquity": cost_of_equity,
        "costOfDebt": cost_of_debt,
        "costOfDebtPreTax": cost_of_debt,
        "equityWeight": equity_weight,
        "debtWeight": debt_weight,
        "waccAuto": wacc_auto,
        "growthModelSuggestion": growth_model,
        "betaAdjusted": beta_adjusted,
        "costOfDebtAfterTax": cost_of_debt_after_tax,
    }
    derived["costOfCapital"] = {
        "riskFreeRate": risk_free,
        "marketRiskPremium": market_premium,
        "betaRaw": beta_raw,
        "betaUnlevered": beta_unlevered,
        "betaRelevered": beta_relevered,
        "betaAdjusted": beta_adjusted,
        "costOfEquity": cost_of_equity,
        "costOfDebt": cost_of_debt,
        "costOfDebtPreTax": cost_of_debt,
        "costOfDebtAfterTax": cost_of_debt_after_tax,
        "equityWeight": equity_weight,
        "debtWeight": debt_weight,
        "wacc": wacc_auto,
    }
    nopat_history_list = _history_dict_to_list(nopat_history, "nopat")
    invested_capital_history_list = _history_dict_to_list(invested_capital_history, "investedCapital")
    roic_history_list = _history_dict_to_list(roic_history, "roic")
    derived["metrics"] = {
        "normalizedTaxRate": normalized_tax_rate,
        "nopatHistory": nopat_history_list,
        "investedCapitalHistory": invested_capital_history_list,
        "roicHistory": roic_history_list,
        "baseYearFcffNormalized": base_year_fcff,
        "baseFcf": base_fcf_value,
        "fcfSeries": fcf_list,
    }

    engine_param = request.query_params.get("engine") if request is not None else None
    scenario_param = request.query_params.get("scenario") if request is not None else None
    growth_model_param = request.query_params.get("growthModel") if request is not None else None
    valid_scenarios = {s.value for s in ScenarioPreset}
    if scenario_param:
        scenario_param = scenario_param.lower()
        if scenario_param not in valid_scenarios:
            scenario_param = ScenarioPreset.BASE.value
    else:
        scenario_param = ScenarioPreset.BASE.value
    if not growth_model_param:
        growth_model_param = growth_model
    if engine_param and engine_param.lower() == "v2":
        metrics_payload = {
            "revenueLast": revenue_last,
            "ebitMarginLast": ebit_margin_last,
            "marginHistory": margin_history,
            "revenueCAGR5Y": revenue_cagr_5y,
            "normalizedTaxRate": normalized_tax_rate,
            "netDebt": net_debt,
            "sharesOutstanding": shares_outstanding,
            "baseYear": base_year,
            "roicHistory": roic_history_list,
            "baseYearFcffNormalized": base_year_fcff,
            "baseFcf": base_fcf_value,
            "fcfSeries": fcf_list,
            "nopatHistory": nopat_history_list,
            "growthModel": growth_model_param or growth_model,
        }
        if not _is_finite_number(base_fcf_value):
            derived["valuationV2"] = {
                "error": "no_base_fcf",
                "message": "No usable free cash flow available for this ticker.",
            }
        else:
            try:
                valuation_v2 = run_dcf_v2(
                    metrics_payload,
                    derived.get("costOfCapital"),
                    scenario=scenario_param,
                )
                if valuation_v2 is not None:
                    derived["valuationV2"] = valuation_v2
            except DCFComputationError as exc:
                message = str(exc)
                error_code = "no_base_fcf" if "no_base_fcf" in message else "valuation_unavailable"
                logger.warning("DCF v2 unavailable for %s: %s", ticker, exc)
                derived["valuationV2"] = {
                    "error": error_code,
                    "message": message,
                }
            except Exception as exc:
                logger.exception("DCF v2 failed for %s", ticker)
                derived["valuationV2"] = {
                    "error": "valuation_failed",
                    "message": "DCF v2 could not be computed for this ticker.",
                }

    return {
        "ticker": ticker_clean,
        "baseYear": base_year,
        "derived": derived,
        "fcfSeries": fcf_list,
    }
