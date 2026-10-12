export function money(value: number | null | undefined, currency: string, digits = 0): string {
  if (value == null) return '—';
  return new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function range(low: number | null | undefined, high: number | null | undefined, currency: string): string {
  if (low == null || high == null) return '—';
  if (Math.round(low) === Math.round(high)) return money(low, currency);
  return `${money(low, currency)} – ${money(high, currency)}`;
}

export const METALS_FR: Record<string, string> = {
  gold: 'Or',
  silver: 'Argent',
  platinum: 'Platine',
  palladium: 'Palladium',
  billon: 'Billon',
  copper: 'Cuivre',
  bronze: 'Bronze',
  nickel: 'Nickel',
  aluminium: 'Aluminium',
  steel: 'Acier',
  zinc: 'Zinc',
  other: 'Autre',
  unknown: 'Inconnu',
};

export const GRADES_FR: Record<string, string> = {
  B: 'B — Beau',
  TB: 'TB — Très Beau',
  TTB: 'TTB — Très Très Beau',
  SUP: 'SUP — Superbe',
  SPL: 'SPL — Splendide',
  FDC: 'FDC — Fleur de Coin',
  unknown: 'Non évalué',
};

export function confidenceLabel(c: number): { text: string; tone: 'success' | 'warning' | 'danger' } {
  if (c >= 0.8) return { text: 'Identification sûre', tone: 'success' };
  if (c >= 0.5) return { text: 'Identification probable', tone: 'warning' };
  return { text: 'Identification incertaine', tone: 'danger' };
}

export function sourceLabel(source: string): string {
  return source === 'gadoury' ? 'Gadoury' : source;
}
