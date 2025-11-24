export function PVSummary({ dcfResult }) {
  if (!dcfResult || !Array.isArray(dcfResult.projected) || dcfResult.projected.length === 0) {
    return <p className="pv-summary__empty">Run a valuation to see the PV summary.</p>
  }

  const totalPvFcf = dcfResult.projected.reduce(
    (sum, row) => (Number.isFinite(row.pvFcf) ? sum + row.pvFcf : sum),
    0,
  )

  const formatCurrency = (value) =>
    Number.isFinite(value)
      ? `$${value.toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })}`
      : 'N/A'

  return (
    <div className="pv-summary">
      <table className="data-table">
        <tbody>
          <tr className="data-table__row">
            <td className="data-table__cell">Sum of PV FCFs:</td>
            <td className="data-table__cell">{formatCurrency(totalPvFcf)}</td>
          </tr>
          <tr className="data-table__row">
            <td className="data-table__cell">PV of Terminal Value:</td>
            <td className="data-table__cell">{formatCurrency(dcfResult.pvTerminalValue)}</td>
          </tr>
          <tr className="data-table__row">
            <td className="data-table__cell">Enterprise Value:</td>
            <td className="data-table__cell">{formatCurrency(dcfResult.enterpriseValue)}</td>
          </tr>
          <tr className="data-table__row">
            <td className="data-table__cell">Equity Value:</td>
            <td className="data-table__cell">{formatCurrency(dcfResult.equityValue)}</td>
          </tr>
          <tr className="data-table__row">
            <td className="data-table__cell">Implied Share Price:</td>
            <td className="data-table__cell">
              {Number.isFinite(dcfResult.impliedSharePrice)
                ? `$${dcfResult.impliedSharePrice.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}`
                : 'N/A'}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}
