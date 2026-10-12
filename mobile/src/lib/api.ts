import { File } from 'expo-file-system';
import { Platform } from 'react-native';
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
  // explanation text from older saved estimates; new ones carry `basis` and the app writes the text
  explanation?: string;
  basis?: { listings: number; first_year: number | null; last_year: number | null; metal_share: number | null };
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
  photos: { front: string; back: string | null };
  photo_warning: 'same_side' | null;
  identification: Identification;
  melt: Melt | null;
  comparables: Comparable[];
  match: CatalogMatch | null;
  price_table: GradePrice[];
  valuation: Valuation | null;
  valuation_error?: string;
  already_owned?: number;
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
  totals: { count: number; value_low: number; value_high: number; melt: number };
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

export const photoUrl = (s: Settings, name: string | null) => (name ? `${s.apiUrl}/uploads/${name}` : undefined);

/**
 * Add a photo to a multipart form. Native: expo/fetch (the global fetch) only takes Blob/File parts, not RN's
 * { uri, name, type } objects, so wrap the file. Web: the uri is a blob:/data: URL, read it into a Blob.
 */
async function appendPhoto(form: FormData, field: string, uri: string) {
  if (Platform.OS === 'web') {
    const blob = await (await fetch(uri)).blob();
    form.append(field, blob, `${field}.jpg`);
  } else {
    form.append(field, new File(uri));
  }
}

export async function estimate(s: Settings, front: string, back: string | null, language: string): Promise<Estimate> {
  const form = new FormData();
  await appendPhoto(form, 'front', front);
  if (back) await appendPhoto(form, 'back', back);
  form.append('currency', s.currency);
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

export const getCollection = (s: Settings) => request<CollectionResponse>(s, `/collection?currency=${s.currency}`);

export const getItem = (s: Settings, id: number) => request<Item>(s, `/collection/${id}?currency=${s.currency}`);

export const addItem = (s: Settings, est: Estimate, quantity = 1) =>
  request<Item>(s, '/collection', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ estimate: est, quantity }),
  });

export const patchItem = (s: Settings, id: number, patch: Partial<Item>) =>
  request<Item>(s, `/collection/${id}?currency=${s.currency}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });

export const deleteItem = (s: Settings, id: number) => request(s, `/collection/${id}`, { method: 'DELETE' });

export const health = (s: Settings) => request<{ ok: boolean; catalog_coins: number }>(s, '/health');
