const DEFAULTS = {
  baseFcf: 100_000_000,
  horizon: 10,
  growthModel: 'Mature Stable',
  terminalGrowth: 0.02,
  wacc: 0.08,
  netDebt: 0,
  sharesOutstanding: 1_000_000_000,
  taxRate: 0.21,
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function buildGrowthPath(growthModel, horizon, terminalGrowth) {
  const growthRates = []
  const safeHorizon = Math.max(1, horizon)

  if (growthModel === 'High Growth') {
    const gStart = Math.max(0.1, terminalGrowth + 0.05)
    const transition = Math.max(1, Math.floor((safeHorizon * 2) / 3))
    for (let year = 1; year <= safeHorizon; year += 1) {
      if (year <= safeHorizon - transition) {
        growthRates.push(gStart)
      } else {
        const progress = (year - (safeHorizon - transition)) / transition
        const rate = gStart + (terminalGrowth - gStart) * progress
        growthRates.push(rate)
      }
    }
    return growthRates
  }

  if (growthModel === 'Established Growth') {
    const gStart = Math.max(0.06, terminalGrowth + 0.03)
    const half = Math.max(1, Math.floor(safeHorizon / 2))
    for (let year = 1; year <= safeHorizon; year += 1) {
      if (year <= half) {
        growthRates.push(gStart)
      } else {
        const progress = (year - half) / Math.max(1, safeHorizon - half)
        const rate = gStart + (terminalGrowth - gStart) * progress
        growthRates.push(rate)
      }
    }
    return growthRates
  }

  // Mature Stable
  const gStart = Math.min(0.04, terminalGrowth + 0.02)
  for (let year = 1; year <= safeHorizon; year += 1) {
    const progress = year / safeHorizon
    const rate = gStart + (terminalGrowth - gStart) * progress
    growthRates.push(rate)
  }
  return growthRates
}

export function runDCF(inputs = {}) {
  const baseFcf = Number.isFinite(inputs.baseFcf) ? inputs.baseFcf : DEFAULTS.baseFcf
  const horizon = Number.isFinite(inputs.horizon) ? Math.max(1, inputs.horizon) : DEFAULTS.horizon
  const growthModel = inputs.growthModel || DEFAULTS.growthModel
  let terminalGrowth = Number.isFinite(inputs.terminalGrowth) ? inputs.terminalGrowth : DEFAULTS.terminalGrowth
  let wacc = Number.isFinite(inputs.wacc) ? inputs.wacc : DEFAULTS.wacc
  const netDebt = Number.isFinite(inputs.netDebt) ? inputs.netDebt : DEFAULTS.netDebt
  const sharesOutstanding = Number.isFinite(inputs.sharesOutstanding)
    ? Math.max(1, inputs.sharesOutstanding)
    : DEFAULTS.sharesOutstanding
  const taxRate = Number.isFinite(inputs.taxRate) ? inputs.taxRate : DEFAULTS.taxRate

  if (wacc <= 0) {
    wacc = DEFAULTS.wacc
  }
  if (terminalGrowth >= wacc) {
    terminalGrowth = clamp(wacc - 0.005, -0.01, wacc - 0.001)
  }

  const growthRates = buildGrowthPath(growthModel, horizon, terminalGrowth)
  const projected = []

  let fcf = baseFcf
  let pvSum = 0

  for (let year = 1; year <= horizon; year += 1) {
    const growth = growthRates[year - 1] ?? terminalGrowth
    fcf = year === 1 ? baseFcf * (1 + growth) : fcf * (1 + growth)
    const discountFactor = 1 / Math.pow(1 + wacc, year)
    const pvFcf = fcf * discountFactor
    pvSum += pvFcf

    projected.push({
      year,
      growth,
      fcf,
      discountFactor,
      pvFcf,
    })
  }

  const lastFcf = projected.length > 0 ? projected[projected.length - 1].fcf : baseFcf
  const terminalValue = lastFcf * (1 + terminalGrowth) / (wacc - terminalGrowth)
  const pvTerminalValue = terminalValue / Math.pow(1 + wacc, horizon)
  const enterpriseValue = pvSum + pvTerminalValue
  const equityValue = enterpriseValue - netDebt
  const impliedSharePrice = equityValue / sharesOutstanding

  return {
    horizon,
    growthModel,
    terminalGrowth,
    wacc,
    baseFcf,
    projected,
    terminalValue,
    pvTerminalValue,
    enterpriseValue,
    equityValue,
    impliedSharePrice,
    taxRate,
  }
}
