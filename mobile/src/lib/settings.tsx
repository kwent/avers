import AsyncStorage from '@react-native-async-storage/async-storage';
import { getLocales } from 'expo-localization';
import { createContext, ReactNode, useContext, useEffect, useState } from 'react';
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

const Ctx = createContext<{ settings: Settings; save: (s: Partial<Settings>) => void }>({
  settings: DEFAULTS,
  save: () => {},
});

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState(DEFAULTS);

  useEffect(() => {
    AsyncStorage.getItem(KEY)
      .then((raw) => raw && setSettings({ ...DEFAULTS, ...JSON.parse(raw) }))
      .catch(() => {});
  }, []);

  const save = (patch: Partial<Settings>) => {
    const next = { ...settings, ...patch };
    setSettings(next);
    AsyncStorage.setItem(KEY, JSON.stringify(next)).catch(() => {});
  };

  return <Ctx.Provider value={{ settings, save }}>{children}</Ctx.Provider>;
}

export const useSettings = () => useContext(Ctx);
