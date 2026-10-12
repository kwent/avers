import Ionicons from '@expo/vector-icons/Ionicons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Haptics from 'expo-haptics';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, Platform, Pressable, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button, Press, T } from '../components/ui';
import { useI18n } from '../i18n';
import { FrameStatus, frameCheck } from '../lib/api';
import { scan } from '../lib/scanStore';
import { useSettings } from '../lib/settings';
import { colors } from '../theme';

const CIRCLE = 0.8; // circle diameter as a fraction of screen width
const CIRCLE_MAX_HEIGHT = 0.44; // ...but at most this fraction of the height, to leave room for the texts
const PADDING = 1.1; // crop 10% beyond the circle (the API's frame check assumes this)
const OUTPUT = 1400; // px, square, final photo
const CHECK_SIZE = 480; // px, square, live frame check
const CHECK_INTERVAL = 500; // ms between live checks
const OK_STREAK = 2; // consecutive good frames before the automatic shot

// Virtual multi-camera devices switch to the ultra-wide lens for close-up (macro) focus,
// like Apple's Camera app; the default wide lens cannot focus on a coin held close.
const PREFERRED_LENSES = [/triple/i, /dual wide/i, /dual/i];

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** The session is (re)starting, e.g. right after a lens switch: retry instead of failing. */
const isNotReady = (e: unknown) => String(e).includes('CameraNotReady');

const imageSize = (uri: string) =>
  new Promise<[number, number]>((resolve, reject) => Image.getSize(uri, (w, h) => resolve([w, h]), reject));

