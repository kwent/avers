import Ionicons from '@expo/vector-icons/Ionicons';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from 'expo-haptics';
import { createContext, ReactNode, useCallback, useContext, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useI18n } from '../i18n';
import { colors, font } from '../lib/theme';

type CopyCtx = { copied: string | null; copy: (key: string, text: string) => void };

const Ctx = createContext<CopyCtx>({ copied: null, copy: () => {} });

/** Shares "which field was just copied" so only that field shows the ✓. */
export function CopyProvider({ children }: { children: ReactNode }) {
  const [copied, setCopied] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const copy = useCallback((key: string, text: string) => {
    Clipboard.setStringAsync(text).catch(() => {});
    Haptics.selectionAsync().catch(() => {});
    setCopied(key);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(null), 3000);
  }, []);
  return <Ctx.Provider value={{ copied, copy }}>{children}</Ctx.Provider>;
}

export const useCopy = () => useContext(Ctx);

/** Copy icon that turns into a ✓ once its text is on the clipboard. */
export function CopyButton({ id, text, label, light }: { id: string; text: string; label: string; light?: boolean }) {
  const { m } = useI18n();
  const { copied, copy } = useCopy();
  const done = copied === id;
  return (
    <Pressable
      testID={`copy-${id}`}
      accessibilityRole="button"
      accessibilityLabel={`${m.common.copy} : ${label}`}
      accessibilityHint={done ? m.common.copied : undefined}
      onPress={() => copy(id, text)}
      hitSlop={8}
      style={styles.button}
    >
      <Ionicons
        name={done ? 'checkmark-circle' : 'copy-outline'}
        size={24}
        color={done ? colors.success : light ? colors.brassDark : colors.muted}
      />
    </Pressable>
  );
}

/** Label/value row whose value can be copied with one tap. */
export function CopyRow({ id, label, value }: { id: string; label: string; value: string | number }) {
  const text = String(value);
  const { copy } = useCopy();
  return (
    <Pressable style={styles.row} onPress={() => copy(id, text)} accessibilityRole="button">
      <Text style={styles.label}>{label}</Text>
      <View style={styles.valueWrap}>
        <Text style={styles.value} selectable>
          {text}
        </Text>
        <CopyButton id={id} text={text} label={label} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, minHeight: 48 },
  label: { fontSize: font.body, color: colors.muted },
  valueWrap: { flexDirection: 'row', alignItems: 'center', flexShrink: 1 },
  value: { fontSize: font.body, color: colors.text, fontWeight: '600', flexShrink: 1, textAlign: 'right' },
});
