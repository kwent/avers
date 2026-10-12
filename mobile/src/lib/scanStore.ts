// Hands the current scan between screens without serialising photos into route params.
import { Estimate } from './api';

type Scan = { front: string | null; back: string | null; estimate: Estimate | null };

export const scan: Scan = { front: null, back: null, estimate: null };

export function resetScan() {
  scan.front = null;
  scan.back = null;
  scan.estimate = null;
}
