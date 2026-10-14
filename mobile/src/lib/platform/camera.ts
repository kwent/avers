import { useCameraPermissions, type CameraView } from 'expo-camera';

/** The camera permission (the system remembers it). */
export const useCameraAccess = useCameraPermissions;

/** The phone's torch can be driven from the app. */
export const CAN_TORCH = true;

// Virtual multi-camera devices switch to the ultra-wide lens for close-up (macro) focus,
// like Apple's Camera app; the default wide lens cannot focus on a coin held close.
const PREFERRED_LENSES = [/triple/i, /dual wide/i, /dual/i];

/** The lens to shoot a coin with, when the device offers a better one than the default. */
export async function bestLens(camera: CameraView | null): Promise<string | undefined> {
  try {
    const lenses = (await camera?.getAvailableLensesAsync()) ?? [];
    return PREFERRED_LENSES.map((re) => lenses.find((l) => re.test(l))).find(Boolean);
  } catch {
    return undefined; // Android / older devices: keep the default lens
  }
}

/** Once the preview runs: nothing to adjust on a phone. */
export async function tuneStream() {}

/** Size of a captured photo: what the camera reports. */
export const capturedSize = async (_uri: string, width: number, height: number): Promise<[number, number]> => [
  width,
  height,
];
