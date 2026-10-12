import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { I18nProvider, useI18n } from '../i18n';
import { SettingsProvider } from '../lib/settings';
import { colors, font } from '../lib/theme';

function Navigator() {
  const { m } = useI18n();
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: colors.bg },
        headerTintColor: colors.brassDark,
        headerTitleStyle: { fontSize: font.large, color: colors.text },
        headerBackTitle: m.common.back,
        contentStyle: { backgroundColor: colors.bg },
      }}
    >
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="scan" options={{ headerShown: false, presentation: 'fullScreenModal' }} />
      <Stack.Screen name="result" options={{ title: m.result.title }} />
      <Stack.Screen name="item/[id]" options={{ title: m.item.title }} />
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <SettingsProvider>
      <I18nProvider>
        <StatusBar style="dark" />
        <Navigator />
      </I18nProvider>
    </SettingsProvider>
  );
}
