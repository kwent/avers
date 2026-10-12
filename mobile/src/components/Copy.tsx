import Ionicons from '@expo/vector-icons/Ionicons';
import * as Clipboard from 'expo-clipboard';
import { createContext, ReactNode, useCallback, useContext, useRef, useState } from 'react';
import { Pressable, View } from 'react-native';
import { useI18n } from '../i18n';
import { colors } from '../theme';
import { Row, T, tick } from './ui';

type CopyCtx = { copied: string | null; copy: (key: string, text: string) => void };

const Ctx = createContext<CopyCtx>({ copied: null, copy: () => {} });

/** Shares "which field was just copied" so only that field shows the confirmation. */
export function CopyProvider({ children }: { children: ReactNode }) {
  const [copied, setCopied] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const copy = useCallback((key: string, text: string) => {
    Clipboard.setStringAsync(text).catch(() => {});
    tick();
    setCopied(key);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(null), 2500);
  }, []);
  return <Ctx.Provider value={{ copied, copy }}>{children}</Ctx.Provider>;
}

export const useCopy = () => useContext(Ctx);

/** A record line: tapping it copies the value, which briefly reads "Copié". */
export function CopyRow({ id, label, value }: { id: string; label: string; value: string }) {
  const { m } = useI18n();
  const { copied, copy } = useCopy();
  const done = copied === id;
  return (
    <Row
      testID={`copy-${id}`}
      label={label}
      accessibilityLabel={`${label} : ${value}. ${m.common.copy}`}
      onPress={() => copy(id, value)}
      value={
        done ? (
          <View className="flex-row items-center gap-1">
            <Ionicons name="checkmark-circle" size={22} color={colors.success} />
            <T variant="bodyStrong" tone="success">
              {m.common.copied}
            </T>
          </View>
        ) : (
          <T variant="bodyStrong" className="shrink text-right">
            {value}
          </T>
        )
      }
    />
  );
}

/** "Copy the record" link for a section header. */
export function CopyAllButton({ text }: { text: string }) {
  const { m } = useI18n();
  const { copied, copy } = useCopy();
  const done = copied === 'all';
  return (
    <Pressable
      testID="copy-all"
      accessibilityRole="button"
      accessibilityLabel={done ? m.common.copied : m.estimate.copyAll}
      onPress={() => copy('all', text)}
      hitSlop={8}
      className="min-h-[44px] flex-row items-center gap-1 active:opacity-60"
    >
      <Ionicons
        name={done ? 'checkmark-circle' : 'copy-outline'}
        size={22}
        color={done ? colors.success : colors.gold}
      />
      <T variant="smallStrong" tone={done ? 'success' : 'accent'}>
        {done ? m.common.copied : m.estimate.copyAll}
      </T>
    </Pressable>
  );
}
