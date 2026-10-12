import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import * as Linking from 'expo-linking';
import { getLocales } from 'expo-localization';
import { createContext, ReactNode, useContext, useEffect, useState } from 'react';
import { Platform } from 'react-native';
import type { LanguageSetting } from '../i18n';

export type Settings = {
  apiUrl: string;
  token: string;
  /** ISO code, or 'auto': the one that goes with the language (see `currencyOf`). */
  currency: string;
  language: LanguageSetting;
};

export const CURRENCIES = ['EUR', 'CHF', 'USD', 'GBP', 'CAD'];

/**
 * Development on a phone: the API runs on the machine serving the bundle, so its address is the dev server's host
 * (Expo Go knows it), port 8000. `localhost` would be the phone itself.
 */
function devApiUrl(): string {
  const host = Constants.expoConfig?.hostUri?.split(':')[0];
  return __DEV__ && Platform.OS !== 'web' && host ? `http://${host}:8000` : 'http://localhost:8000';
}

const DEFAULTS: Settings = {
  apiUrl: process.env.EXPO_PUBLIC_API_URL ?? devApiUrl(),
  token: process.env.EXPO_PUBLIC_APP_TOKEN ?? '',
  currency: 'auto',
  language: 'auto',
};
const KEY = 'avers.settings';

/**
 * Web build: the access code can come with the link (https://…/#code=…), so nothing has to be typed. The fragment is
 * left in place on purpose: "Add to Home Screen" bookmarks the current URL, and the installed app has its own storage.
 */
function linkCode(): string | null {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return null;
  return new URLSearchParams(window.location.hash.slice(1)).get('code');
}

/**
 * Development builds only: settings passed in the app link (exp://…/--/?api=…&lang=fr), so e2e flows configure the
 * app without going through the settings screen. Never in production: a link could otherwise send the access code to
 * another server.
 */
function linkSettings(url: string | null): Partial<Settings> | null {
  if (!__DEV__ || !url) return null;
  const { api, lang } = Linking.parse(url).queryParams ?? {};
  const patch: Partial<Settings> = {};
  if (typeof api === 'string') patch.apiUrl = api;
  if (lang === 'fr' || lang === 'en' || lang === 'auto') patch.language = lang;
  return Object.keys(patch).length ? patch : null;
}

const Ctx = createContext<{ settings: Settings; save: (s: Partial<Settings>) => void }>({
  settings: DEFAULTS,
  save: () => {},
});

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState(DEFAULTS);
  const [loaded, setLoaded] = useState(false);
  const url = Linking.useLinkingURL();

  useEffect(() => {
    AsyncStorage.getItem(KEY)
      .then((raw) => {
        const stored = raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS;
        const code = linkCode();
        setSettings(code ? { ...stored, token: code } : stored);
        if (code) AsyncStorage.setItem(KEY, JSON.stringify({ ...stored, token: code })).catch(() => {});
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  const save = (patch: Partial<Settings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      AsyncStorage.setItem(KEY, JSON.stringify(next)).catch(() => {});
      return next;
    });
  };

  useEffect(() => {
    const patch = loaded ? linkSettings(url) : null;
    if (patch) save(patch);
  }, [url, loaded]);

  // Render nothing until stored settings (server, access code) are known: no request may leave without them.
  if (!loaded) return null;
  return <Ctx.Provider value={{ settings, save }}>{children}</Ctx.Provider>;
}

export const useSettings = () => useContext(Ctx);
