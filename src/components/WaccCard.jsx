export function WaccCard({ derived, waccValue }) {
  if (!derived && !Number.isFinite(waccValue)) {
    return <p className="wacc-card__empty">Run a valuation to see the WACC diagnostics.</p>
  }

  const formatPercent = (value) =>
    Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : 'N/A'

  const effectiveWacc = Number.isFinite(waccValue) ? waccValue : derived?.waccAuto

  return (
    <div className="wacc-card">
      <div className="wacc-card__row">
        <span>WACC:</span>
        <strong>{formatPercent(effectiveWacc)}</strong>
      </div>
      <div className="wacc-card__row">
        <span>Cost of Equity:</span>
        <span>{formatPercent(derived?.costOfEquity)}</span>
      </div>
      <div className="wacc-card__row">
        <span>Cost of Debt:</span>
        <span>{formatPercent(derived?.costOfDebt)}</span>
      </div>
      <div className="wacc-card__row">
        <span>Equity Weight:</span>
        <span>{formatPercent(derived?.equityWeight)}</span>
      </div>
      <div className="wacc-card__row">
        <span>Debt Weight:</span>
        <span>{formatPercent(derived?.debtWeight)}</span>
      </div>
    </div>
  )
}
