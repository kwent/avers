import Ionicons from '@expo/vector-icons/Ionicons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Haptics from 'expo-haptics';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button } from '../components/ui';
import { useI18n } from '../i18n';
import { FrameStatus, frameCheck } from '../lib/api';
import { scan } from '../lib/scanStore';
import { useSettings } from '../lib/settings';
import { colors, font } from '../lib/theme';

const CIRCLE = 0.8; // circle diameter as a fraction of screen width
const PADDING = 1.1; // crop 10% beyond the circle (the API's frame check assumes this)
const OUTPUT = 1400; // px, square, final photo
const CHECK_SIZE = 480; // px, square, live frame check
const CHECK_INTERVAL = 500; // ms between live checks
const OK_STREAK = 2; // consecutive good frames before the automatic shot

// Virtual multi-camera devices switch to the ultra-wide lens for close-up (macro) focus,
// like Apple's Camera app; the default wide lens cannot focus on a coin held close.
const PREFERRED_LENSES = [/triple/i, /dual wide/i, /dual/i];

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function ScanScreen() {
  const { m } = useI18n();
  const { settings } = useSettings();
  const [permission, requestPermission] = useCameraPermissions();
  const camera = useRef<CameraView>(null);
  const { width: W, height: H } = useWindowDimensions();
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
    const scale = Math.max(W / w, H / h);
    const side = Math.min(w, h, ((CIRCLE * W) / scale) * PADDING);
    const image = await ImageManipulator.manipulate(uri)
      .crop({ originX: (w - side) / 2, originY: (h - side) / 2, width: side, height: side })
      .resize({ width: Math.min(size, Math.round(side)) })
      .renderAsync();
    return (await image.saveAsync({ format: SaveFormat.JPEG, compress })).uri;
  };

  const capture = async () => {
    if (!camera.current || capturing.current) return;
    capturing.current = true;
    setBusy(true);
    try {
      const photo = await camera.current.takePictureAsync({ quality: 0.9 });
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
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
    } finally {
      capturing.current = false;
      setBusy(false);
    }
  };

  const onReady = async () => {
    setReady(true);
    try {
      const lenses = (await camera.current?.getAvailableLensesAsync()) ?? [];
      const best = PREFERRED_LENSES.map((re) => lenses.find((l) => re.test(l))).find(Boolean);
      if (best) setLens(best);
    } catch {
      // Android / older devices: keep the default lens
    }
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
        try {
          const photo = await camera.current.takePictureAsync({ quality: 0.5, shutterSound: false });
          if (cancelled || capturing.current) continue;
          const uri = await cropToGuide(photo.uri, photo.width, photo.height, CHECK_SIZE, 0.7);
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

  if (!permission) return <View style={styles.black} />;
  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.permission}>
        <Text style={styles.permissionText}>{m.scan.permission}</Text>
        <Button title={m.scan.allowCamera} onPress={requestPermission} />
        <Button title={m.common.cancel} variant="secondary" onPress={() => router.back()} />
      </SafeAreaView>
    );
  }

  const d = CIRCLE * W;
  const ringColor = status === 'ok' ? colors.success : status ? colors.warning : colors.brassLight;
  const guidance = status ? m.scan.guide[status] : m.scan.hint;

  return (
    <View style={styles.black}>
      <CameraView
        ref={camera}
        style={StyleSheet.absoluteFill}
        facing="back"
        autofocus="on"
        selectedLens={lens}
        enableTorch={torch}
        onCameraReady={onReady}
      />

      {/* dim everything outside the circle */}
      <View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.center]}>
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

      <SafeAreaView style={styles.overlay} edges={['top', 'bottom']}>
        <View style={styles.topBar}>
          <Pressable accessibilityLabel={m.scan.close} onPress={() => router.back()} style={styles.iconButton}>
            <Ionicons name="close" size={34} color="#fff" />
          </Pressable>
          <Pressable
            accessibilityLabel={torch ? m.scan.torchOff : m.scan.torchOn}
            onPress={() => setTorch((t) => !t)}
            style={styles.iconButton}
          >
            <Ionicons name={torch ? 'flashlight' : 'flashlight-outline'} size={30} color="#fff" />
          </Pressable>
        </View>

        <View style={styles.instructions}>
          <Text style={styles.step}>{m.scan.step(step === 'front' ? 1 : 2)}</Text>
          <Text style={styles.prompt}>{step === 'front' ? m.scan.promptFront : m.scan.promptBack}</Text>
        </View>

        <View style={styles.bottom}>
          <View style={[styles.guidance, { borderColor: ringColor }]}>
            <Text style={styles.guidanceText} accessibilityLiveRegion="polite">
              {guidance}
            </Text>
          </View>
          <View style={styles.bottomBar}>
            <View style={styles.side} />
            <Pressable accessibilityLabel={m.scan.shoot} onPress={capture} style={styles.shutter} disabled={busy}>
              {busy ? <ActivityIndicator color={colors.brass} size="large" /> : <View style={styles.shutterInner} />}
            </Pressable>
            <View style={styles.side}>
              {step === 'back' && (
                <Pressable onPress={() => router.replace('/result')} style={styles.skip}>
                  <Text style={styles.skipText}>{m.scan.skip}</Text>
                </Pressable>
              )}
            </View>
          </View>
        </View>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  black: { flex: 1, backgroundColor: '#000' },
  center: { alignItems: 'center', justifyContent: 'center' },
  overlay: { flex: 1, justifyContent: 'space-between' },
  topBar: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 16 },
  iconButton: { width: 56, height: 56, alignItems: 'center', justifyContent: 'center' },
  instructions: { alignItems: 'center', gap: 4, position: 'absolute', top: 110, left: 0, right: 0 },
  step: { color: colors.brassLight, fontSize: font.body, fontWeight: '700' },
  prompt: { color: '#fff', fontSize: font.title, fontWeight: '800', textAlign: 'center', paddingHorizontal: 20 },
  bottom: { gap: 16 },
  guidance: {
    alignSelf: 'center',
    backgroundColor: 'rgba(0,0,0,0.6)',
    borderWidth: 2,
    borderRadius: 999,
    paddingHorizontal: 20,
    paddingVertical: 10,
    marginHorizontal: 20,
  },
  guidanceText: { color: '#fff', fontSize: font.large, fontWeight: '700', textAlign: 'center' },
  bottomBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 24, paddingBottom: 16 },
  side: { width: 90, alignItems: 'center' },
  shutter: {
    width: 88,
    height: 88,
    borderRadius: 44,
    borderWidth: 5,
    borderColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
  },
  shutterInner: { width: 68, height: 68, borderRadius: 34, backgroundColor: colors.brass },
  skip: { padding: 12 },
  skipText: { color: '#fff', fontSize: font.large, fontWeight: '700' },
  permission: { flex: 1, backgroundColor: colors.bg, padding: 24, gap: 16, justifyContent: 'center' },
  permissionText: { fontSize: font.large, color: colors.text, textAlign: 'center', marginBottom: 12 },
});
