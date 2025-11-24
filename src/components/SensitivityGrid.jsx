export function SensitivityGrid({ baseInputs }) {
  const validInputs =
    baseInputs &&
    Array.isArray(baseInputs.fcffForecast) &&
    baseInputs.fcffForecast.length > 0 &&
    Number.isFinite(baseInputs.wacc) &&
    Number.isFinite(baseInputs.terminalGrowth) &&
    Number.isFinite(baseInputs.netDebt) &&
    Number.isFinite(baseInputs.sharesOutstanding) &&
    baseInputs.sharesOutstanding > 0

  if (!validInputs) {
    return (
      <p className="sensitivity-grid__empty">
        Run a valuation to see sensitivity analysis.
      </p>
    )
  }

  const fcffSeries = baseInputs.fcffForecast.map((row) =>
    Number.isFinite(row?.fcff) ? row.fcff : 0,
  )
  const horizon = fcffSeries.length
  const lastFcff = horizon > 0 ? fcffSeries[horizon - 1] : 0
  const baseWacc = baseInputs.wacc
  const baseTerminalGrowth = baseInputs.terminalGrowth
  const netDebt = baseInputs.netDebt
  const shares = baseInputs.sharesOutstanding

  const waccValues = [
    Math.max(0.02, baseWacc - 0.02),
    Math.max(0.02, baseWacc - 0.01),
    baseWacc,
    baseWacc + 0.01,
    baseWacc + 0.02,
  ]
  const growthValues = [
    Math.max(0.01, baseTerminalGrowth - 0.005),
    Math.max(0.01, baseTerminalGrowth - 0.0025),
    baseTerminalGrowth,
    baseTerminalGrowth + 0.0025,
    baseTerminalGrowth + 0.005,
  ]

  const computePrice = (testWacc, testGrowth) => {
    try {
      const pvCashFlows = fcffSeries.reduce((sum, fcff, index) => {
        const year = index + 1
        const discount = 1 / Math.pow(1 + testWacc, year)
        return sum + fcff * discount
      }, 0)
      const spread = Math.max(testWacc - testGrowth, 0.03)
      const terminalValue = lastFcff * (1 + testGrowth) / spread
      const pvTerminal = terminalValue / Math.pow(1 + testWacc, horizon)
      const enterpriseValue = pvCashFlows + pvTerminal
      const equityValue = enterpriseValue - netDebt
      const price = equityValue / shares
      return Number.isFinite(price) ? price : null
    } catch (error) {
      console.error('Sensitivity scenario failed', error)
      return null
    }
  }

  const tableData = waccValues.map((testWacc) => {
    const prices = growthValues.map((testGrowth) => computePrice(testWacc, testGrowth))
    return { wacc: testWacc, prices }
  })

  const formatPercent = (value) => `${(value * 100).toFixed(1)}%`
  const formatPrice = (value) =>
    value === null
      ? 'N/A'
      : `$${value.toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })}`

  return (
    <div className="sensitivity-grid">
      <table className="data-table sensitivity-grid__table">
        <thead className="data-table__header sensitivity-grid__header">
          <tr>
            <th>WACC \\ Terminal Growth</th>
            {growthValues.map((growth) => (
              <th key={growth}>{formatPercent(growth)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tableData.map((row) => (
            <tr key={row.wacc} className="data-table__row sensitivity-grid__row">
              <td className="data-table__cell sensitivity-grid__cell">
                <strong>{formatPercent(row.wacc)}</strong>
              </td>
              {row.prices.map((price, index) => {
                const growth = growthValues[index]
                const isBase =
                  Math.abs(row.wacc - baseWacc) < 1e-8 &&
                  Math.abs(growth - baseTerminalGrowth) < 1e-8
                const cellClass = [
                  'data-table__cell',
                  'sensitivity-grid__cell',
                  isBase ? 'sensitivity-grid__cell--base' : '',
                ]
                  .filter(Boolean)
                  .join(' ')
                return (
                  <td key={`${row.wacc}-${growth}`} className={cellClass}>
                    {formatPrice(price)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="sensitivity-grid__legend">
        Each cell shows the implied share price for the intersection of WACC (rows) and terminal
        growth (columns). Center cell highlights the current assumptions.
      </p>
    </div>
  )
}
