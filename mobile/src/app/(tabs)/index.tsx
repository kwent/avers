import Ionicons from '@expo/vector-icons/Ionicons';
import * as ImagePicker from 'expo-image-picker';
import { router } from 'expo-router';
import { Alert, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Button, Card } from '../../components/ui';
import { resetScan, scan } from '../../lib/scanStore';
import { colors, font } from '../../lib/theme';

export default function ScannerHome() {
  const fromLibrary = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsMultipleSelection: true,
      selectionLimit: 2,
      quality: 0.9,
    });
    if (res.canceled) return;
    if (!res.assets.length) return Alert.alert('Aucune photo choisie');
    resetScan();
    scan.front = res.assets[0].uri;
    scan.back = res.assets[1]?.uri ?? null;
    router.push('/result');
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.hero}>
        <View style={styles.coin}>
          <Ionicons name="logo-euro" size={72} color={colors.brass} />
        </View>
        <Text style={styles.title}>Combien vaut ma pièce ?</Text>
        <Text style={styles.subtitle}>Photographiez la pièce des deux côtés. Avers l’identifie et estime sa valeur.</Text>
      </View>

      <Button
        title="Photographier une pièce"
        icon={<Ionicons name="camera" size={28} color="#fff" />}
        onPress={() => {
          resetScan();
          router.push('/scan');
        }}
        style={{ minHeight: 72 }}
      />
      <Button
        title="Choisir dans mes photos"
        variant="secondary"
        icon={<Ionicons name="images" size={26} color={colors.brassDark} />}
        onPress={fromLibrary}
      />

      <Card>
        <Text style={styles.tipTitle}>Pour une bonne photo</Text>
        <Text style={styles.tip}>• Posez la pièce sur un fond uni et sombre</Text>
        <Text style={styles.tip}>• Bonne lumière, sans reflet</Text>
        <Text style={styles.tip}>• La pièce bien au centre du cercle</Text>
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
