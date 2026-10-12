import { getLocales } from 'expo-localization';
import { createContext, ReactNode, useContext, useMemo } from 'react';
import { CURRENCIES, Settings, useSettings } from '../lib/settings';
import en from './en';
import fr, { Messages } from './fr';

// To add a language: create <code>.ts typed as Messages, then register it here.
export const LANGUAGES = {
  fr: { name: 'Français', messages: fr },
  en: { name: 'English', messages: en },
} as const;

export type Language = keyof typeof LANGUAGES;
export type LanguageSetting = Language | 'auto';
export const FALLBACK_LANGUAGE: Language = 'en';

const isLanguage = (code: string | null | undefined): code is Language => !!code && code in LANGUAGES;

/** First device language Avers supports, else English. */
export function detectLanguage(): Language {
  for (const locale of getLocales()) {
    if (isLanguage(locale.languageCode)) return locale.languageCode;
  }
  return FALLBACK_LANGUAGE;
}

/** BCP 47 tag for Intl formatting: keep the device region when it speaks the chosen language. */
function formattingLocale(language: Language): string {
  const device = getLocales().find((l) => l.languageCode === language);
  return device?.languageTag ?? language;
}

/**
 * Currency that goes with a language: the device's own when it speaks that language (fr-CH: CHF, en-GB: GBP), else
 * the usual one (English: USD, French: EUR). Only a default: a currency picked in Settings wins.
 */
export function suggestedCurrency(language: Language): string {
  const device = getLocales().find((l) => l.languageCode === language)?.currencyCode;
  if (device && CURRENCIES.includes(device)) return device;
  return language === 'en' ? 'USD' : 'EUR';
}

export const resolveLanguage = (s: Settings): Language => (s.language === 'auto' ? detectLanguage() : s.language);

/** The currency prices are shown in. */
export const currencyOf = (s: Settings): string =>
  s.currency === 'auto' ? suggestedCurrency(resolveLanguage(s)) : s.currency;

type I18n = { m: Messages; language: Language; locale: string };

const Ctx = createContext<I18n>({ m: fr, language: 'fr', locale: 'fr-FR' });

export function I18nProvider({ children }: { children: ReactNode }) {
  const { settings } = useSettings();
  const value = useMemo(() => {
    const language = resolveLanguage(settings);
    return { m: LANGUAGES[language].messages, language, locale: formattingLocale(language) };
  }, [settings.language]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useI18n = () => useContext(Ctx);

/** User-facing text for any error thrown by the API client. */
export function errorText(e: unknown, m: Messages): string {
  if (e && typeof e === 'object' && 'kind' in e) {
    const err = e as { kind: string; status: number; message: string };
    if (err.kind === 'unreachable') return m.errors.unreachable;
    if (err.status === 401) return m.errors.badCode;
    if (err.status === 429) return m.errors.dailyLimit;
    if (err.status === 502) return m.errors.vision;
    return err.message || m.errors.http(err.status);
  }
  return e instanceof Error ? e.message : String(e);
}
