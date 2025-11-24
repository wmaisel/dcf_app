function formatCurrency(value) {
  if (!Number.isFinite(value)) {
    return 'N/A'
  }
  return `$${value.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`
}

function formatPercent(value) {
  if (!Number.isFinite(value)) {
    return 'N/A'
  }
  return `${(value * 100).toFixed(1)}%`
}

export function BackendDcfV2Card({ valuation }) {
  if (!valuation) {
    return null
  }

  const settings = valuation.settings || {}
  const terminalValue = valuation.terminalValue || {}
  const previewRows = Array.isArray(valuation.fcffForecast)
    ? valuation.fcffForecast.slice(0, 3)
    : []

  return (
    <div className="backend-v2-card">
      <div className="backend-v2-card__summary">
        <p>
          <strong>Implied Share Price: </strong>
          {Number.isFinite(valuation.impliedSharePrice)
            ? `$${valuation.impliedSharePrice.toFixed(2)}`
            : 'N/A'}
        </p>
        <p>
          <strong>Enterprise Value: </strong>
          {formatCurrency(valuation.enterpriseValue)}
        </p>
        <p>
          <strong>Equity Value: </strong>
          {formatCurrency(valuation.equityValue)}
        </p>
        <p>
          <strong>WACC / Terminal Growth: </strong>
          {formatPercent(settings.wacc)} / {formatPercent(settings.gTerminal)}
        </p>
      </div>
      <div className="backend-v2-card__terminal">
        <p>
          <strong>Terminal FCFF:</strong> {formatCurrency(terminalValue.fcffTerminal)}
        </p>
        <p>
          <strong>PV of Terminal Value:</strong> {formatCurrency(terminalValue.pvTv)}
        </p>
      </div>
      {previewRows.length > 0 && (
        <div className="backend-v2-card__table-wrapper">
          <table className="data-table">
            <thead className="data-table__header">
              <tr>
                <th>Year</th>
                <th>Revenue</th>
                <th>Growth</th>
                <th>FCFF</th>
                <th>PV FCFF</th>
              </tr>
            </thead>
            <tbody>
              {previewRows.map((row) => (
                <tr key={row.year} className="data-table__row">
                  <td className="data-table__cell">{row.year}</td>
                  <td className="data-table__cell">{formatCurrency(row.revenue)}</td>
                  <td className="data-table__cell">{formatPercent(row.growth)}</td>
                  <td className="data-table__cell">{formatCurrency(row.fcff)}</td>
                  <td className="data-table__cell">{formatCurrency(row.pvFcff)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
