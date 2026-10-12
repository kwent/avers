import { appendPhoto } from './platform/upload';
import { currencyOf } from '../i18n';
import { Settings } from './settings';

export type Grade = 'B' | 'TB' | 'TTB' | 'SUP' | 'SPL' | 'FDC' | 'unknown';

export type Identification = {
  status: 'identified' | 'not_a_coin' | 'unidentifiable';
  status_reason: string | null;
  photo_sides: ('obverse' | 'reverse' | 'unclear')[];
  title: string;
  country_iso: string | null;
  country_name: string | null;
  year: number | null;
  mint_mark: string | null;
  face_value: number | null;
  denomination: string | null;
  type_name: string | null;
  metal: string;
  fineness: number | null;
  weight_g: number | null;
  catalog_refs: string[];
  grade: Grade;
  grade_notes: string;
  confidence: number;
  authenticity_notes: string | null;
  notes: string;
};

export type Melt = {
  metal: string;
  weight_g: number;
  fineness: number;
  pure_metal_g: number;
  spot_per_gram: number;
  value: number;
  currency: string;
};

export type PricePoint = {
  source: string;
  name: string | null;
  url: string | null;
  grade: string | null;
  kind: 'listing' | 'sold';
  year: number | null;
  /** as listed, and brought to today's metal price (the premium paid then kept) */
  price: number;
  adjusted: number;
};

export type Comparable = {
  id: number;
  source: string;
  name: string;
  url: string;
  year: number | null;
  grade: string | null;
  metal: string | null;
  weight_g: number | null;
  price: number;
  currency: string;
  in_stock: number;
  listed: string;
  images: string[];
  score: number;
};

export type Valuation = {
  value_low: number;
  value_high: number;
  retail_low: number | null;
  retail_high: number | null;
  best_match_ids: number[];
  /** where the prices come from: catalog listings, or Numista's estimates when the catalog has none */
  source?: 'catalog' | 'numista';
  /** every price that went into the estimate, newest first */
  points?: PricePoint[];
  // explanation text from older saved estimates; new ones carry `basis` and the app writes the text
  explanation?: string;
  basis?: {
    listings: number;
    sold?: number;
    first_year: number | null;
    last_year: number | null;
    metal_share: number | null;
    /** few or old prices: the range reaches lower */
    low_confidence?: boolean;
  };
};

export type CatalogMatch = {
  id: number;
  source: string;
  name: string;
  url: string;
  images: string[];
  confidence: number;
  reason?: string; // older saved estimates
  criteria?: ('country' | 'year' | 'face_value' | 'mint' | 'reference' | 'photo')[];
  similarity?: number | null;
};

export type GradePrice = { grade: string; retail: number | null; resale: number | null; points: number };

export type Estimate = {
  currency: string;
  /** stored photo names, obverse first; `swapped`: the obverse was sent second */
  photos: { front: string; back: string | null; swapped?: boolean };
  photo_warning: 'same_side' | null;
  identification: Identification;
  melt: Melt | null;
  comparables: Comparable[];
  match: CatalogMatch | null;
  price_table: GradePrice[];
  valuation: Valuation | null;
  already_owned?: number;
  /** what Numista knows, looked up when the catalog has no listing of this coin */
  numista?: {
    type_id: number;
    title: string | null;
    url: string;
    years: number[];
    issue: { id: number; mintage: number | null; mint: string | null } | null;
    /** Numista's price per grade (our grade codes) */
    prices?: Record<string, number>;
  } | null;
  /** set when the year read has no catalog listing: the app asks which year the coin shows */
  year_check?: { read: number; suggestions: number[] } | null;
};

export type Item = {
  id: number;
  created_at: string;
  title: string;
  country_iso: string | null;
  year: number | null;
  denomination: string | null;
  metal: string | null;
  fineness: number | null;
  weight_g: number | null;
  grade: string | null;
  quantity: number;
  value_low: number | null;
  value_high: number | null;
  value_currency: string;
  photo_front: string | null;
  photo_back: string | null;
  notes: string | null;
  melt: Melt | null;
  estimate?: Estimate;
};

export type CollectionResponse = {
  currency: string;
  items: Item[];
  totals: {
    count: number;
    /** priced coins at their value, the others at their metal value */
    total_low: number;
    total_high: number;
    priced_count: number;
    value_low: number;
    value_high: number;
    unpriced_count: number;
    unpriced_melt: number;
    melt: number;
  };
};

/** kind 'unreachable' = network failure; 'http' carries the server's detail message when it sent one. */
export class ApiError extends Error {
  constructor(
    public kind: 'unreachable' | 'http',
    public status = 0,
    detail = '',
  ) {
    super(detail);
  }
}

async function request<T>(s: Settings, path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (s.token) headers['X-App-Token'] = s.token;
  let res: Response;
  try {
    res = await fetch(`${s.apiUrl}${path}`, { ...init, headers });
  } catch (e) {
    console.warn(`fetch ${path} failed`, e);
    throw new ApiError('unreachable');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError('http', res.status, typeof body?.detail === 'string' ? body.detail : '');
  }
  return res.json();
}

/** A stored photo; `thumb` for the small version shown in lists. */
export const photoUrl = (s: Settings, name: string | null, thumb = false) =>
  name ? `${s.apiUrl}/uploads/${name}${thumb ? '?size=thumb' : ''}` : undefined;

export async function estimate(s: Settings, front: string, back: string | null, language: string): Promise<Estimate> {
  const form = new FormData();
  await appendPhoto(form, 'front', front);
  if (back) await appendPhoto(form, 'back', back);
  form.append('currency', currencyOf(s));
  form.append('language', language);
  return request(s, '/estimate', { method: 'POST', body: form });
}

export type FrameStatus = 'ok' | 'no_coin' | 'too_dark' | 'off_center' | 'too_small' | 'too_big' | 'blurry' | 'glare';

export type FrameCheck = { status: FrameStatus; coin: { x: number; y: number; r: number } | null };

export async function frameCheck(s: Settings, uri: string): Promise<FrameCheck> {
  const form = new FormData();
  await appendPhoto(form, 'frame', uri);
  return request(s, '/frame-check', { method: 'POST', body: form });
}

export const getCollection = (s: Settings) => request<CollectionResponse>(s, `/collection?currency=${currencyOf(s)}`);

export const getItem = (s: Settings, id: number) => request<Item>(s, `/collection/${id}?currency=${currencyOf(s)}`);

/** Re-price an estimate with the year the user reads on the coin (no new photo reading). */
export const correctYear = (s: Settings, est: Estimate, year: number) =>
  request<Estimate>(s, '/estimate/year', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ estimate: est, year }),
  });

export const addItem = (s: Settings, est: Estimate, quantity = 1) =>
  request<Item>(s, '/collection', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ estimate: est, quantity }),
  });

export const patchItem = (s: Settings, id: number, patch: Partial<Item>) =>
  request<Item>(s, `/collection/${id}?currency=${currencyOf(s)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });

export const deleteItem = (s: Settings, id: number) => request(s, `/collection/${id}`, { method: 'DELETE' });

export const health = (s: Settings) => request<{ ok: boolean; catalog_coins: number }>(s, '/health');
