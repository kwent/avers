import '../../global.css';
import { Lexend_400Regular, Lexend_600SemiBold, Lexend_700Bold, useFonts } from '@expo-google-fonts/lexend';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { I18nProvider, useI18n } from '../i18n';
import { SettingsProvider } from '../lib/settings';
import { colors, fonts, headerTitleStyle } from '../theme';

SplashScreen.preventAutoHideAsync().catch(() => {});

function Navigator() {
  const { m } = useI18n();
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: colors.ground },
        headerTintColor: colors.gold,
        headerTitleStyle,
        headerShadowVisible: false,
        headerBackTitle: m.common.back,
        contentStyle: { backgroundColor: colors.ground },
      }}
    >
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="scan" options={{ headerShown: false, presentation: 'fullScreenModal' }} />
      <Stack.Screen name="pick" options={{ title: m.pick.title }} />
      <Stack.Screen name="result" options={{ title: m.result.title }} />
      <Stack.Screen name="item/[id]" options={{ title: m.item.title }} />
    </Stack>
  );
}

export default function RootLayout() {
  const [loaded, failed] = useFonts({
    [fonts.regular]: Lexend_400Regular,
    [fonts.strong]: Lexend_600SemiBold,
    [fonts.heavy]: Lexend_700Bold,
  });
  const ready = loaded || !!failed; // a font failure falls back to the system font rather than a blank app

  useEffect(() => {
    if (ready) SplashScreen.hideAsync().catch(() => {});
  }, [ready]);

  if (!ready) return null;
  return (
    <SettingsProvider>
      <I18nProvider>
        <StatusBar style="light" />
        <Navigator />
      </I18nProvider>
    </SettingsProvider>
  );
}
