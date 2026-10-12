import Ionicons from '@expo/vector-icons/Ionicons';
import { router } from 'expo-router';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { Button, Card } from '../../components/ui';
import { useI18n } from '../../i18n';
import { resetScan, scan } from '../../lib/scanStore';
import { colors, font } from '../../lib/theme';

export default function ScannerHome() {
  const { m } = useI18n();

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.hero}>
        <View style={styles.coin}>
          <Ionicons name="logo-euro" size={72} color={colors.brass} />
        </View>
        <Text style={styles.title}>{m.home.title}</Text>
        <Text style={styles.subtitle}>{m.home.subtitle}</Text>
      </View>

      <Button
        title={m.home.takePhoto}
        icon={<Ionicons name="camera" size={28} color="#fff" />}
        onPress={() => {
          resetScan();
          router.push('/scan');
        }}
        style={{ minHeight: 72 }}
      />
      <Button
        title={m.home.fromLibrary}
        variant="secondary"
        icon={<Ionicons name="images" size={26} color={colors.brassDark} />}
        onPress={() => router.push('/pick')}
      />

      <Card>
        <Text style={styles.tipTitle}>{m.home.tipsTitle}</Text>
        {m.home.tips.map((tip) => (
          <Text key={tip} style={styles.tip}>
            • {tip}
          </Text>
        ))}
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, gap: 16 },
  hero: { alignItems: 'center', gap: 12, paddingVertical: 16 },
  coin: {
    width: 140,
    height: 140,
    borderRadius: 70,
    backgroundColor: colors.brassLight,
    borderWidth: 4,
    borderColor: colors.brass,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: { fontSize: font.title, fontWeight: '800', color: colors.text, textAlign: 'center' },
  subtitle: { fontSize: font.body, color: colors.muted, textAlign: 'center', lineHeight: 26 },
  tipTitle: { fontSize: font.large, fontWeight: '700', color: colors.text },
  tip: { fontSize: font.body, color: colors.text, lineHeight: 28 },
});
