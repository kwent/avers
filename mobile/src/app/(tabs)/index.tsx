import Ionicons from '@expo/vector-icons/Ionicons';
import { router } from 'expo-router';
import { ScrollView, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Band, Button, CoinWell, Row, Section, T } from '../../components/ui';
import { useI18n } from '../../i18n';
import { resetScan } from '../../lib/scanStore';
import { colors } from '../../theme';

const TIP_ICONS = ['contrast-outline', 'sunny-outline', 'radio-button-on-outline'] as const;

export default function ScannerHome() {
  const { m } = useI18n();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const well = Math.min(232, Math.min(width, 600) * 0.58);

  const shoot = () => {
    resetScan();
    router.push('/scan');
  };

  return (
    <ScrollView contentContainerClassName="pb-8">
      <Band className="items-center gap-6 pb-8" style={{ paddingTop: insets.top + 24 }}>
        <T variant="smallStrong" tone="gold" className="tracking-widest">
          Avers
        </T>
        <View className="max-w-[480px] gap-2">
          <T variant="title" tone="ink" accessibilityRole="header" className="text-center">
            {m.home.title}
          </T>
          <T tone="soft" className="text-center">
            {m.home.subtitle}
          </T>
        </View>
        <CoinWell
          size={well}
          icon="camera"
          label={m.home.takePhotoShort}
          accessibilityLabel={m.home.takePhoto}
          onPress={shoot}
          testID="home-shoot"
          glow
        />
      </Band>

      <View className="gap-6 p-gutter">
        <Button
          title={m.home.fromLibrary}
          variant="secondary"
          icon="images-outline"
          onPress={() => router.push('/pick')}
        />
        <Section title={m.home.tipsTitle}>
          {m.home.tips.map((tip, i) => (
            <Row
              key={tip}
              label={tip}
              leading={<Ionicons name={TIP_ICONS[i] ?? 'ellipse-outline'} size={26} color={colors.gold} />}
            />
          ))}
        </Section>
      </View>
    </ScrollView>
  );
}