export default function ScanScreen() {
  const { m } = useI18n();
  const { settings } = useSettings();
  const [permission, requestPermission] = useCameraPermissions();
  const camera = useRef<CameraView>(null);
  const { width: W, height: H } = useWindowDimensions();
  const guide = Math.min(CIRCLE * W, CIRCLE_MAX_HEIGHT * H); // on-screen circle diameter
  const [step, setStep] = useState<'front' | 'back'>('front');
  const [torch, setTorch] = useState(false);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [lens, setLens] = useState<string | undefined>();
  const [status, setStatus] = useState<FrameStatus | null>(null);
  const capturing = useRef(false);
  // After a shot the same coin is still in frame: wait for a change before shooting again.
  const armed = useRef(true);

  // Crop the photo to the square around the on-screen circle (preview is "cover"-scaled).
  const cropToGuide = async (uri: string, w: number, h: number, size: number, compress: number) => {
    // web: expo-camera reports the stream's size (landscape on phones), not the captured portrait frame's
    if (Platform.OS === 'web') [w, h] = await imageSize(uri);
    const scale = Math.max(W / w, H / h);
    const side = Math.min(w, h, (guide / scale) * PADDING);
    const image = await ImageManipulator.manipulate(uri)
      .crop({
        originX: (w - side) / 2,
        originY: (h - side) / 2,
        width: side,
        height: side,
      })
      .resize({ width: Math.min(size, Math.round(side)) })
      .renderAsync();
    return (await image.saveAsync({ format: SaveFormat.JPEG, compress })).uri;
  };

  const takePicture = async (options: { quality: number; shutterSound?: boolean }) => {
    for (let attempt = 0; ; attempt++) {
      try {
        const photo = await camera.current?.takePictureAsync(options);
        if (!photo) throw new Error('CameraNotReady: no camera');
        return photo;
      } catch (e) {
        if (!isNotReady(e) || attempt >= 5) throw e;
        await sleep(300);
      }
    }
  };

  const capture = async () => {
    if (!camera.current || capturing.current || !ready) return;
    capturing.current = true;
    setBusy(true);
    try {
      const photo = await takePicture({ quality: 0.9 });
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {}); // no haptics on the web
      const uri = await cropToGuide(photo.uri, photo.width, photo.height, OUTPUT, 0.88);
      armed.current = false;
      setStatus(null);
      if (step === 'front') {
        scan.front = uri;
        setStep('back');
      } else {
        scan.back = uri;
        router.replace('/result');
      }
    } catch (e) {
      console.warn('capture failed', e);
    } finally {
      capturing.current = false;
      setBusy(false);
    }
  };

  // Choose the lens first: switching it restarts the session, and photos taken meanwhile fail.
  const onReady = async () => {
    if (lens === undefined) {
      try {
        const lenses = (await camera.current?.getAvailableLensesAsync()) ?? [];
        const best = PREFERRED_LENSES.map((re) => lenses.find((l) => re.test(l))).find(Boolean);
        if (best) {
          setLens(best);
          await sleep(800); // let the session settle on the new lens
        }
      } catch {
        // Android / older devices: keep the default lens
      }
    }
    setReady(true);
  };

  // Live guidance: grab a small silent frame, ask the API whether it is good, shoot when it is.
  useEffect(() => {
    if (!permission?.granted || !ready) return;
    let cancelled = false;
    let streak = 0;
    (async () => {
      while (!cancelled) {
        await sleep(CHECK_INTERVAL);
        if (cancelled || capturing.current || !camera.current) continue;
        let uri: string;
        try {
          const photo = await takePicture({
            quality: 0.5,
            shutterSound: false,
          });
          if (cancelled || capturing.current) continue;
          uri = await cropToGuide(photo.uri, photo.width, photo.height, CHECK_SIZE, 0.7);
        } catch {
          continue; // camera busy or restarting: try again next tick
        }
        try {
          const res = await frameCheck(settings, uri);
          if (cancelled || capturing.current) continue;
          setStatus(res.status);
          if (res.status !== 'ok') armed.current = true;
          streak = res.status === 'ok' && armed.current ? streak + 1 : 0;
          if (streak >= OK_STREAK) {
            streak = 0;
            await capture();
          }
        } catch {
          // API unreachable or too old: fall back to manual shooting without guidance
          setStatus(null);
          return;
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [permission?.granted, ready, step, settings]);

  if (!permission) return <View className="flex-1 bg-black" />;
  if (!permission.granted) {
    return (
      <SafeAreaView className="flex-1 justify-center gap-4 bg-ground p-gutter">
        <T variant="heading" className="mb-3 text-center">
          {m.scan.permission}
        </T>
        <Button title={m.scan.allowCamera} onPress={requestPermission} />
        <Button title={m.common.cancel} variant="secondary" onPress={() => router.back()} />
      </SafeAreaView>
    );
  }

  const d = guide;
  const ringColor = status === 'ok' ? '#5CC97A' : status ? '#F2B84B' : colors.cream;
  const guidance = status ? m.scan.guide[status] : m.scan.hint;

  return (
    <View className="flex-1 bg-black">
      <CameraView
        ref={camera}
        style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
        facing="back"
        autofocus="on"
        selectedLens={lens}
        enableTorch={torch}
        onCameraReady={onReady}
      />

      {/* dim everything outside the circle */}
      <View pointerEvents="none" className="absolute inset-0 items-center justify-center">
        <View
          testID="guide-ring"
          style={{
            width: d,
            height: d,
            borderRadius: d / 2,
            borderWidth: status === 'ok' ? 7 : 4,
            borderColor: ringColor,
            boxShadow: `0 0 0 ${Math.max(W, H)}px rgba(0,0,0,0.55)`,
          }}
        />
      </View>

      <SafeAreaView className="flex-1 justify-between" edges={['top', 'bottom']}>
        <View className="flex-row justify-between px-4">
          <Pressable
            accessibilityLabel={m.scan.close}
            onPress={() => router.back()}
            className="h-14 w-14 items-center justify-center"
          >
            <Ionicons name="close" size={34} color="#fff" />
          </Pressable>
          {Platform.OS !== 'web' && ( // browsers cannot drive the torch
            <Pressable
              accessibilityLabel={torch ? m.scan.torchOff : m.scan.torchOn}
              onPress={() => setTorch((t) => !t)}
              className="h-14 w-14 items-center justify-center"
            >
              <Ionicons name={torch ? 'flashlight' : 'flashlight-outline'} size={30} color="#fff" />
            </Pressable>
          )}
        </View>

        {/* above the circle, whatever the screen height */}
        <View className="absolute left-0 right-0 items-center gap-1 px-gutter" style={{ bottom: (H + d) / 2 + 16 }}>
          <T variant="bodyStrong" tone="soft">
            {m.scan.step(step === 'front' ? 1 : 2)}
          </T>
          <T variant="title" className="text-center text-white">
            {step === 'front' ? m.scan.promptFront : m.scan.promptBack}
          </T>
        </View>

        <View className="gap-4">
          <View
            className="mx-gutter self-center rounded-full border-2 bg-well/85 px-gutter py-3"
            style={{ borderColor: ringColor }}
          >
            <T variant="heading" className="text-center text-white" accessibilityLiveRegion="polite">
              {guidance}
            </T>
          </View>
          <View className="flex-row items-center justify-between px-6 pb-4">
            <View className="w-[90px] items-center" />
            <Press
              accessibilityLabel={m.scan.shoot}
              onPress={capture}
              disabled={busy || !ready}
              scaleTo={0.92}
              className={`h-[88px] w-[88px] items-center justify-center rounded-full border-[5px] border-white ${ready ? '' : 'opacity-50'}`}
            >
              {busy ? (
                <ActivityIndicator color="#fff" size="large" />
              ) : (
                <View className="h-[68px] w-[68px] rounded-full bg-white" />
              )}
            </Press>
            <View className="w-[90px] items-center">
              {step === 'back' && (
                <Pressable onPress={() => router.replace('/result')} className="p-3">
                  <T variant="button" className="text-white">
                    {m.scan.skip}
                  </T>
                </Pressable>
              )}
            </View>
          </View>
        </View>
      </SafeAreaView>
    </View>
  );
}
