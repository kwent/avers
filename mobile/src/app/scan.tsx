import Ionicons from '@expo/vector-icons/Ionicons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Haptics from 'expo-haptics';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { router } from 'expo-router';
import { useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button } from '../components/ui';
import { scan } from '../lib/scanStore';
import { colors, font } from '../lib/theme';

const CIRCLE = 0.8; // circle diameter as a fraction of screen width
const OUTPUT = 1400; // px, square

export default function ScanScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const camera = useRef<CameraView>(null);
  const { width: W, height: H } = useWindowDimensions();
  const [step, setStep] = useState<'front' | 'back'>('front');
  const [torch, setTorch] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!permission) return <View style={styles.black} />;
  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.permission}>
        <Text style={styles.permissionText}>Avers a besoin de l’appareil photo pour photographier vos pièces.</Text>
        <Button title="Autoriser l’appareil photo" onPress={requestPermission} />
        <Button title="Annuler" variant="secondary" onPress={() => router.back()} />
      </SafeAreaView>
    );
  }

  // Crop the photo to the square around the on-screen circle (preview is "cover"-scaled).
  const cropToCircle = async (uri: string, w: number, h: number) => {
    const scale = Math.max(W / w, H / h);
    const side = Math.min(w, h, ((CIRCLE * W) / scale) * 1.1);
    const ctx = ImageManipulator.manipulate(uri)
      .crop({ originX: (w - side) / 2, originY: (h - side) / 2, width: side, height: side })
      .resize({ width: Math.min(OUTPUT, Math.round(side)) });
    const image = await ctx.renderAsync();
    const saved = await image.saveAsync({ format: SaveFormat.JPEG, compress: 0.88 });
    return saved.uri;
  };

  const capture = async () => {
    if (!camera.current || busy) return;
    setBusy(true);
    try {
      const photo = await camera.current.takePictureAsync({ quality: 0.9 });
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      const uri = await cropToCircle(photo.uri, photo.width, photo.height);
      if (step === 'front') {
        scan.front = uri;
        setStep('back');
      } else {
        scan.back = uri;
        router.replace('/result');
      }
    } finally {
      setBusy(false);
    }
  };

  const d = CIRCLE * W;
  return (
    <View style={styles.black}>
      <CameraView ref={camera} style={StyleSheet.absoluteFill} facing="back" enableTorch={torch} animateShutter />

      {/* dim everything outside the circle */}
      <View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.center]}>
        <View
          style={{
            width: d,
            height: d,
            borderRadius: d / 2,
            borderWidth: 4,
            borderColor: colors.brassLight,
            boxShadow: `0 0 0 ${Math.max(W, H)}px rgba(0,0,0,0.55)`,
          }}
        />
      </View>

      <SafeAreaView style={styles.overlay} edges={['top', 'bottom']}>
        <View style={styles.topBar}>
          <Pressable accessibilityLabel="Fermer" onPress={() => router.back()} style={styles.iconButton}>
            <Ionicons name="close" size={34} color="#fff" />
          </Pressable>
          <Pressable
            accessibilityLabel={torch ? 'Éteindre la lampe' : 'Allumer la lampe'}
            onPress={() => setTorch((t) => !t)}
            style={styles.iconButton}
          >
            <Ionicons name={torch ? 'flashlight' : 'flashlight-outline'} size={30} color="#fff" />
          </Pressable>
        </View>

        <View style={styles.instructions}>
          <Text style={styles.step}>{step === 'front' ? 'Étape 1 sur 2' : 'Étape 2 sur 2'}</Text>
          <Text style={styles.prompt}>
            {step === 'front' ? 'Photographiez le côté face' : 'Retournez la pièce : côté pile'}
          </Text>
          <Text style={styles.hint}>Placez la pièce dans le cercle</Text>
        </View>

        <View style={styles.bottomBar}>
          <View style={styles.side} />
          <Pressable accessibilityLabel="Prendre la photo" onPress={capture} style={styles.shutter} disabled={busy}>
            {busy ? <ActivityIndicator color={colors.brass} size="large" /> : <View style={styles.shutterInner} />}
          </Pressable>
          <View style={styles.side}>
            {step === 'back' && (
              <Pressable onPress={() => router.replace('/result')} style={styles.skip}>
                <Text style={styles.skipText}>Passer</Text>
              </Pressable>
            )}
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
  hint: { color: '#ddd', fontSize: font.body },
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
