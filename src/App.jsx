import { useState, useCallback } from 'react'
import './App.css'
import { ForecastTable } from './components/ForecastTable'
import { PVSummary } from './components/PVSummary'
import { WaccCard } from './components/WaccCard'
import { SensitivityGrid } from './components/SensitivityGrid'
import { NarrativeSection } from './components/NarrativeSection'
import { BackendDcfV2Card } from './components/BackendDcfV2Card'

// Default to the deployed Render backend; override locally with VITE_API_BASE=http://localhost:8000
const API_BASE =
  import.meta.env.VITE_API_BASE || "https://dcf-backend-3yq2.onrender.com"

const buildApiUrl = (path) => `${API_BASE}${path}`

const PLACEHOLDER = '—'

const formatCurrency = (value, fractionDigits = 0) => {
  if (!Number.isFinite(value)) {
    return PLACEHOLDER
  }
  return value.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  })
}

const formatPercent = (value, fractionDigits = 1) => {
  if (!Number.isFinite(value)) {
    return PLACEHOLDER
  }
  return `${(value * 100).toFixed(fractionDigits)}%`
}

const formatNumber = (value, fractionDigits = 0) => {
  if (!Number.isFinite(value)) {
    return PLACEHOLDER
  }
  return value.toLocaleString(undefined, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  })
}

