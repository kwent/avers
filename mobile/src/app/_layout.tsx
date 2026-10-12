import '../../global.css';
import { Lexend_400Regular, Lexend_600SemiBold, Lexend_700Bold, useFonts } from '@expo-google-fonts/lexend';
import Ionicons from '@expo/vector-icons/Ionicons';
import { router, Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { Platform, Pressable } from 'react-native';
import { T } from '../components/ui';
import { I18nProvider, useI18n } from '../i18n';
import { SettingsProvider } from '../lib/settings';
import { colors, fonts, headerTitleStyle } from '../theme';

SplashScreen.preventAutoHideAsync().catch(() => {});

/**
 * Web: the stack header draws no back button, and the home-screen web app has no browser bar, so add one. Falls back to
 * the home tab when there is no history (page opened directly).
 */
function WebBack({ label }: { label: string }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))}
      className="min-h-touch flex-row items-center gap-1 px-3"
    >
      <Ionicons name="chevron-back" size={26} color={colors.gold} />
      <T variant="bodyStrong" tone="gold">
        {label}
      </T>
    </Pressable>
  );
}

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
        ...(Platform.OS === 'web' && { headerLeft: () => <WebBack label={m.common.back} /> }),
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
