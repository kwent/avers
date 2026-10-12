import { Image } from 'react-native';

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
