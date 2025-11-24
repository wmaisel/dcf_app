const PLACEHOLDER = 'N/A'

const formatCurrency = (value, fractionDigits = 0) => {
  if (!Number.isFinite(value)) return PLACEHOLDER
  return `$${value.toLocaleString(undefined, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  })}`
}

const formatPercent = (value, digits = 1) => {
  if (!Number.isFinite(value)) return PLACEHOLDER
  return `${(value * 100).toFixed(digits)}%`
}

const formatNumber = (value, digits = 0) => {
  if (!Number.isFinite(value)) return PLACEHOLDER
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

const formatScenario = (value) => {
  if (!value) return PLACEHOLDER
  return value.charAt(0).toUpperCase() + value.slice(1)
}

export function NarrativeSection({ dcfResult, inputs, derived, insights }) {
  if (!dcfResult || !inputs) {
    return (
      <div className="narrative-section">
        <p className="narrative-section__paragraph">
          Run a valuation to generate a narrative explanation.
        </p>
      </div>
    )
  }

  const fcffForecast = Array.isArray(inputs.fcffForecast) ? inputs.fcffForecast : []
  const costOfCapital = derived?.costOfCapital ?? {}
  const metrics = derived?.metrics ?? {}
  const fcffSeries = Array.isArray(metrics?.fcfSeries) ? metrics.fcfSeries : []

  const tickerLabel = insights?.ticker ?? PLACEHOLDER
  const scenarioLabel = formatScenario(inputs.scenarioPreset ?? insights?.scenarioPreset)
  const archetype = insights?.archetype ?? inputs.archetype ?? PLACEHOLDER
  const growthModel = insights?.growthModel ?? PLACEHOLDER
  const revenueLastValue = Number.isFinite(derived?.revenueLast) ? derived.revenueLast : null
  const ebitMarginLastValue = Number.isFinite(derived?.ebitMarginLast)
    ? derived.ebitMarginLast
    : null
  const revenueCagr5Y = Number.isFinite(derived?.revenueCAGR5Y)
    ? derived.revenueCAGR5Y
    : null
  const baseFcff = Number.isFinite(inputs.baseFcf)
    ? inputs.baseFcf
    : Number.isFinite(insights?.baseFcff)
      ? insights.baseFcff
      : null
  const baseFcffNormalized = Number.isFinite(inputs.baseFcfNormalized)
    ? inputs.baseFcfNormalized
    : Number.isFinite(insights?.baseFcffNormalized)
      ? insights.baseFcffNormalized
      : null
  const waccUsed = Number.isFinite(inputs.wacc) ? inputs.wacc : Number(insights?.wacc)
  const terminalGrowth = Number.isFinite(inputs.terminalGrowth)
    ? inputs.terminalGrowth
    : Number(insights?.terminalGrowth)
  const impliedPrice = Number.isFinite(dcfResult.impliedSharePrice)
    ? dcfResult.impliedSharePrice
    : insights?.impliedSharePrice
  const currentPrice = insights?.currentSharePrice
  const upside = insights?.upside
  const horizonYears = Number.isFinite(inputs.horizon)
    ? inputs.horizon
    : Number.isFinite(insights?.horizon)
      ? insights.horizon
      : fcffForecast.length
  const netDebt = Number.isFinite(inputs.netDebt) ? inputs.netDebt : insights?.netDebt
  const sharesOutstanding = Number.isFinite(inputs.sharesOutstanding)
    ? inputs.sharesOutstanding
    : insights?.sharesOutstanding
  const pvStage = (dcfResult.projected || []).reduce(
    (sum, row) => sum + (Number.isFinite(row.pvFcf) ? row.pvFcf : 0),
    0,
  )
  const fcffTerminal = fcffForecast[fcffForecast.length - 1]?.fcf ?? null
  const waccMinusTerminal = Number.isFinite(waccUsed) && Number.isFinite(terminalGrowth)
    ? waccUsed - terminalGrowth
    : null

  const fcffMarginNormalizedRatio =
    Number.isFinite(baseFcffNormalized) && Number.isFinite(revenueLastValue) && revenueLastValue
      ? baseFcffNormalized / revenueLastValue
      : null

  const fcffHistoryDisplay = fcffSeries.slice(0, 5).map((entry) => {
    const label = entry?.label ?? 'Year'
    const value = Number.isFinite(entry?.value) ? entry.value : null
    return `${label}: ${formatCurrency(value)}`
  })

  const fcffProjectionDisplay = [
    `Base FCFF: ${formatCurrency(baseFcff)}`,
    ...fcffForecast.slice(0, 5).map((row, index) => {
      const yearLabel = row?.year ?? index + 1
      const growthLabel = formatPercent(row?.growth ?? terminalGrowth)
      const fcffLabel = formatCurrency(row?.fcf)
      return `Year ${yearLabel} (g=${growthLabel}) → ${fcffLabel}`
    }),
  ]

  const growthPathDisplay = (() => {
    if (fcffForecast.length === 0) {
      return ['Growth path unavailable']
    }
    const firstGrowth = fcffForecast[0]?.growth
    const midGrowth = fcffForecast[Math.max(0, Math.floor(fcffForecast.length / 2))]?.growth
    const lastGrowth = fcffForecast[fcffForecast.length - 1]?.growth ?? terminalGrowth
    return [
      `Short-term acceleration: ${formatPercent(firstGrowth)} (Years 1-${Math.min(
        2,
        fcffForecast.length,
      )})`,
      `Mid-cycle fade: ${formatPercent(midGrowth)} by year ${Math.max(
        3,
        Math.floor(fcffForecast.length * 0.6),
      )}`,
      `Terminal glide: ${formatPercent(lastGrowth)} (capped to sustainable growth)`,
    ]
  })()

  const discountFactorYear1 =
    Number.isFinite(waccUsed) && waccUsed !== -1
      ? 1 / Math.pow(1 + waccUsed, 1)
      : null

  const fcffStepMetrics = []
  fcffStepMetrics.push(`Base × (1 + g₁) → ${formatCurrency(fcffForecast[0]?.fcf)}`)
  if (fcffForecast[1]) {
    fcffStepMetrics.push(`Year 2 (g=${formatPercent(fcffForecast[1]?.growth)}) → ${formatCurrency(
      fcffForecast[1]?.fcf,
    )}`)
  }
  if (fcffForecast.length > 2) {
    const index = Math.min(2, fcffForecast.length - 1)
    fcffStepMetrics.push(
      `Year ${fcffForecast[index]?.year ?? index + 1} (g=${formatPercent(
        fcffForecast[index]?.growth,
      )}) → ${formatCurrency(fcffForecast[index]?.fcf)}`,
    )
  }
  fcffStepMetrics.push(`Terminal Year FCFF → ${formatCurrency(fcffTerminal)}`)

  const fundamentalsNumbers = [
    `Revenue (Last FY): ${formatCurrency(revenueLastValue)}`,
    `EBIT Margin (Last FY): ${formatPercent(ebitMarginLastValue)}`,
    `Base Year: ${insights?.baseYear ?? PLACEHOLDER}`,
    `Shares Outstanding: ${formatNumber(sharesOutstanding)}`,
    `Net Debt: ${formatCurrency(netDebt)}`,
    `5Y Revenue CAGR: ${formatPercent(revenueCagr5Y)}`,
  ]

  const normalizationAdjustment = Number.isFinite(baseFcff) && Number.isFinite(baseFcffNormalized)
    ? baseFcff - baseFcffNormalized
    : null

  const valuationSteps = [
    {
      id: 'fundamentals',
      title: 'Company Fundamentals',
      numbers: fundamentalsNumbers,
      equations: [
        'Raw historical values pulled from yfinance via the backend; no adjustments applied at this stage.',
        'These metrics anchor scale (revenue), profitability (EBIT margin), and capital structure (shares, net debt).',
      ],
      output: 'Raw scale, profitability, and leverage inputs that seed the normalization step.',
      explanation:
        'They define the economic bounds of the company—larger revenue and stronger margins enable higher sustainable FCFF, while leverage informs how much of enterprise value belongs to equity.',
    },
    {
      id: 'normalization',
      title: 'Free Cash Flow Normalization',
      numbers: [
        `Reported FCFF history (recent): ${fcffHistoryDisplay.length > 0 ? fcffHistoryDisplay.join(' • ') : PLACEHOLDER}`,
        `Normalized FCFF median: ${formatCurrency(baseFcffNormalized)}`,
        `Scenario-tilted projection start FCFF: ${formatCurrency(baseFcff)}`,
        `Adjustment vs median: ${formatCurrency(normalizationAdjustment)}`,
        `FCFF Margin: ${formatPercent(fcffMarginNormalizedRatio)}`,
      ],
      equations: [
        'Backend logic trims outliers (>50% away from median), weights recent years more heavily, and can lean forward a slice of short-term growth when scenarios allow.',
        'No math is redone here—the frontend simply displays the normalized FCFF already computed server-side.',
      ],
      output: `Normalized base-year FCFF used as FCFF₀ = ${formatCurrency(baseFcff)}.`,
      explanation:
        'Smoothing keeps the DCF from overreacting to single-year spikes or dips and ensures projections start from a representative steady-state cash flow.',
    },
    {
      id: 'cost-of-capital',
      title: 'Cost of Capital (WACC)',
      numbers: [
        `Risk-free rate: ${formatPercent(costOfCapital.riskFreeRate)}`,
        `Equity risk premium: ${formatPercent(costOfCapital.marketRiskPremium)}`,
        `Beta (raw → adj): ${formatNumber(costOfCapital.betaRaw, 2)} → ${formatNumber(costOfCapital.betaAdjusted, 2)}`,
        `Cost of equity: ${formatPercent(costOfCapital.costOfEquity)}`,
        `Cost of debt (pre / after tax): ${formatPercent(costOfCapital.costOfDebtPreTax)} / ${formatPercent(costOfCapital.costOfDebtAfterTax)}`,
        `Capital weights (E / D): ${formatPercent(costOfCapital.equityWeight)} / ${formatPercent(costOfCapital.debtWeight)}`,
        `Final WACC (clamped): ${formatPercent(waccUsed)}`,
      ],
      equations: [
        'Cost of equity = risk-free + beta_adjusted × equity risk premium.',
        'After-tax cost of debt = pre-tax cost × (1 − normalized tax rate).',
        'WACC = equity_weight × cost_of_equity + debt_weight × after-tax cost_of_debt, then clamped to a realistic 6–11% band.',
      ],
      output: `Discount rate applied to every FCFF = ${formatPercent(waccUsed)}.`,
      explanation:
        'WACC encodes both business risk and leverage. Small changes shift the PV of both forecast and terminal cash flows, which is why the sensitivity grid centers around this number.',
    },
    {
      id: 'growth-model',
      title: 'Growth Model & Scenario',
      numbers: [
        `Growth model: ${growthModel}`,
        `Scenario preset: ${scenarioLabel}`,
        `Horizon: ${formatNumber(horizonYears)} years`,
        `Short-term growth anchor: ${formatPercent(fcffForecast[0]?.growth)}`,
        `Terminal growth clamp: ${formatPercent(terminalGrowth)}`,
      ],
      equations: [
        'Short-term growth blends FCFF and revenue CAGRs with ROIC × reinvestment and scenario nudges.',
        `Growth fades from the short-term anchor toward the terminal clamp across the ${formatNumber(
          horizonYears,
        )}-year horizon, ensuring g_terminal < WACC.`,
      ],
      output: 'A year-by-year growth path {g₁, g₂, …, g_T} that drives FCFF projections.',
      explanation:
        'Multi-phase growth lets the model capture hypergrowth ramp-down or steady compounding, instead of forcing a single CAGR across all years.',
    },
    {
      id: 'fcff-forecast',
      title: 'FCFF Forecast',
      numbers: fcffStepMetrics,
      equations: [
        'Year 1 FCFF = baseFcff × (1 + g₁).',
        'Year t FCFF = FCFF_{t−1} × (1 + g_t).',
        'No extra reinvestment penalty: FCFF is already after reinvestment.',
      ],
      output: `Complete FCFF path over ${formatNumber(horizonYears)} years feeding the PV stage.`,
      explanation:
        'Projecting FCFF focuses the DCF on cash available to all capital providers, aligning with enterprise value before subtracting net debt.',
    },
    {
      id: 'discounting',
      title: 'Discounting FCFF',
      numbers: [
        `Example discount factor (Year 1): ${
          Number.isFinite(discountFactorYear1) ? discountFactorYear1.toFixed(3) : PLACEHOLDER
        }`,
        `Sum of PV(FCFF forecast): ${formatCurrency(pvStage)}`,
        `WACC applied: ${formatPercent(waccUsed)}`,
      ],
      equations: [
        'Discount factor DF_t = 1 / (1 + WACC)^t.',
        'PV(FCFF_t) = FCFF_t × DF_t.',
        'Sum PV = Σ PV(FCFF_t) across the explicit horizon.',
      ],
      output: `Stage-one present value contribution = ${formatCurrency(pvStage)}.`,
      explanation:
        'Discounting translates future cash flows into today’s dollars. Earlier cash flows dominate because they face fewer discount periods.',
    },
    {
      id: 'terminal-value',
      title: 'Terminal Value',
      numbers: [
        `Terminal FCFF: ${formatCurrency(fcffTerminal)}`,
        `Terminal growth: ${formatPercent(terminalGrowth)}`,
        `Raw terminal value: ${formatCurrency(dcfResult.terminalValue?.tv)}`,
        `PV(Terminal Block): ${formatCurrency(dcfResult.pvTerminalValue)}`,
      ],
      equations: [
        'TV = FCFF_terminal × (1 + g_terminal) / (WACC − g_terminal), with g < WACC by design.',
        'PV_Terminal = TV / (1 + WACC)^horizon.',
      ],
      output: `Discounted terminal contribution = ${formatCurrency(dcfResult.pvTerminalValue)}.`,
      explanation:
        'The perpetual-growth block usually carries most of the value for compounding businesses. Guardrails keep it from exploding when WACC is low or growth assumptions are aggressive.',
    },
    {
      id: 'value-assembly',
      title: 'Value Assembly',
      numbers: [
        `Sum PV(FCFF): ${formatCurrency(pvStage)}`,
        `PV(Terminal): ${formatCurrency(dcfResult.pvTerminalValue)}`,
        `Enterprise value: ${formatCurrency(dcfResult.enterpriseValue)}`,
        `Net debt: ${formatCurrency(netDebt)}`,
        `Equity value: ${formatCurrency(dcfResult.equityValue)}`,
        `Implied share price: ${formatCurrency(impliedPrice, 2)}`,
        `Current share price: ${formatCurrency(currentPrice, 2)}`,
        `Upside / (Downside): ${formatPercent(upside)}`,
      ],
      equations: [
        'Enterprise Value = Σ PV(FCFF) + PV(Terminal).',
        'Equity Value = Enterprise Value − Net Debt.',
        'Implied Share Price = Equity Value / Shares Outstanding.',
        'Upside = (Implied − Current) / Current.',
      ],
      output: `Final implied fair value = ${formatCurrency(impliedPrice, 2)} per share.`,
      explanation:
        'Subtracting net debt reconciles enterprise value back to equity holders, connecting the analytical DCF to what trades in the market.',
    },
  ]

  const waccFormulaBlock = [
    `Cost of Equity = RF + β_adjusted × ERP`,
    `After-Tax Cost of Debt = CoD × (1 - TaxRate)`,
    `WACC = W_e × Cost of Equity + W_d × After-Tax Cost of Debt`,
    `Final WACC (clamped to 6–11% w/ scenario shifts) = ${formatPercent(waccUsed)}`,
  ].join('\n')

  const baseFcffReason =
    fcffSeries.length >= 3
      ? 'Median of multi-year reported FCFF (outliers down-weighted) with forward tilt when scenario presets allow.'
      : 'Normalized FCFF built from NOPAT, reinvestment, and working-capital heuristics due to sparse direct FCFF history.'

  const terminalFormulaBlock = [
    'TV = FCFF_terminal × (1 + g_terminal) / (WACC - g_terminal)',
    `FCFF_terminal (final forecast year) = ${formatCurrency(fcffTerminal)}`,
    `g_terminal (clamped to realistic GDP band) = ${formatPercent(terminalGrowth)}`,
    `Discounted TV contribution = ${formatCurrency(dcfResult.pvTerminalValue)}`,
  ].join('\n')

  return (
    <div className="narrative-section narrative-section--expanded">
      <div className="narrative-section__group">
        <h3>1. Overview: Inputs → Outputs at a Glance</h3>
        <ul className="narrative-list">
          <li>
            <strong>Ticker:</strong> {tickerLabel}
          </li>
          <li>
            <strong>Scenario / Archetype:</strong> {scenarioLabel} ({archetype})
          </li>
          <li>
            <strong>Growth model selected:</strong> {growthModel}
          </li>
          <li>
            <strong>Base FCFF used:</strong> {formatCurrency(baseFcff)}
          </li>
          <li>
            <strong>WACC:</strong> {formatPercent(waccUsed)}
          </li>
          <li>
            <strong>Terminal growth:</strong> {formatPercent(terminalGrowth)}
          </li>
          <li>
            <strong>Implied share price:</strong> {formatCurrency(impliedPrice, 2)}
          </li>
          <li>
            <strong>Current share price:</strong> {formatCurrency(currentPrice, 2)}
          </li>
          <li>
            <strong>Upside / (Downside):</strong> {formatPercent(upside)}
          </li>
          <li>
            <strong>Forecast horizon:</strong> {formatNumber(horizonYears)} years
          </li>
        </ul>
      </div>

      <div className="narrative-section__group">
        <h3>2. Inputs into Valuation</h3>
        <p>
          Each stage below shows the tangible data that feeds the model, the adjustments already
          performed by the backend, the output handed to the next stage, and why the step matters in
          the valuation chain.
        </p>
        <div className="narrative-flow">
          {valuationSteps.map((step) => (
            <div className="narrative-flow__block" key={step.id}>
              <h4>{step.title}</h4>
              {step.numbers?.length > 0 && (
                <div className="narrative-flow__section">
                  <h5>Numbers from the model</h5>
                  <ul>
                    {step.numbers.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}
              {step.equations?.length > 0 && (
                <div className="narrative-flow__section">
                  <h5>How we use them</h5>
                  <ul>
                    {step.equations.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="narrative-flow__section">
                <h5>Output</h5>
                <p>{step.output}</p>
              </div>
              <div className="narrative-flow__section">
                <h5>Why it matters</h5>
                <p>{step.explanation}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="narrative-section__group">
        <h3>3. Cost of Capital (WACC) — Fully Explained</h3>
        <p>
          The discount rate blends normalized macro inputs with company-specific beta, taxes, and
          capital structure. Raw beta ({formatNumber(costOfCapital.betaRaw, 2)}) is shrunk toward
          1.0 to avoid overstating volatility, capital weights are clamped between 70% and 98%
          equity, and cost of debt is reduced by the normalized tax rate so borrowing benefits are
          captured explicitly. Scenario knobs can also shift WACC within the 6–11% band.
        </p>
        <ul className="narrative-list">
          <li>Risk-free rate: {formatPercent(costOfCapital.riskFreeRate)}</li>
          <li>Equity risk premium: {formatPercent(costOfCapital.marketRiskPremium)}</li>
          <li>Raw beta → adjusted beta: {formatNumber(costOfCapital.betaRaw, 2)} →{' '}
            {formatNumber(costOfCapital.betaAdjusted, 2)}</li>
          <li>Cost of equity: {formatPercent(costOfCapital.costOfEquity)}</li>
          <li>
            Cost of debt (pre / after tax): {formatPercent(costOfCapital.costOfDebtPreTax)} /
            {formatPercent(costOfCapital.costOfDebtAfterTax)}
          </li>
          <li>
            Capital weights (equity / debt, clamped): {formatPercent(costOfCapital.equityWeight)} /{' '}
            {formatPercent(costOfCapital.debtWeight)}
          </li>
          <li>Final WACC: {formatPercent(waccUsed)}</li>
        </ul>
        <pre className="narrative-code-block">{waccFormulaBlock}</pre>
      </div>

      <div className="narrative-section__group">
        <h3>4. Base Year Free Cash Flow — How It’s Determined</h3>
        <p>
          The engine inspects reported FCFF history and normalized NOPAT-based cash flow to find a
          stable starting point. Working-capital spikes, capital intensity swings, and one-off
          charges are smoothed via trimmed medians before the growth model “leans forward” for
          optimistic scenarios. When projection FCFF differs from the normalized anchor, the gap
          represents the forward tilt applied after scenario adjustments.
        </p>
        <div className="narrative-callout">
          <p>
            <strong>Base FCFF chosen:</strong> {formatCurrency(baseFcff)}
          </p>
          <p>
            <strong>Normalization anchor:</strong> {formatCurrency(baseFcffNormalized)}
          </p>
          <p>
            <strong>Reason:</strong> {baseFcffReason}
          </p>
          <p>
            <strong>Adjustments applied:</strong>
          </p>
          <ul className="narrative-list narrative-list--compact">
            <li>Outliers removed if ±50% away from median.</li>
            <li>Recency weights {fcffSeries.length >= 3 ? 'favor the latest ' + Math.min(5, fcffSeries.length) + ' observations.' : 'set to 100% because history is thin.'}</li>
            <li>
              Scenario preset adds {(Number.isFinite(baseFcff) && Number.isFinite(baseFcffNormalized) && baseFcffNormalized
                ? ((baseFcff - baseFcffNormalized) / baseFcffNormalized) * 100
                : 0
              ).toFixed(1)}
              % lean forward where permitted.
            </li>
          </ul>
          <p>
            <strong>Historical FCFF series used:</strong>
          </p>
          <pre className="narrative-code-block">
            {fcffHistoryDisplay.length > 0 ? fcffHistoryDisplay.join('\n') : 'Not available'}
          </pre>
        </div>
      </div>

      <div className="narrative-section__group">
        <h3>5. Growth Path — Short → Mid → Terminal</h3>
        <p>
          Growth is archetype-driven: {growthModel} with {scenarioLabel} preset blends FCF CAGR,
          revenue trends, and ROIC × reinvestment math. Rates start at data-driven levels and fade
          toward sustainable GDP-like terminal growth, never exceeding the WACC - 2.5% safety gap.
          The fade segments are proportionate to the {formatNumber(horizonYears)}-year horizon so
          compounders receive longer high-growth windows while mature companies compress sooner.
        </p>
        <pre className="narrative-code-block">{growthPathDisplay.join('\n')}</pre>
      </div>

      <div className="narrative-section__group">
        <h3>6. FCFF Forecast — Year-by-Year Explanation</h3>
        <p>
          Each projected year compounds the prior FCFF by (1 + growthRate). Because the base is
          already a cash flow to the firm, no additional reinvestment haircut is applied. Discount
          factors use (1 + WACC)<sup>t</sup>, e.g., Year 1 factor = {Number.isFinite(discountFactorYear1)
            ? `1 / (1 + ${formatPercent(waccUsed)}) = ${discountFactorYear1.toFixed(3)}`
            : 'not available'}.
        </p>
        <pre className="narrative-code-block">{fcffProjectionDisplay.join('\n')}</pre>
      </div>

      <div className="narrative-section__group">
        <h3>7. Present Value of Cash Flows</h3>
        <p>
          Every year’s FCFF is discounted using PV = FCFF / (1 + WACC)^t. The sum of these
          discounted flows produces the stage-one value that captures explicit forecast confidence,
          while the terminal block captures value beyond the modeled horizon. Scenario presets only
          adjust the WACC and growth assumptions—they do not alter the underlying cash flow math.
        </p>
        <div className="narrative-callout">
          <p>
            <strong>Sum of PV(Forecast FCFF):</strong> {formatCurrency(pvStage)}
          </p>
          <p>
            <strong>WACC applied:</strong> {formatPercent(waccUsed)}
          </p>
        </div>
      </div>

      <div className="narrative-section__group">
        <h3>8. Terminal Value — Explanation & Assumptions</h3>
        <p>
          The final forecast year steps into a perpetual-growth regime capped by macro constraints.
          If WACC - g becomes dangerously tight, the denominator is floored at ~3.5% to avoid
          runaway valuations. Here, WACC - g = {Number.isFinite(waccMinusTerminal)
            ? formatPercent(waccMinusTerminal)
            : PLACEHOLDER}, so the denominator stays healthy while reflecting the company’s growth
          profile.
        </p>
        <pre className="narrative-code-block">{terminalFormulaBlock}</pre>
        <p>
          <strong>Enterprise value:</strong> {formatCurrency(dcfResult.enterpriseValue)}
        </p>
      </div>

      <div className="narrative-section__group">
        <h3>9. Equity Value & Implied Share Price</h3>
        <p>
          The final step subtracts net debt (or adds net cash) and divides by diluted shares to
          translate enterprise value into per-share equity value.
        </p>
        <pre className="narrative-code-block">
          {[
            `Equity Value = Enterprise Value - Net Debt`,
            `= ${formatCurrency(dcfResult.enterpriseValue)} - ${formatCurrency(netDebt)}`,
            `= ${formatCurrency(dcfResult.equityValue)}`,
            '',
            `Implied Share Price = Equity Value / Shares`,
            `= ${formatCurrency(dcfResult.equityValue)} / ${formatNumber(sharesOutstanding)}`,
            `= ${formatCurrency(impliedPrice, 2)}`,
            '',
            `Market vs. DCF: ${formatCurrency(currentPrice, 2)} → ${formatPercent(upside)} upside`,
          ].join('\n')}
        </pre>
      </div>
    </div>
  )
}
