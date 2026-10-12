import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Button, Card, Label } from '../../components/ui';
import { detectLanguage, errorText, LANGUAGES, LanguageSetting, useI18n } from '../../i18n';
import { health } from '../../lib/api';
import { number } from '../../lib/format';
import { CURRENCIES, useSettings } from '../../lib/settings';
import { colors, font } from '../../lib/theme';

function Chips<T extends string>({
  options,
  value,
  onChange,
  testIDPrefix,
}: {
  options: { key: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  testIDPrefix: string;
}) {
  return (
    <View style={styles.chips}>
      {options.map((o) => (
        <Pressable
          key={o.key}
          testID={`${testIDPrefix}-${o.key}`}
          accessibilityRole="radio"
          accessibilityState={{ selected: value === o.key }}
          onPress={() => onChange(o.key)}
          style={[styles.chip, value === o.key && styles.chipActive]}
        >
          <Text style={[styles.chipText, value === o.key && { color: '#fff' }]}>{o.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export default function SettingsScreen() {
  const { settings, save } = useSettings();
  const { m, locale } = useI18n();
  const [apiUrl, setApiUrl] = useState(settings.apiUrl);
  const [token, setToken] = useState(settings.token);
  const [status, setStatus] = useState<string | null>(null);

  const languages: { key: LanguageSetting; label: string }[] = [
    { key: 'auto', label: m.settings.automatic(LANGUAGES[detectLanguage()].name) },
    ...Object.entries(LANGUAGES).map(([key, l]) => ({ key: key as LanguageSetting, label: l.name })),
  ];

  const test = async () => {
    const next = { ...settings, apiUrl: apiUrl.replace(/\/+$/, ''), token };
    save(next);
    setStatus(m.settings.connecting);
    try {
      const h = await health(next);
      setStatus(m.settings.connected(number(h.catalog_coins, locale)));
    } catch (e) {
      setStatus(errorText(e, m));
    }
  };

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      automaticallyAdjustKeyboardInsets
      keyboardShouldPersistTaps="handled"
    >
      <Card>
        <Label>{m.settings.language}</Label>
        <Chips
          options={languages}
          value={settings.language}
          onChange={(language) => save({ language })}
          testIDPrefix="language"
        />
      </Card>

      <Card>
        <Label>{m.settings.currency}</Label>
        <Chips
          options={CURRENCIES.map((c) => ({ key: c, label: c }))}
          value={settings.currency}
          onChange={(currency) => save({ currency })}
          testIDPrefix="currency"
        />
      </Card>

      <Card>
        <Label>{m.settings.server}</Label>
        <TextInput
          testID="server-url"
          selectTextOnFocus
          clearButtonMode="while-editing"
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
          placeholder={m.settings.token}
        />
        <Button testID="server-save" title={m.settings.saveTest} onPress={test} />
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
