import Ionicons from '@expo/vector-icons/Ionicons';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { EstimateView } from '../../components/EstimateView';
import { Button, Card, Label } from '../../components/ui';
import { deleteItem, getItem, Item, patchItem, photoUrl } from '../../lib/api';
import { range } from '../../lib/format';
import { useSettings } from '../../lib/settings';
import { colors, font } from '../../lib/theme';

export default function ItemScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { settings } = useSettings();
  const [item, setItem] = useState<Item | null>(null);
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getItem(settings, Number(id))
      .then((i) => {
        setItem(i);
        setNotes(i.notes ?? '');
      })
      .catch((e) => setError(e.message));
  }, [id, settings]);

  const update = async (patch: Partial<Item>) => {
    try {
      setItem(await patchItem(settings, Number(id), patch));
    } catch (e: any) {
      Alert.alert('Erreur', e.message);
    }
  };

  const remove = () =>
    Alert.alert('Retirer cette pièce ?', 'Elle sera supprimée de votre collection.', [
      { text: 'Annuler', style: 'cancel' },
      {
        text: 'Retirer',
        style: 'destructive',
        onPress: async () => {
          await deleteItem(settings, Number(id));
          router.back();
        },
      },
    ]);

  if (error) return <Text style={[styles.body, { padding: 24 }]}>{error}</Text>;
  if (!item) return <ActivityIndicator style={{ marginTop: 48 }} size="large" color={colors.brass} />;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Card style={{ backgroundColor: colors.brassLight, borderColor: colors.brass }}>
        <Label>Dans ma collection</Label>
        <View style={styles.qtyRow}>
          <Text style={styles.body}>Quantité</Text>
          <View style={styles.stepper}>
            <Pressable
              accessibilityLabel="Moins"
              style={styles.stepButton}
              onPress={() => item.quantity > 1 && update({ quantity: item.quantity - 1 })}
            >
              <Ionicons name="remove" size={28} color={colors.brassDark} />
            </Pressable>
            <Text style={styles.qty}>{item.quantity}</Text>
            <Pressable
              accessibilityLabel="Plus"
              style={styles.stepButton}
              onPress={() => update({ quantity: item.quantity + 1 })}
            >
              <Ionicons name="add" size={28} color={colors.brassDark} />
            </Pressable>
          </View>
        </View>
        {item.quantity > 1 && (
          <Text style={styles.body}>
            Total : {range((item.value_low ?? 0) * item.quantity, (item.value_high ?? 0) * item.quantity, item.value_currency)}
          </Text>
        )}
        <TextInput
          style={styles.notes}
          placeholder="Notes (provenance, prix d’achat…)"
          placeholderTextColor={colors.muted}
          multiline
          value={notes}
          onChangeText={setNotes}
          onBlur={() => notes !== (item.notes ?? '') && update({ notes })}
        />
      </Card>

      {item.estimate ? (
        <EstimateView
          est={{ ...item.estimate, already_owned: 0 }}
          photos={[photoUrl(settings, item.photo_front), photoUrl(settings, item.photo_back)]}
        />
      ) : (
        <Text style={styles.title}>{item.title}</Text>
      )}

      <Button title="Retirer de ma collection" variant="danger" onPress={remove} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, gap: 16, paddingBottom: 48 },
  title: { fontSize: font.title, fontWeight: '800', color: colors.text },
  body: { fontSize: font.body, color: colors.text },
  qtyRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  stepButton: {
    width: 56,
    height: 56,
    borderRadius: 28,
    borderWidth: 2,
    borderColor: colors.brass,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.card,
  },
  qty: { fontSize: font.title, fontWeight: '800', minWidth: 36, textAlign: 'center', color: colors.text },
  notes: {
    minHeight: 80,
    fontSize: font.body,
    backgroundColor: colors.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 12,
    color: colors.text,
  },
});
