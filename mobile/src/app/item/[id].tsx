import Ionicons from '@expo/vector-icons/Ionicons';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, ScrollView, TextInput, View } from 'react-native';
import { EstimateView } from '../../components/EstimateView';
import { Button, Notice, Press, Row, Section, T } from '../../components/ui';
import { errorText, useI18n } from '../../i18n';
import { confirm } from '../../lib/platform/confirm';
import { deleteItem, getItem, Item, patchItem, photoUrl } from '../../lib/api';
import { range } from '../../lib/format';
import { useSettings } from '../../lib/settings';
import { colors } from '../../theme';

export default function ItemScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { settings } = useSettings();
  const { m, locale } = useI18n();
  const [item, setItem] = useState<Item | null>(null);
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getItem(settings, Number(id))
      .then((i) => {
        setItem(i);
        setNotes(i.notes ?? '');
      })
      .catch((e) => setError(errorText(e, m)));
  }, [id, settings]);

  const update = async (patch: Partial<Item>) => {
    try {
      setItem(await patchItem(settings, Number(id), patch));
    } catch (e) {
      Alert.alert(m.common.error, errorText(e, m));
    }
  };

  const doRemove = async () => {
    await deleteItem(settings, Number(id));
    router.back();
  };

  const remove = async () => {
    if (await confirm(m.item.removeTitle, m.item.removeBody, m.item.removeConfirm, m.common.cancel)) doRemove();
  };

  if (error) {
    return (
      <View className="p-gutter">
        <Notice tone="danger">{error}</Notice>
      </View>
    );
  }
  if (!item) return <ActivityIndicator className="mt-12" size="large" color={colors.gold} />;

  const stepper = (
    <View className="flex-row items-center gap-3">
      <Press
        accessibilityRole="button"
        accessibilityLabel={m.item.less}
        disabled={item.quantity <= 1}
        className={`h-[52px] w-[52px] items-center justify-center rounded-full border-2 border-gold ${item.quantity <= 1 ? 'opacity-40' : ''}`}
        onPress={() => update({ quantity: item.quantity - 1 })}
      >
        <Ionicons name="remove" size={28} color={colors.gold} />
      </Press>
      <T variant="title" className="min-w-[36px] text-center" accessibilityLiveRegion="polite">
        {item.quantity}
      </T>
      <Press
        accessibilityRole="button"
        accessibilityLabel={m.item.more}
        className="h-[52px] w-[52px] items-center justify-center rounded-full border-2 border-gold"
        onPress={() => update({ quantity: item.quantity + 1 })}
      >
        <Ionicons name="add" size={28} color={colors.gold} />
      </Press>
    </View>
  );

  const collectionSection = (
    <Section
      title={m.item.inCollection}
      footer={
        item.quantity > 1 && !settings.hidePrices
          ? m.item.total(
              range(
                (item.value_low ?? 0) * item.quantity,
                (item.value_high ?? 0) * item.quantity,
                item.value_currency,
                locale,
              ),
            )
          : undefined
      }
    >
      <Row label={m.item.quantity} value={stepper} />
      {/* notes may hold the purchase price ("prix d'achat"): hidden with the prices */}
      {!settings.hidePrices && (
        <View className="p-3">
          <TextInput
            className="min-h-[96px] rounded-sm bg-ground p-3 font-regular text-body text-cream"
            textAlignVertical="top"
            placeholder={m.item.notes}
            placeholderTextColor={colors['cream-soft']}
            accessibilityLabel={m.item.notes}
            multiline
            value={notes}
            onChangeText={setNotes}
            onBlur={() => notes !== (item.notes ?? '') && update({ notes })}
          />
        </View>
      )}
    </Section>
  );

  return (
    <ScrollView contentContainerClassName="pb-8" keyboardShouldPersistTaps="handled" automaticallyAdjustKeyboardInsets>
      {item.estimate ? (
        <EstimateView
          est={item.estimate}
          saved
          photos={[photoUrl(settings, item.photo_front), photoUrl(settings, item.photo_back)]}
        >
          {collectionSection}
        </EstimateView>
      ) : (
        <View className="gap-6 p-gutter">
          <T variant="title">{item.title}</T>
          {collectionSection}
        </View>
      )}
      <View className="px-gutter">
        <Button title={m.item.remove} variant="danger" icon="trash-outline" onPress={remove} />
      </View>
    </ScrollView>
  );
}
