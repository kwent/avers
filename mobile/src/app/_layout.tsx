import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SettingsProvider } from '../lib/settings';
import { colors, font } from '../lib/theme';

export default function RootLayout() {
  return (
    <SettingsProvider>
      <StatusBar style="dark" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: colors.bg },
          headerTintColor: colors.brassDark,
          headerTitleStyle: { fontSize: font.large, color: colors.text },
          headerBackTitle: 'Retour',
          contentStyle: { backgroundColor: colors.bg },
        }}
      >
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="scan" options={{ headerShown: false, presentation: 'fullScreenModal' }} />
        <Stack.Screen name="result" options={{ title: 'Estimation' }} />
        <Stack.Screen name="item/[id]" options={{ title: 'Ma pièce' }} />
      </Stack>
    </SettingsProvider>
  );
}