const formatScenarioLabel = (value) => {
  if (!value) {
    return PLACEHOLDER
  }
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function App() {
  const [ticker, setTicker] = useState('AAPL')
  const [horizon, setHorizon] = useState(10)
  const [growthModel, setGrowthModel] = useState('Mature Stable')
  const [terminalGrowth, setTerminalGrowth] = useState(0.02)
  const [waccInput, setWaccInput] = useState('8.0')
  const [autoMetrics, setAutoMetrics] = useState(null)
  const [fundamentalsLoading, setFundamentalsLoading] = useState(false)
  const [metricsError, setMetricsError] = useState(null)
  const [autoGrowth, setAutoGrowth] = useState(false)
  const [autoTerminal, setAutoTerminal] = useState(false)
  const [autoWacc, setAutoWacc] = useState(false)
  const [inputsUsed, setInputsUsed] = useState(null)
  const [valuationV2, setValuationV2] = useState(null)
  const [valuationV2Loading, setValuationV2Loading] = useState(false)
  const [valuationV2Error, setValuationV2Error] = useState(null)
  const [showBackendDetails, setShowBackendDetails] = useState(true)
  const [scenarioPreset, setScenarioPreset] = useState('base')

  const fetchBackendValuation = useCallback(async (normalizedTicker) => {
    if (!normalizedTicker) {
      return
    }
    setValuationV2Loading(true)
    setValuationV2Error(null)
    try {
      const response = await fetch(
        buildApiUrl(
          `/api/company/${normalizedTicker}?engine=v2&scenario=${encodeURIComponent(
            scenarioPreset,
          )}&growthModel=${encodeURIComponent(growthModel)}`,
        ),
      )
      if (!response.ok) {
        throw new Error('Unable to fetch backend DCF v2.')
      }
      const data = await response.json()
      const derived = data?.derived || {}
      const valuation = derived?.valuationV2 || null
      if (valuation?.error) {
        setValuationV2(null)
        setInputsUsed(null)
        setValuationV2Error(
          valuation.message || 'The backend model could not compute this ticker.',
        )
        return
      }
      setValuationV2Error(null)
      setValuationV2(valuation)
      if (valuation) {
        const settings = valuation.settings || {}
        const fcffForecast = Array.isArray(valuation.fcffForecast)
          ? valuation.fcffForecast
          : []
        const netDebtValueRaw = Number(derived?.netDebt ?? 0)
        const netDebtValue = Number.isFinite(netDebtValueRaw) ? netDebtValueRaw : 0
        const sharesValueRaw = Number(derived?.sharesOutstanding ?? 1)
        const sharesValue =
          Number.isFinite(sharesValueRaw) && sharesValueRaw > 0 ? sharesValueRaw : 1
        const baseFcffNormalized =
          Number.isFinite(settings.baseFcffNormalized)
            ? settings.baseFcffNormalized
            : Number.isFinite(valuation.baseFcff)
              ? valuation.baseFcff
              : null
        const baseFcffProjection =
          Number.isFinite(settings.baseFcffProjectionStart)
            ? settings.baseFcffProjectionStart
            : baseFcffNormalized
        const waccUsed = Number.isFinite(settings.waccUsed)
          ? settings.waccUsed
          : Number.isFinite(settings.wacc)
            ? settings.wacc
            : null
        const gTerminalUsed = Number.isFinite(settings.gTerminalUsed)
          ? settings.gTerminalUsed
          : Number.isFinite(settings.gTerminal)
            ? settings.gTerminal
            : null
        const scenarioFromSettings = settings.scenarioPreset || scenarioPreset
        setInputsUsed({
          wacc: waccUsed,
          terminalGrowth: gTerminalUsed,
          horizon: settings.horizonYears ?? fcffForecast.length ?? null,
          fcffForecast,
          netDebt: netDebtValue,
          sharesOutstanding: sharesValue,
          baseFcf: baseFcffProjection,
          baseFcfNormalized: baseFcffNormalized,
          scenarioPreset: scenarioFromSettings,
          archetype: settings.archetype ?? null,
        })
      } else {
        setInputsUsed(null)
      }
    } catch (error) {
      console.error('Backend DCF v2 fetch failed', error)
      setValuationV2(null)
      setInputsUsed(null)
      setValuationV2Error('Unable to reach the backend valuation service. Please try again.')
    } finally {
      setValuationV2Loading(false)
    }
  }, [scenarioPreset, growthModel])

  async function fetchMetricsForTicker(tickerSymbol) {
    const normalizedTicker = tickerSymbol?.trim().toUpperCase()
    if (!normalizedTicker) {
      return
    }
    setValuationV2(null)
    setInputsUsed(null)
    setFundamentalsLoading(true)
    setMetricsError(null)
    try {
      const response = await fetch(buildApiUrl(`/api/company/${normalizedTicker}`))
      if (!response.ok) {
        let detail = 'Unable to fetch fundamentals.'
        try {
          const errorJson = await response.json()
          if (errorJson?.detail) detail = errorJson.detail
        } catch (error) {
          detail = 'Unable to fetch fundamentals.'
        }
        throw new Error(detail)
      }
      const data = await response.json()
      setAutoMetrics(data)
      setTicker(normalizedTicker)

      const derived = data?.derived || {}
      if (autoGrowth && derived.growthModelSuggestion) {
        setGrowthModel(derived.growthModelSuggestion)
      }
      if (
        autoWacc &&
        typeof derived.waccAuto === 'number' &&
        Number.isFinite(derived.waccAuto)
      ) {
        setWaccInput((derived.waccAuto * 100).toFixed(1))
      }
      if (autoTerminal) {
        setTerminalGrowth(0.02)
      }
    } catch (error) {
      console.error(error)
      setAutoMetrics(null)
      setValuationV2(null)
      setInputsUsed(null)
      setMetricsError(error.message || 'Failed to load fundamentals.')
    } finally {
      setFundamentalsLoading(false)
    }
  }

  const handleRunClick = useCallback(async () => {
    const normalizedTicker = ticker?.trim().toUpperCase()
    if (!normalizedTicker) {
      setMetricsError('Enter a ticker before running a valuation.')
      return
    }
    setMetricsError(null)
    if (!autoMetrics || autoMetrics?.ticker?.toUpperCase() !== normalizedTicker) {
      await fetchMetricsForTicker(normalizedTicker)
    }
    await fetchBackendValuation(normalizedTicker)
  }, [ticker, autoMetrics, fetchBackendValuation, fetchMetricsForTicker])

  const derived = autoMetrics?.derived
  const valuationReady = Boolean(valuationV2)
  const dcfResult = valuationV2
    ? {
        projected: Array.isArray(valuationV2.fcffForecast)
          ? valuationV2.fcffForecast.map((row, index) => ({
              year: row.year ?? index + 1,
              growth: row.growth ?? null,
              fcf: row.fcff ?? null,
              discountFactor: row.discountFactor ?? null,
              pvFcf: row.pvFcff ?? null,
            }))
          : [],
        terminalValue: valuationV2.terminalValue?.tv ?? null,
        pvTerminalValue: valuationV2.terminalValue?.pvTv ?? null,
        enterpriseValue: valuationV2.enterpriseValue ?? null,
        equityValue: valuationV2.equityValue ?? null,
        impliedSharePrice: valuationV2.impliedSharePrice ?? null,
        wacc:
          Number.isFinite(valuationV2.settings?.waccUsed)
            ? valuationV2.settings.waccUsed
            : valuationV2.settings?.wacc ?? null,
      }
    : null
  const currentSharePrice =
    derived &&
    Number.isFinite(derived.marketCap) &&
    Number.isFinite(derived.sharesOutstanding) &&
    derived.sharesOutstanding > 0
      ? derived.marketCap / derived.sharesOutstanding
      : null
  const currentEnterpriseValue =
    derived && Number.isFinite(derived.marketCap) && Number.isFinite(derived.netDebt)
      ? derived.marketCap + derived.netDebt
      : null
  const impliedSharePrice = Number.isFinite(valuationV2?.impliedSharePrice)
    ? valuationV2.impliedSharePrice
    : null
  const upside =
    currentSharePrice && impliedSharePrice
      ? impliedSharePrice / currentSharePrice - 1
      : null
  const upsideToneClass = Number.isFinite(upside)
    ? upside >= 0
      ? 'text-upside'
      : 'text-downside'
    : ''
  const revenueLast =
    derived && Number.isFinite(derived.revenueLast) ? derived.revenueLast : null
  const revenueCagr5Y =
    derived && Number.isFinite(derived.revenueCAGR5Y) ? derived.revenueCAGR5Y : null
  const ebitMarginLast =
    derived && Number.isFinite(derived.ebitMarginLast) ? derived.ebitMarginLast : null
  const netDebtValue = Number.isFinite(derived?.netDebt) ? derived.netDebt : null
  const sharesOutstandingValue = Number.isFinite(derived?.sharesOutstanding)
    ? derived.sharesOutstanding
    : null
  const baseFcffNormalizedValue = Number.isFinite(inputsUsed?.baseFcfNormalized)
    ? inputsUsed.baseFcfNormalized
    : null
  const baseFcffProjectionValue = Number.isFinite(inputsUsed?.baseFcf)
    ? inputsUsed.baseFcf
    : Number.isFinite(inputsUsed?.baseFcfProjectionStart)
      ? inputsUsed.baseFcfProjectionStart
      : null
  const waccUsedValue = Number.isFinite(inputsUsed?.wacc) ? inputsUsed.wacc : null
  const gTerminalUsedValue = Number.isFinite(inputsUsed?.terminalGrowth)
    ? inputsUsed.terminalGrowth
    : null
  const horizonUsedValue = Number.isFinite(inputsUsed?.horizon) ? inputsUsed.horizon : null
  const scenarioInUse = inputsUsed?.scenarioPreset ?? scenarioPreset
  const archetypeUsed = inputsUsed?.archetype ?? null
  const fcffMarginNormalized =
    Number.isFinite(baseFcffNormalizedValue) &&
    Number.isFinite(revenueLast) &&
    revenueLast !== 0
      ? baseFcffNormalizedValue / revenueLast
      : null
  const fallbackWacc =
    waccUsedValue ??
    (Number.isFinite(derived?.waccAuto) ? derived.waccAuto : Number(waccInput) / 100)
  const fallbackTerminalGrowth =
    gTerminalUsedValue ??
    (Number.isFinite(terminalGrowth) ? terminalGrowth : null)
  const forecastHorizonDisplay = Number.isFinite(horizonUsedValue)
    ? horizonUsedValue
    : horizon
  const narrativeContext = {
    ticker: autoMetrics?.ticker ?? ticker,
    scenarioPreset: scenarioInUse,
    growthModel,
    baseFcff: baseFcffProjectionValue,
    baseFcffNormalized: baseFcffNormalizedValue,
    wacc: fallbackWacc,
    terminalGrowth: fallbackTerminalGrowth,
    impliedSharePrice,
    currentSharePrice,
    upside,
    horizon: forecastHorizonDisplay,
    netDebt: netDebtValue,
    sharesOutstanding: sharesOutstandingValue,
    archetype: inputsUsed?.archetype ?? null,
    baseYear: autoMetrics?.baseYear ?? null,
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="header-text">
          <h1>Discounted Cash Flow Analysis</h1>
          <p className="subtitle">
            An automated fast track to a fine-tuned and customized DCF
          </p>
        </div>
        <p className="disclaimer">For educational use only</p>
      </header>

      <main className="app-main">
        <section className="section-container valuation-setup">
          <div className="section-header">
            <h2>Valuation Parameters</h2>
          </div>
          <div className="section-body">
            <div className="valuation-card">
              <div className="valuation-input-grid">
                <div className="valuation-field">
                  <div className="field-label-row">
                    <label htmlFor="ticker-input">Ticker</label>
                  </div>
                  <div className="field-stack">
                    <input
                      id="ticker-input"
                      type="text"
                      value={ticker}
                      onChange={(event) => {
                        const value = event.target.value.toUpperCase()
                        setTicker(value)
                        if (!value) {
                          setAutoMetrics(null)
                          setMetricsError(null)
                        }
                      }}
                      onBlur={() => {
                        if (ticker && !fundamentalsLoading) {
                          fetchMetricsForTicker(ticker)
                        }
                      }}
                    />
                    <button
                      type="button"
                      className="load-fundamentals-button"
                      onClick={() => fetchMetricsForTicker(ticker)}
                      disabled={fundamentalsLoading}
                    >
                      {fundamentalsLoading ? 'Loading…' : 'Load Fundamentals'}
                    </button>
                  </div>
                  {metricsError && <p className="error-text field-error">{metricsError}</p>}
                </div>

                <div className="valuation-field">
                  <div className="field-label-row">
                    <label htmlFor="horizon-input">Forecast Horizon (years)</label>
                  </div>
                  <input
                    id="horizon-input"
                    type="number"
                    min={1}
                    max={30}
                    value={horizon}
                    onChange={(event) => {
                      const parsed = Number(event.target.value)
                      setHorizon(Number.isFinite(parsed) ? Math.max(1, parsed) : 1)
                    }}
                  />
                </div>

                <div className="valuation-field">
                  <div className="field-label-row">
                    <label htmlFor="growth-model-select">Growth Model</label>
                    <label className="auto-toggle">
                      <input
                        type="checkbox"
                        checked={autoGrowth}
                        onChange={(event) => {
                          const checked = event.target.checked
                          setAutoGrowth(checked)
                          const derivedMetrics = autoMetrics?.derived
                          if (checked && derivedMetrics?.growthModelSuggestion) {
                            setGrowthModel(derivedMetrics.growthModelSuggestion)
                          }
                        }}
                      />
                      Auto
                    </label>
                  </div>
                  <select
                    id="growth-model-select"
                    value={growthModel}
                    onChange={(event) => setGrowthModel(event.target.value)}
                    disabled={autoGrowth}
                  >
                    <option value="Mature Stable">Mature Stable</option>
                    <option value="Established Growth">Established Growth</option>
                    <option value="High Growth">High Growth</option>
                  </select>
                </div>

                <div className="valuation-field">
                  <div className="field-label-row">
                    <label htmlFor="wacc-input">WACC (%)</label>
                    <label className="auto-toggle">
                      <input
                        type="checkbox"
                        checked={autoWacc}
                        onChange={(event) => {
                          const checked = event.target.checked
                          setAutoWacc(checked)
                          const derivedMetrics = autoMetrics?.derived
                          if (
                            checked &&
                            derivedMetrics?.waccAuto != null &&
                            Number.isFinite(derivedMetrics.waccAuto)
                          ) {
                            setWaccInput((derivedMetrics.waccAuto * 100).toFixed(1))
                          }
                        }}
                      />
                      Auto
                    </label>
                  </div>
                  <input
                    id="wacc-input"
                    type="number"
                    step="0.1"
                    value={waccInput}
                    onChange={(event) => setWaccInput(event.target.value)}
                    disabled={autoWacc}
                  />
                </div>

                <div className="valuation-field">
                  <div className="field-label-row">
                    <label htmlFor="scenario-select">Scenario</label>
                  </div>
                  <select
                    id="scenario-select"
                    value={scenarioPreset}
                    onChange={(event) => setScenarioPreset(event.target.value)}
                  >
                    <option value="conservative">Conservative</option>
                    <option value="base">Base</option>
                    <option value="optimistic">Optimistic</option>
                  </select>
                </div>

                <div className="valuation-field">
                  <div className="field-label-row">
                    <label htmlFor="terminal-growth-select">Terminal Growth</label>
                    <label className="auto-toggle">
                      <input
                        type="checkbox"
                        checked={autoTerminal}
                        onChange={(event) => {
                          const checked = event.target.checked
                          setAutoTerminal(checked)
                          if (checked) {
                            setTerminalGrowth(0.02)
                          }
                        }}
                      />
                      Auto
                    </label>
                  </div>
                  <select
                    id="terminal-growth-select"
                    value={terminalGrowth}
                    onChange={(event) => setTerminalGrowth(Number(event.target.value))}
                    disabled={autoTerminal}
                  >
                    <option value={0.02}>Conservative (2.0%)</option>
                    <option value={0.025}>Moderate (2.5%)</option>
                    <option value={0.03}>Aggressive (3.0%)</option>
                  </select>
                </div>
              </div>

              <div className="backend-toggle-row">
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={showBackendDetails}
                    onChange={(event) => setShowBackendDetails(event.target.checked)}
                  />
                  <span>Show backend valuation details</span>
                </label>
                <p className="helper-text">
                  Toggle the detailed FCFF forecast table from the backend engine.
                </p>
              </div>

              <div className="run-button-row">
                <button className="run-button" type="button" onClick={handleRunClick}>
                  Run Valuation
                </button>
              </div>
            </div>
            {autoMetrics && (
              <div className="fundamentals-card">
                <div className="fundamentals-card__header">
                  <h3>Fundamentals Snapshot: {autoMetrics.ticker}</h3>
                  {archetypeUsed && (
                    <span className="fundamentals-pill">{archetypeUsed}</span>
                  )}
                </div>
                <div className="fundamentals-grid">
                  <div className="fundamentals-group">
                    <h4>Scale &amp; Growth</h4>
                    <p className="fundamentals-metric">
                      <span>Base Year</span>
                      <strong>{autoMetrics.baseYear ?? PLACEHOLDER}</strong>
                    </p>
                    <p className="fundamentals-metric">
                      <span>Revenue (Last FY)</span>
                      <strong>{formatCurrency(revenueLast)}</strong>
                    </p>
                    <p className="fundamentals-metric">
                      <span>5Y Revenue CAGR</span>
                      <strong>{formatPercent(revenueCagr5Y)}</strong>
                    </p>
                    <p className="fundamentals-metric">
                      <span>Forecast Horizon Used</span>
                      <strong>{formatNumber(forecastHorizonDisplay)}</strong>
                    </p>
                  </div>

                  <div className="fundamentals-group">
                    <h4>Profitability &amp; Cash Flows</h4>
                    <p className="fundamentals-metric">
                      <span>EBIT Margin (Last FY)</span>
                      <strong>{formatPercent(ebitMarginLast)}</strong>
                    </p>
                    <p className="fundamentals-metric">
                      <span>Base FCFF (Normalized)</span>
                      <strong>{formatCurrency(baseFcffNormalizedValue)}</strong>
                    </p>
                    <p className="fundamentals-metric">
                      <span>Projection FCFF Start</span>
                      <strong>{formatCurrency(baseFcffProjectionValue)}</strong>
                    </p>
                    <p className="fundamentals-metric">
                      <span>FCFF Margin (Normalized)</span>
                      <strong>{formatPercent(fcffMarginNormalized)}</strong>
                    </p>
                  </div>

                  <div className="fundamentals-group">
                    <h4>Capital Structure &amp; Discounting</h4>
                    <p className="fundamentals-metric">
                      <span>Net Debt</span>
                      <strong>{formatCurrency(netDebtValue)}</strong>
                    </p>
                    <p className="fundamentals-metric">
                      <span>Shares Outstanding</span>
                      <strong>{formatNumber(sharesOutstandingValue)}</strong>
                    </p>
                    <p className="fundamentals-metric">
                      <span>WACC (Used)</span>
                      <strong>{formatPercent(fallbackWacc)}</strong>
                    </p>
                    <p className="fundamentals-metric">
                      <span>Terminal Growth (Used)</span>
                      <strong>{formatPercent(fallbackTerminalGrowth)}</strong>
                    </p>
                    <p className="fundamentals-metric">
                      <span>Scenario</span>
                      <strong>{formatScenarioLabel(scenarioInUse)}</strong>
                    </p>
                  </div>

                  <div className="fundamentals-group">
                    <h4>Valuation Context</h4>
                    <p className="fundamentals-metric">
                      <span>Current Enterprise Value</span>
                      <strong>{formatCurrency(currentEnterpriseValue)}</strong>
                    </p>
                    <p className="fundamentals-metric">
                      <span>Current Share Price</span>
                      <strong>{formatCurrency(currentSharePrice, 2)}</strong>
                    </p>
                    <p className="fundamentals-metric">
                      <span>Backend DCF Price</span>
                      <strong>{formatCurrency(impliedSharePrice, 2)}</strong>
                    </p>
                    <p className="fundamentals-metric">
                      <span>Upside / (Downside)</span>
                      <strong className={upsideToneClass}>{formatPercent(upside)}</strong>
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="section-container valuation-snapshot">
          <div className="section-header">
            <h2>Valuation Snapshot</h2>
          </div>
          <div className="section-body">
            {valuationReady ? (
              <div className="valuation-output">
                <div className="valuation-output__metric valuation-output__metric--primary">
                  <p className="valuation-output__label">Implied Share Price</p>
                  <p className="valuation-output__value">
                    {Number.isFinite(valuationV2?.impliedSharePrice)
                      ? `$${valuationV2.impliedSharePrice.toFixed(2)}`
                      : 'N/A'}
                  </p>
                </div>
                <div className="valuation-output__divider" />
                <div className="valuation-output__metric">
                  <p className="valuation-output__label">Enterprise Value</p>
                  <p className="valuation-output__value">
                    {Number.isFinite(valuationV2?.enterpriseValue)
                      ? `$${valuationV2.enterpriseValue.toLocaleString()}`
                      : 'N/A'}
                  </p>
                </div>
                {Number.isFinite(currentSharePrice) && (
                  <>
                    <div className="valuation-output__divider" />
                    <div className="valuation-output__metric">
                      <p className="valuation-output__label">Current Share Price</p>
                      <p className="valuation-output__value">{`$${currentSharePrice.toFixed(2)}`}</p>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <p>
                Run the valuation to generate backend FCFF outputs, implied fair value, and
                enterprise value insights.
              </p>
            )}
            {valuationV2Error && (
              <p className="error-text">{valuationV2Error}</p>
            )}
          </div>
        </section>

        {showBackendDetails && (
          <section className="section-container backend-v2">
            <div className="section-header">
              <h2>Analyst DCF Details</h2>
            </div>
            <div className="section-body">
              {valuationV2Loading && <p>Loading backend valuation…</p>}
              {!valuationV2Loading && valuationV2 && (
                <BackendDcfV2Card valuation={valuationV2} />
              )}
              {!valuationV2Loading && !valuationV2 && (
                <p>
                  Run the valuation to view the backend FCFF forecast and present-value detail.
                </p>
              )}
              {valuationV2Error && (
                <p className="error-text">{valuationV2Error}</p>
              )}
            </div>
          </section>
        )}

        <section className="section-container narrative-walkthrough">
          <div className="section-header">
            <h2>Insights</h2>
          </div>
          <div className="section-body">
            <NarrativeSection
              dcfResult={dcfResult ?? null}
              inputs={inputsUsed ?? null}
              derived={derived ?? null}
              insights={narrativeContext}
            />
          </div>
        </section>

        <section className="section-container dcf-details">
          <div className="section-header">
            <h2>DCF Details</h2>
          </div>
          <div className="section-body">
            <p>Forecast table, PV breakdown, and WACC context are shown below.</p>
            <ForecastTable projected={dcfResult?.projected ?? []} />
            <PVSummary dcfResult={dcfResult ?? null} />
            <WaccCard derived={derived ?? null} waccValue={inputsUsed ? inputsUsed.wacc : null} />
          </div>
        </section>

        <section className="section-container sensitivity-analysis">
          <div className="section-header">
            <h2>Sensitivity Analysis</h2>
          </div>
          <div className="section-body">
            <p>Scenario and sensitivity outputs highlight how WACC and growth shift value.</p>
            <SensitivityGrid baseInputs={inputsUsed ?? null} />
          </div>
        </section>
      </main>

      <footer className="app-footer">
        <p>Discounted Cash Flow Analysis © 2025</p>
      </footer>
    </div>
  )
}

export default App
