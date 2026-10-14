import { PermissionResponse, PermissionStatus, useCameraPermissions } from 'expo-camera';
import { Image } from 'react-native';

/**
 * One camera stream for the whole visit. Safari asks for the camera again on each getUserMedia call once the previous
 * stream has stopped (every time in a home-screen app), and expo-camera opens and closes a stream for the permission
 * check and for each scan. So the first request opens the back camera once, and every later request (expo-camera's
 * included) gets a copy of it: closing a copy leaves the camera granted. The shared track is switched off while no
 * scan uses it.
 */
let shared: MediaStream | null = null;
let users = 0;
const live = () => shared?.getVideoTracks()[0]?.readyState === 'live';

if (typeof navigator !== 'undefined' && navigator.mediaDevices?.getUserMedia) {
  const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia = async (constraints?: MediaStreamConstraints) => {
    if (!constraints?.video || constraints.audio) return original(constraints);
    if (!live()) {
      // the app only ever shoots with the back camera, at a size that can read a date
      shared = await original({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      });
    }
    const source = shared!.getVideoTracks()[0];
    source.enabled = true;
    users++;
    const copy = shared!.clone();
    for (const track of copy.getTracks()) {
      const stop = track.stop.bind(track);
      let stopped = false;
      track.stop = () => {
        stop();
        if (stopped) return;
        stopped = true;
        if (--users === 0) source.enabled = false;
      };
    }
    return copy;
  };
}

/**
 * The camera permission. Safari may answer "ask" to a permission query even after the camera was allowed: while the
 * shared stream is open, the camera is allowed.
 */
export function useCameraAccess(): ReturnType<typeof useCameraPermissions> {
  const [permission, request, get] = useCameraPermissions();
  const granted: PermissionResponse = {
    status: PermissionStatus.GRANTED,
    granted: true,
    canAskAgain: true,
    expires: 'never',
  };
  return [live() ? granted : permission, request, get];
}

/** Browsers cannot drive the torch. */
export const CAN_TORCH = false;

/** Browsers pick the camera themselves. */
export const bestLens = async (_camera: unknown): Promise<string | undefined> => undefined;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * expo-camera opens the stream without a resolution, so browsers fall back to about 640×480, too coarse to read a
 * date. Ask the running stream for Full HD (the browser picks the closest it can do).
 */
export async function tuneStream() {
  let stream: unknown;
  // onCameraReady fires before expo-camera attaches the stream to the <video>
  for (let i = 0; i < 20 && !(stream instanceof MediaStream); i++) {
    stream = document.querySelector('video')?.srcObject;
    if (!(stream instanceof MediaStream)) await sleep(100);
  }
  const track = stream instanceof MediaStream ? stream.getVideoTracks()[0] : undefined;
  try {
    await track?.applyConstraints({ width: { ideal: 1920 }, height: { ideal: 1080 } });
    await sleep(300); // let the new frame size reach the video element
  } catch {
    // keep the default resolution
  }
}

/** Size of a captured photo: expo-camera reports the stream's (landscape on phones), not the portrait frame's. */
export const capturedSize = (uri: string, _width: number, _height: number) =>
  new Promise<[number, number]>((resolve, reject) => Image.getSize(uri, (w, h) => resolve([w, h]), reject));
