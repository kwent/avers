import { useState } from 'react';
import { ScrollView, TextInput, View } from 'react-native';
import { Button, Row, Section, T } from '../../components/ui';
import { detectLanguage, errorText, LANGUAGES, LanguageSetting, suggestedCurrency, useI18n } from '../../i18n';
import { health } from '../../lib/api';
import { number } from '../../lib/format';
import { CURRENCIES, useSettings } from '../../lib/settings';

const input = 'mb-2 rounded-sm bg-ground px-3 py-3 font-regular text-body text-cream';

const CURRENCY_NAMES: Record<string, string> = {
  EUR: '€',
  CHF: 'CHF',
  USD: '$',
  GBP: '£',
  CAD: '$ CA',
};

export default function SettingsScreen() {
  const { settings, save } = useSettings();
  const { m, locale, language } = useI18n();
  const [apiUrl, setApiUrl] = useState(settings.apiUrl);
  const [token, setToken] = useState(settings.token);
  const [status, setStatus] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(false);

  const languages: { key: LanguageSetting; label: string }[] = [
    {
      key: 'auto',
      label: m.settings.automatic(LANGUAGES[detectLanguage()].name),
    },
    ...Object.entries(LANGUAGES).map(([key, l]) => ({
      key: key as LanguageSetting,
      label: l.name,
    })),
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
      contentContainerClassName="gap-6 p-gutter pb-8"
      automaticallyAdjustKeyboardInsets
      keyboardShouldPersistTaps="handled"
    >
      <Section title={m.settings.language}>
        {languages.map((l) => (
          <Row
            key={l.key}
            testID={`language-${l.key}`}
            accessibilityRole="radio"
            label={l.label}
            selected={settings.language === l.key}
            onPress={() => save({ language: l.key })}
          />
        ))}
      </Section>

      <Section title={m.settings.currency}>
        <Row
          testID="currency-auto"
          accessibilityRole="radio"
          label={m.settings.automatic(suggestedCurrency(language))}
          selected={settings.currency === 'auto'}
          onPress={() => save({ currency: 'auto' })}
        />
        {CURRENCIES.map((c) => (
          <Row
            key={c}
            testID={`currency-${c}`}
            accessibilityRole="radio"
            label={c}
            value={
              <T tone="soft" className="flex-1 text-right">
                {CURRENCY_NAMES[c]}
              </T>
            }
            selected={settings.currency === c}
            onPress={() => save({ currency: c })}
          />
        ))}
      </Section>

      {/* development only: production builds have the server built in and get the access code from the link */}
      {__DEV__ && (
        <Section footer={advanced ? undefined : m.settings.serverHint}>
          <Row
            testID="server-toggle"
            label={m.settings.server}
            chevron={!advanced}
            onPress={() => setAdvanced((a) => !a)}
          />
          {advanced && (
            <View className="gap-2 p-4">
              <T variant="small" tone="soft">
                {m.settings.serverUrl}
              </T>
              <TextInput
                testID="server-url"
                selectTextOnFocus
                clearButtonMode="while-editing"
                className={input}
                value={apiUrl}
                onChangeText={setApiUrl}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="url"
                placeholder="https://…"
              />
              <T variant="small" tone="soft">
                {m.settings.token}
              </T>
              <TextInput
                testID="server-token"
                className={input}
                value={token}
                onChangeText={setToken}
                autoCapitalize="none"
                autoCorrect={false}
                secureTextEntry
              />
              <Button testID="server-save" title={m.settings.saveTest} onPress={test} />
              {status && <T accessibilityLiveRegion="polite">{status}</T>}
            </View>
          )}
        </Section>
      )}
    </ScrollView>
  );
}
