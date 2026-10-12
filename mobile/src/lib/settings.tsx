import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, ReactNode, useContext, useEffect, useState } from 'react';

export type Settings = {
  apiUrl: string;
  token: string;
  currency: string;
};

export const CURRENCIES = ['EUR', 'CHF', 'USD', 'GBP', 'CAD'];

const DEFAULTS: Settings = {
  apiUrl: process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000',
  token: process.env.EXPO_PUBLIC_APP_TOKEN ?? '',
  currency: 'EUR',
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
