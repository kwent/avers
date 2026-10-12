import type { Messages } from '../i18n/fr';

export function money(value: number | null | undefined, currency: string, locale: string, digits = 0): string {
  if (value == null) return '—';
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function range(
  low: number | null | undefined,
  high: number | null | undefined,
  currency: string,
  locale: string,
): string {
  if (low == null || high == null) return '—';
  if (Math.round(low) === Math.round(high)) return money(low, currency, locale);
  return `${money(low, currency, locale)} – ${money(high, currency, locale)}`;
}

export const number = (value: number, locale: string) => value.toLocaleString(locale);

export function confidence(c: number, m: Messages): { text: string; tone: 'success' | 'warning' | 'danger' } {
  if (c >= 0.8) return { text: m.estimate.confidence.high, tone: 'success' };
  if (c >= 0.5) return { text: m.estimate.confidence.medium, tone: 'warning' };
  return { text: m.estimate.confidence.low, tone: 'danger' };
}

export const metalName = (metal: string, m: Messages) => m.metals[metal as keyof Messages['metals']] ?? metal;

/** Name of a grade code (TTB -> Très Très Beau). */
export const gradeName = (grade: string, m: Messages) => m.grades[grade as keyof Messages['grades']] ?? grade;

/** Grade as plain text, code first: "TTB (Très Très Beau)". */
export const gradeLabel = (grade: string, m: Messages) =>
  grade === 'unknown' ? gradeName(grade, m) : `${grade} (${gradeName(grade, m)})`;

export function sourceLabel(source: string): string {
  return { gadoury: 'Gadoury', numista: 'Numista' }[source] ?? source;
}
