import Ionicons from '@expo/vector-icons/Ionicons';
import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import { router, Stack } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Button } from '../components/ui';
import { useI18n } from '../i18n';
import { toUploadJpeg } from '../lib/images';
import { resetScan, scan } from '../lib/scanStore';
import { colors, font, radius } from '../lib/theme';

type Side = 'front' | 'back';

/** Pick each side of the coin explicitly instead of relying on multi-selection order. */
export default function PickScreen() {
  const { m } = useI18n();
  const [photos, setPhotos] = useState<Record<Side, string | null>>({ front: null, back: null });
  const [loading, setLoading] = useState<Side | null>(null);

  const choose = async (side: Side) => {
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.9 });
    if (res.canceled || !res.assets[0]) return;
    setLoading(side);
    try {
      const a = res.assets[0];
      const uri = await toUploadJpeg(a.uri, a.width, a.height);
      setPhotos((p) => ({ ...p, [side]: uri }));
    } finally {
      setLoading(null);
    }
  };

  const analyze = () => {
    resetScan();
    scan.front = photos.front;
    scan.back = photos.back;
    router.replace('/result');
  };

  const slot = (side: Side, title: string, hint: string) => {
    const uri = photos[side];
    return (
      <Pressable
        testID={`pick-${side}`}
        accessibilityRole="button"
        accessibilityLabel={`${title}. ${uri ? m.pick.change : m.pick.choose}`}
        onPress={() => choose(side)}
        style={[styles.slot, uri && styles.slotFilled]}
      >
        <View style={styles.thumb}>
          {uri ? (
            <Image source={{ uri }} style={styles.thumbImg} contentFit="cover" />
          ) : (
            <Ionicons name={loading === side ? 'hourglass-outline' : 'add'} size={44} color={colors.brass} />
          )}
        </View>
        <View style={{ flex: 1, gap: 4 }}>
          <Text style={styles.slotTitle}>{title}</Text>
          <Text style={styles.slotHint}>{hint}</Text>
          <Text style={styles.slotAction}>{uri ? m.pick.change : m.pick.choose}</Text>
        </View>
        {uri && side === 'back' && (
          <Pressable
            accessibilityLabel={m.pick.remove}
            hitSlop={8}
            onPress={() => setPhotos((p) => ({ ...p, back: null }))}
            style={styles.remove}
          >
            <Ionicons name="close-circle" size={30} color={colors.muted} />
          </Pressable>
        )}
      </Pressable>
    );
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Stack.Screen options={{ title: m.pick.title }} />
      <Text style={styles.intro}>{m.pick.intro}</Text>
      {slot('front', m.pick.front, m.pick.frontHint)}
      {slot('back', m.pick.back, m.pick.backHint)}
      <Button title={m.pick.analyze} onPress={analyze} disabled={!photos.front} style={{ minHeight: 72 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, gap: 16 },
  intro: { fontSize: font.body, color: colors.text, lineHeight: 26 },
  slot: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
    padding: 16,
    borderRadius: radius,
    borderWidth: 2,
    borderStyle: 'dashed',
    borderColor: colors.brass,
    backgroundColor: colors.card,
  },
  slotFilled: { borderStyle: 'solid' },
  thumb: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: colors.brassLight,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  thumbImg: { width: 96, height: 96 },
  slotTitle: { fontSize: font.large, fontWeight: '800', color: colors.text },
  slotHint: { fontSize: font.small, color: colors.muted, lineHeight: 21 },
  slotAction: { fontSize: font.body, fontWeight: '700', color: colors.brassDark },
  remove: { alignSelf: 'flex-start' },
});
