import { useState } from 'react';
import { TextInput, View } from 'react-native';
import { useI18n } from '../i18n';
import { colors } from '../theme';
import { Button, Notice } from './ui';

/**
 * The year read has no catalog listing, or could not be read (read null): rather than guess, ask which year the
 * coin shows. Offers the catalogued years a worn date is usually mistaken for, the year as read, and any other year.
 */
export function YearCheck({
  read,
  suggestions,
  onYear,
}: {
  read: number | null;
  suggestions: number[];
  onYear: (year: number) => Promise<void>;
}) {
  const { m } = useI18n();
  const [busy, setBusy] = useState<number | null>(null);
  const [other, setOther] = useState('');
  const typed = /^\d{3,4}$/.test(other) ? Number(other) : null;

  const pick = async (year: number) => {
    setBusy(year);
    try {
      await onYear(year);
    } finally {
      setBusy(null);
    }
  };

  return (
    <View className="gap-3" testID="year-check">
      <Notice tone="warning" title={read ? m.estimate.yearTitle(read) : m.estimate.yearUnreadTitle}>
        {read ? m.estimate.yearBody(read) : m.estimate.yearUnreadBody}
      </Notice>
      {suggestions.map((y) => (
        <Button
          key={y}
          testID={`year-${y}`}
          title={m.estimate.yearIs(y)}
          loading={busy === y}
          disabled={busy != null}
          onPress={() => pick(y)}
        />
      ))}
      {read != null && (
        <Button
          testID="year-keep"
          variant="secondary"
          title={m.estimate.yearKeep(read)}
          loading={busy === read}
          disabled={busy != null}
          onPress={() => pick(read)}
        />
      )}
      <View className="flex-row items-center gap-3">
        <TextInput
          testID="year-other"
          className="min-h-touch flex-1 rounded-sm bg-surface px-4 font-regular text-body text-cream"
          placeholder={m.estimate.yearOther}
          placeholderTextColor={colors['cream-soft']}
          accessibilityLabel={m.estimate.yearOther}
          keyboardType="number-pad"
          maxLength={4}
          value={other}
          onChangeText={setOther}
          onSubmitEditing={() => typed && pick(typed)}
        />
        <Button
          variant="quiet"
          icon="checkmark"
          title="OK"
          disabled={!typed || busy != null}
          loading={typed != null && busy === typed && !suggestions.includes(typed) && typed !== read}
          onPress={() => typed && pick(typed)}
        />
      </View>
    </View>
  );
}
