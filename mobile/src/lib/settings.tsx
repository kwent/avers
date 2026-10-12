import AsyncStorage from '@react-native-async-storage/async-storage';
import { getLocales } from 'expo-localization';
import { createContext, ReactNode, useContext, useEffect, useState } from 'react';
import { Platform } from 'react-native';
import type { LanguageSetting } from '../i18n';

export type Settings = {
  apiUrl: string;
  token: string;
  currency: string;
  language: LanguageSetting;
};

export const CURRENCIES = ['EUR', 'CHF', 'USD', 'GBP', 'CAD'];

/** Device currency when supported (e.g. CHF in Switzerland), else EUR. */
function detectCurrency(): string {
  const code = getLocales()[0]?.currencyCode;
  return code && CURRENCIES.includes(code) ? code : 'EUR';
}

const DEFAULTS: Settings = {
  apiUrl: process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000',
  token: process.env.EXPO_PUBLIC_APP_TOKEN ?? '',
  currency: detectCurrency(),
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

const Ctx = createContext<{ settings: Settings; save: (s: Partial<Settings>) => void }>({
  settings: DEFAULTS,
  save: () => {},
});

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState(DEFAULTS);
  const [loaded, setLoaded] = useState(false);

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
    const next = { ...settings, ...patch };
    setSettings(next);
    AsyncStorage.setItem(KEY, JSON.stringify(next)).catch(() => {});
  };

  // Render nothing until stored settings (server, access code) are known: no request may leave without them.
  if (!loaded) return null;
  return <Ctx.Provider value={{ settings, save }}>{children}</Ctx.Provider>;
}

export const useSettings = () => useContext(Ctx);
