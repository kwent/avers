import * as ImagePicker from 'expo-image-picker';
import { router, Stack } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, ScrollView, View } from 'react-native';
import { Button, CoinWell, Press, T } from '../components/ui';
import { useI18n } from '../i18n';
import { toUploadJpeg } from '../lib/images';
import { resetScan, scan } from '../lib/scanStore';
import { colors } from '../theme';

type Side = 'front' | 'back';

/** Pick each side of the coin explicitly instead of relying on multi-selection order. */
export default function PickScreen() {
  const { m } = useI18n();
  const [photos, setPhotos] = useState<Record<Side, string | null>>({
    front: null,
    back: null,
  });
  const [loading, setLoading] = useState<Side | null>(null);

  const choose = async (side: Side) => {
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.9,
    });
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
      <View className="gap-1">
        <Press
          testID={`pick-${side}`}
          accessibilityRole="button"
          accessibilityLabel={`${title}. ${uri ? m.pick.change : m.pick.choose}`}
          onPress={() => choose(side)}
          className="flex-row items-center gap-4 rounded-md bg-surface p-4 active:bg-raised"
        >
          {loading === side ? (
            <View className="h-[104px] w-[104px] items-center justify-center">
              <ActivityIndicator color={colors.gold} />
            </View>
          ) : (
            <CoinWell size={104} uri={uri} icon="add" />
          )}
          <View className="flex-1 gap-0.5">
            <T variant="heading">{title}</T>
            <T variant="small" tone="soft">
              {hint}
            </T>
            <T variant="smallStrong" tone="accent" className="mt-1">
              {uri ? m.pick.change : m.pick.choose}
            </T>
          </View>
        </Press>
        {uri && side === 'back' && (
          <View className="self-end">
            <Button title={m.pick.remove} variant="quiet" onPress={() => setPhotos((p) => ({ ...p, back: null }))} />
          </View>
        )}
      </View>
    );
  };

  return (
    <ScrollView contentContainerClassName="gap-4 p-gutter">
      <Stack.Screen options={{ title: m.pick.title }} />
      <T>{m.pick.intro}</T>
      {slot('front', m.pick.front, m.pick.frontHint)}
      {slot('back', m.pick.back, m.pick.backHint)}
      <Button title={m.pick.analyze} onPress={analyze} disabled={!photos.front} />
    </ScrollView>
  );
}
