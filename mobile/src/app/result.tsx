import Ionicons from '@expo/vector-icons/Ionicons';
import * as Haptics from 'expo-haptics';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { EstimateView } from '../components/EstimateView';
import { Button, Card } from '../components/ui';
import { addItem, estimate, Estimate } from '../lib/api';
import { resetScan, scan } from '../lib/scanStore';
import { useSettings } from '../lib/settings';
import { colors, font } from '../lib/theme';

export default function ResultScreen() {
  const { settings } = useSettings();
  const [est, setEst] = useState<Estimate | null>(scan.estimate);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const run = () => {
    if (!scan.front) return setError('Aucune photo.');
    setError(null);
    estimate(settings, scan.front, scan.back)
      .then((e) => {
        scan.estimate = e;
        setEst(e);
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      })
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    if (!est) run();
  }, []);

  const save = async () => {
    if (!est) return;
    setSaving(true);
    try {
      const item = await addItem(settings, est);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      resetScan();
      router.dismissAll();
      router.push({ pathname: '/item/[id]', params: { id: String(item.id) } });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (error) {
    return (
      <View style={styles.center}>
        <Ionicons name="alert-circle" size={64} color={colors.danger} />
        <Text style={styles.message}>{error}</Text>
        <Button title="Réessayer" onPress={run} />
        <Button title="Reprendre les photos" variant="secondary" onPress={() => router.replace('/scan')} />
      </View>
    );
  }

  if (!est) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.brass} />
        <Text style={styles.message}>Analyse de la pièce…</Text>
        <Text style={styles.hint}>Identification, recherche des prix et cours du métal. Cela prend environ 30 secondes.</Text>
      </View>
    );
  }

  if (!est.identification.is_coin) {
    return (
      <View style={styles.center}>
        <Ionicons name="help-circle" size={64} color={colors.warning} />
        <Text style={styles.message}>Je ne vois pas de pièce sur cette photo.</Text>
        <Button title="Reprendre les photos" onPress={() => router.replace('/scan')} />
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <EstimateView est={est} photos={[scan.front ?? undefined, scan.back ?? undefined]} />
      <Button
        title="Ajouter à ma collection"
        icon={<Ionicons name="add-circle" size={28} color="#fff" />}
        onPress={save}
        loading={saving}
        style={{ minHeight: 72 }}
      />
      <Button title="Scanner une autre pièce" variant="secondary" onPress={() => router.replace('/scan')} />
      <Card style={{ backgroundColor: 'transparent', borderWidth: 0, padding: 0 }}>
        <Text style={styles.hint}>
          Estimation indicative basée sur des prix de marchands et le cours du métal. Pour une vente, faites expertiser la
          pièce.
        </Text>
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, gap: 16, paddingBottom: 48 },
  center: { flex: 1, padding: 24, gap: 16, justifyContent: 'center', alignItems: 'stretch' },
  message: { fontSize: font.large, fontWeight: '700', color: colors.text, textAlign: 'center' },
  hint: { fontSize: font.small, color: colors.muted, textAlign: 'center', lineHeight: 22 },
});
