import { router, useFocusEffect } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { FlatList, RefreshControl, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Band, Button, CoinWell, cn, Notice, Row, Section, Segmented, T } from '../../components/ui';
import { currencyOf, errorText, useI18n } from '../../i18n';
import { CollectionResponse, getCollection, Item, photoUrl } from '../../lib/api';
import { gradeLabel, money, range } from '../../lib/format';
import { useSettings } from '../../lib/settings';
import { colors } from '../../theme';

type Sort = 'value' | 'year' | 'recent';
const SORTS: Sort[] = ['value', 'year', 'recent'];
const THUMB = 72;

export default function CollectionScreen() {
  const { settings } = useSettings();
  const { m, locale } = useI18n();
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<CollectionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sort, setSort] = useState<Sort>('value');

  const load = useCallback(() => {
    setLoading(true);
    getCollection(settings)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(errorText(e, m)))
      .finally(() => setLoading(false));
  }, [settings, m]);

  useFocusEffect(load);

  const items = useMemo(() => {
    const list = [...(data?.items ?? [])];
    const mid = (i: Item) =>
      i.value_low != null ? (i.value_low + (i.value_high ?? i.value_low)) / 2 : (i.melt?.value ?? 0);
    if (sort === 'value') list.sort((a, b) => mid(b) * b.quantity - mid(a) * a.quantity);
    if (sort === 'year') list.sort((a, b) => (a.year ?? 9999) - (b.year ?? 9999));
    return list;
  }, [data, sort]);

  const cur = data?.currency ?? currencyOf(settings);
  const empty = data?.totals.count === 0;
  const last = items.length - 1;

  return (
    <FlatList
      contentContainerClassName="pb-8"
      data={items}
      keyExtractor={(i) => String(i.id)}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={colors.gold} />}
      ListHeaderComponent={
        <View>
          <Band className="gap-1" style={{ paddingTop: insets.top + 24 }}>
            <T variant="heading" tone="ink" accessibilityRole="header">
              {empty ? m.tabs.collection : m.collection.total}
            </T>
            {data && !empty && (
              <>
                <T variant="display" tone="gold" testID="collection-total">
                  {range(data.totals.total_low, data.totals.total_high, cur, locale)}
                </T>
                <T tone="soft">{m.collection.count(data.totals.count)}</T>
              </>
            )}
          </Band>
          <View className="gap-4 p-gutter pb-4">
            {error && <Notice tone="danger">{error}</Notice>}
            {data && !empty && (
              <Section
                title={m.collection.breakdown}
                footer={data.totals.unpriced_count > 0 ? m.collection.unpricedNote : undefined}
              >
                {data.totals.priced_count > 0 && (
                  <Row
                    label={m.collection.priced(data.totals.priced_count)}
                    value={
                      <T variant="bodyStrong" tone="gold">
                        {range(data.totals.value_low, data.totals.value_high, cur, locale)}
                      </T>
                    }
                  />
                )}
                {data.totals.unpriced_count > 0 && (
                  <Row
                    label={m.collection.unpriced(data.totals.unpriced_count)}
                    value={
                      <T variant="bodyStrong" tone="gold">
                        {m.collection.atLeast(money(data.totals.unpriced_melt, cur, locale))}
                      </T>
                    }
                  />
                )}
                <Row
                  label={m.collection.metal}
                  value={<T variant="bodyStrong">{money(data.totals.melt, cur, locale)}</T>}
                />
              </Section>
            )}
            {items.length > 1 && (
              <Segmented
                label={m.collection.sortBy}
                options={SORTS.map((key) => ({ key, label: m.collection.sort[key] }))}
                value={sort}
                onChange={setSort}
              />
            )}
          </View>
        </View>
      }
      ListEmptyComponent={
        data ? (
          <View className="items-center gap-4 p-gutter pt-6">
            <CoinWell size={128} icon="albums-outline" />
            <T variant="heading" className="text-center">
              {m.collection.empty}
            </T>
            <T tone="soft" className="text-center">
              {m.collection.emptyHint}
            </T>
            <View className="self-stretch">
              <Button title={m.collection.scanFirst} icon="camera" onPress={() => router.push('/scan')} />
            </View>
          </View>
        ) : null
      }
      renderItem={({ item, index }) => (
        <View className={cn('mx-gutter bg-surface', index === 0 && 'rounded-t-md', index === last && 'rounded-b-md')}>
          {index > 0 && <View className="h-px bg-line" style={{ marginLeft: 16 + THUMB + 12 }} />}
          <Row
            onPress={() => router.push({ pathname: '/item/[id]', params: { id: String(item.id) } })}
            chevron
            stacked
            leading={<CoinWell size={THUMB} uri={photoUrl(settings, item.photo_front, true)} />}
            label={
              <T variant="bodyStrong" numberOfLines={2}>
                {item.quantity > 1 ? `${item.quantity} × ` : ''}
                {item.title}
              </T>
            }
            value={
              <View className="gap-0.5">
                {!!item.grade && item.grade !== 'unknown' && (
                  <T variant="small" tone="soft">
                    {gradeLabel(item.grade, m)}
                  </T>
                )}
                <T variant="bodyStrong" tone="gold">
                  {item.value_low != null
                    ? range(item.value_low, item.value_high, cur, locale)
                    : item.melt
                      ? m.collection.atLeast(money(item.melt.value, cur, locale))
                      : m.estimate.unknownPrice}
                </T>
              </View>
            }
          />
        </View>
      )}
    />
  );
}
