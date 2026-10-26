// AuraCoin amounts arrive in minor units (1 AC = 100), like paise for rupees.
export function formatAC(minor: number, { compact = false }: { compact?: boolean } = {}): string {
  const ac = minor / 100
  const digits = Number.isInteger(ac) ? 0 : 2
  const text = compact && Math.abs(ac) >= 10_000
    ? new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 }).format(ac)
    : new Intl.NumberFormat('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: 2 }).format(ac)
  return `${text} AC`
}

export function formatINR(rupees: number): string {
  if (rupees >= 1e7) return `₹${trim(rupees / 1e7)} Cr`
  if (rupees >= 1e5) return `₹${trim(rupees / 1e5)} L`
  return `₹${new Intl.NumberFormat('en-IN').format(rupees)}`
}

function trim(value: number): string {
  return value.toFixed(2).replace(/\.?0+$/, '')
}
