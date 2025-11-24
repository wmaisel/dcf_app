export function ForecastTable({ projected }) {
  if (!Array.isArray(projected) || projected.length === 0) {
    return <p className="forecast-table__empty">Run a valuation to see FCF projections.</p>
  }

  const formatPercent = (value) =>
    Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : 'N/A'

  const formatCurrency = (value) =>
    Number.isFinite(value)
      ? `$${value.toLocaleString(undefined, {
          minimumFractionDigits: 0,
          maximumFractionDigits: 0,
        })}`
      : 'N/A'

  const formatDiscount = (value) =>
    Number.isFinite(value)
      ? value.toLocaleString(undefined, {
          minimumFractionDigits: 3,
          maximumFractionDigits: 3,
        })
      : 'N/A'

  return (
    <div className="forecast-table">
      <table className="data-table">
        <thead className="data-table__header">
          <tr>
            <th>Year</th>
            <th>Growth</th>
            <th>FCF</th>
            <th>Discount Factor</th>
            <th>PV of FCF</th>
          </tr>
        </thead>
        <tbody>
          {projected.map((item, index) => (
            <tr key={item.year ?? index} className="data-table__row">
              <td className="data-table__cell">{item.year ?? index + 1}</td>
              <td className="data-table__cell">{formatPercent(item.growth)}</td>
              <td className="data-table__cell">{formatCurrency(item.fcf)}</td>
              <td className="data-table__cell">{formatDiscount(item.discountFactor)}</td>
              <td className="data-table__cell">{formatCurrency(item.pvFcf)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
