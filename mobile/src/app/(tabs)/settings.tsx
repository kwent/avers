import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Button, Card, Label } from '../../components/ui';
import { health } from '../../lib/api';
import { CURRENCIES, useSettings } from '../../lib/settings';
import { colors, font } from '../../lib/theme';

export default function SettingsScreen() {
  const { settings, save } = useSettings();
  const [apiUrl, setApiUrl] = useState(settings.apiUrl);
  const [token, setToken] = useState(settings.token);
  const [status, setStatus] = useState<string | null>(null);

  const test = async () => {
    const next = { ...settings, apiUrl: apiUrl.replace(/\/+$/, ''), token };
    save(next);
    setStatus('Connexion…');
    try {
      const h = await health(next);
      setStatus(`Connecté ✓ (${h.catalog_coins.toLocaleString('fr-FR')} pièces au catalogue)`);
    } catch (e: any) {
      setStatus(e.message);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Card>
        <Label>Devise</Label>
        <View style={styles.chips}>
          {CURRENCIES.map((c) => (
            <Pressable
              key={c}
              onPress={() => save({ currency: c })}
              style={[styles.chip, settings.currency === c && styles.chipActive]}
            >
              <Text style={[styles.chipText, settings.currency === c && { color: '#fff' }]}>{c}</Text>
            </Pressable>
          ))}
        </View>
      </Card>

      <Card>
        <Label>Serveur</Label>
        <TextInput
          style={styles.input}
          value={apiUrl}
          onChangeText={setApiUrl}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          placeholder="http://192.168.1.10:8000"
        />
        <TextInput
          style={styles.input}
          value={token}
          onChangeText={setToken}
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
          placeholder="Code d’accès (optionnel)"
        />
        <Button title="Enregistrer et tester" onPress={test} />
        {status && <Text style={styles.status}>{status}</Text>}
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, gap: 16 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  chip: { borderWidth: 2, borderColor: colors.brass, borderRadius: 999, paddingHorizontal: 18, paddingVertical: 10 },
  chipActive: { backgroundColor: colors.brass },
  chipText: { fontSize: font.body, fontWeight: '700', color: colors.brassDark },
  input: {
    fontSize: font.body,
    backgroundColor: colors.bg,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 14,
    color: colors.text,
  },
  status: { fontSize: font.body, color: colors.text },
});
