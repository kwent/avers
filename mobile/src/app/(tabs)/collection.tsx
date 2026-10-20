import { router, useFocusEffect } from 'expo-router';
import { ReactNode, useCallback, useMemo, useState } from 'react';
import { FlatList, RefreshControl, ScrollView, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Band, Button, Chip, CoinWell, cn, Notice, Row, Section, SwitchRow, T } from '../../components/ui';
import { currencyOf, errorText, useI18n } from '../../i18n';
import type { Messages } from '../../i18n/fr';
import { CollectionResponse, getCollection, Item, photoUrl } from '../../lib/api';
import { gradeLabel, metalName, money, range } from '../../lib/format';
import { useSettings } from '../../lib/settings';
import { colors, metals } from '../../theme';

type Sort = 'value' | 'year' | 'name' | 'recent';
const SORTS: Sort[] = ['value', 'year', 'name', 'recent'];
// prices hidden: no sorting by value either (the order alone would tell the dearest coins)
const BLIND_SORTS: Sort[] = ['recent', 'year', 'name'];
/** Direction a sort starts in: most valuable, oldest, A to Z, newest. */
const DESC_FIRST: Record<Sort, boolean> = { value: true, year: false, name: false, recent: true };
const GRADES = ['B', 'TB', 'TTB', 'SUP', 'SPL', 'FDC', 'unknown'];
const THUMB = 72;

const metalOf = (i: Item) => i.metal ?? 'unknown';
const gradeOf = (i: Item) => i.grade ?? 'unknown';
/** Lower case without accents, so "eu" finds "Écu" and "fr" finds "FR". */
const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

/** What one coin row is worth: its value, or its metal when it has no price (as the totals count it). */
const worth = (i: Item): [number, number] =>
  i.value_low != null
    ? [i.value_low * i.quantity, (i.value_high ?? i.value_low) * i.quantity]
    : [(i.melt?.value ?? 0) * i.quantity, (i.melt?.value ?? 0) * i.quantity];

/** Values present in the collection, in a fixed order, with how many coins each has. */
function facets(items: Item[], key: (i: Item) => string, order: string[]) {
  const counts = new Map<string, number>();
  for (const i of items) counts.set(key(i), (counts.get(key(i)) ?? 0) + i.quantity);
  const rank = (k: string) => (order.includes(k) ? order.indexOf(k) : order.length);
  return [...counts].sort(([a], [b]) => rank(a) - rank(b)).map(([k, count]) => ({ key: k, count }));
}

function haystack(i: Item, m: Messages) {
  return fold(
    [i.title, i.denomination, i.country_iso, i.year, i.notes, i.metal && metalName(i.metal, m), i.grade]
      .filter((x) => x != null && x !== '')
      .join(' '),
  );
}

export default function CollectionScreen() {
  const { settings, save } = useSettings();
  const hide = settings.hidePrices;
  const { m, locale } = useI18n();
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<CollectionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sort, setSort] = useState<Sort>('value');
  const [desc, setDesc] = useState(DESC_FIRST.value);
  const [query, setQuery] = useState('');
  const [metal, setMetal] = useState<string | null>(null);
  const [grade, setGrade] = useState<string | null>(null);

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

  const all = useMemo(() => data?.items ?? [], [data]);
  const metalFacets = useMemo(() => facets(all, metalOf, Object.keys(m.metals)), [all, m]);
  const gradeFacets = useMemo(() => facets(all, gradeOf, GRADES), [all]);

  const shownSort: Sort = hide && sort === 'value' ? 'recent' : sort;
  const shownDesc = hide && sort === 'value' ? DESC_FIRST.recent : desc;

  const items = useMemo(() => {
    const words = fold(query).split(/\s+/).filter(Boolean);
    const list = all.filter(
      (i) =>
        (metal == null || metalOf(i) === metal) &&
        (grade == null || gradeOf(i) === grade) &&
        (words.length === 0 || words.every((w) => haystack(i, m).includes(w))),
    );
    const mid = (i: Item) => (worth(i)[0] + worth(i)[1]) / 2;
    const compare: Record<Sort, (a: Item, b: Item) => number> = {
      value: (a, b) => mid(a) - mid(b),
      // coins without a year go last either way
      year: (a, b) => (a.year ?? (desc ? -Infinity : Infinity)) - (b.year ?? (desc ? -Infinity : Infinity)),
      name: (a, b) => a.title.localeCompare(b.title, locale, { sensitivity: 'base' }),
      recent: (a, b) => a.created_at.localeCompare(b.created_at) || a.id - b.id,
    };
    return list.sort((a, b) => (shownDesc ? -1 : 1) * compare[shownSort](a, b));
  }, [all, query, metal, grade, shownSort, shownDesc, locale, m]);

  const chooseSort = (key: Sort) => {
    if (key === shownSort) setDesc(!shownDesc);
    else {
      setSort(key);
      setDesc(DESC_FIRST[key]);
    }
  };

  const filtering = query.trim() !== '' || metal != null || grade != null;
  const clear = () => {
    setQuery('');
    setMetal(null);
    setGrade(null);
  };
  const shownCount = items.reduce((n, i) => n + i.quantity, 0);
  const shownWorth = items.reduce(([lo, hi], i) => [lo + worth(i)[0], hi + worth(i)[1]], [0, 0]);

  const cur = data?.currency ?? currencyOf(settings);
  const empty = data?.totals.count === 0;
  const last = items.length - 1;

  return (
    <FlatList
      contentContainerClassName="pb-8"
      data={items}
      keyExtractor={(i) => String(i.id)}
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="on-drag"
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={colors.gold} />}
      ListHeaderComponent={
        <View>
          <Band className="gap-1" style={{ paddingTop: insets.top + 24 }}>
            <T variant="heading" tone="ink" accessibilityRole="header">
              {empty || hide ? m.tabs.collection : m.collection.total}
            </T>
            {data && !empty && hide && <T variant="title">{m.collection.count(data.totals.count)}</T>}
            {data && !empty && !hide && (
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
              <Section>
                <SwitchRow
                  testID="collection-hide-prices"
                  label={m.settings.hidePrices}
                  value={hide}
                  onChange={(hidePrices) => save({ hidePrices })}
                />
              </Section>
            )}
            {data && !empty && !hide && (
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
            {all.length > 1 && (
              <View className="gap-3">
                <TextInput
                  testID="collection-search"
                  className="min-h-[56px] rounded-sm bg-surface px-4 font-regular text-body text-cream"
                  placeholder={m.collection.search}
                  placeholderTextColor={colors['cream-soft']}
                  accessibilityLabel={m.collection.search}
                  value={query}
                  onChangeText={setQuery}
                  autoCorrect={false}
                  clearButtonMode="while-editing"
                  returnKeyType="search"
                />
                <ChipRow label={m.collection.sortBy}>
                  {(hide ? BLIND_SORTS : SORTS).map((key) => (
                    <Chip
                      key={key}
                      testID={`sort-${key}`}
                      label={
                        key === shownSort
                          ? `${m.collection.sort[key]}, ${shownDesc ? m.collection.descending : m.collection.ascending}`
                          : m.collection.sort[key]
                      }
                      selected={key === shownSort}
                      icon={key === shownSort ? (shownDesc ? 'arrow-down' : 'arrow-up') : undefined}
                      onPress={() => chooseSort(key)}
                    />
                  ))}
                </ChipRow>
                {metalFacets.length > 1 && (
                  <ChipRow label={m.collection.filterMetal}>
                    <Chip label={m.collection.all} selected={metal == null} onPress={() => setMetal(null)} />
                    {metalFacets.map((f) => (
                      <Chip
                        key={f.key}
                        testID={`metal-${f.key}`}
                        label={metalName(f.key, m)}
                        swatch={metals[f.key]}
                        count={f.count}
                        selected={metal === f.key}
                        onPress={() => setMetal(metal === f.key ? null : f.key)}
                      />
                    ))}
                  </ChipRow>
                )}
                {gradeFacets.length > 1 && (
                  <ChipRow label={m.collection.filterGrade}>
                    <Chip label={m.collection.all} selected={grade == null} onPress={() => setGrade(null)} />
                    {gradeFacets.map((f) => (
                      <Chip
                        key={f.key}
                        testID={`grade-${f.key}`}
                        label={f.key === 'unknown' ? gradeLabel(f.key, m) : f.key}
                        count={f.count}
                        selected={grade === f.key}
                        onPress={() => setGrade(grade === f.key ? null : f.key)}
                      />
                    ))}
                  </ChipRow>
                )}
                {filtering && (
                  <View className="flex-row flex-wrap items-center justify-between gap-2">
                    <View className="shrink" accessibilityLiveRegion="polite">
                      <T variant="bodyStrong">{m.collection.shown(shownCount, data?.totals.count ?? 0)}</T>
                      {items.length > 0 && !hide && (
                        <T variant="small" tone="gold">
                          {range(shownWorth[0], shownWorth[1], cur, locale)}
                        </T>
                      )}
                    </View>
                    <Button variant="quiet" icon="close-circle" title={m.collection.clearFilters} onPress={clear} />
                  </View>
                )}
              </View>
            )}
          </View>
        </View>
      }
      ListEmptyComponent={
        data && !empty ? (
          <View className="items-center gap-2 p-gutter pt-6">
            <T variant="heading" className="text-center">
              {m.collection.noMatch}
            </T>
          </View>
        ) : data ? (
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
                {!hide && (
                  <T variant="bodyStrong" tone="gold">
                    {item.value_low != null
                      ? range(item.value_low, item.value_high, cur, locale)
                      : item.melt
                        ? m.collection.atLeast(money(item.melt.value, cur, locale))
                        : m.estimate.unknownPrice}
                  </T>
                )}
              </View>
            }
          />
        </View>
      )}
    />
  );
}

/** A labelled row of chips that scrolls sideways, edge to edge. */
function ChipRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <View className="gap-1.5">
      <T variant="small" tone="soft">
        {label}
      </T>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        className="-mx-gutter"
        contentContainerClassName="gap-2 px-gutter"
        accessibilityLabel={label}
      >
        {children}
      </ScrollView>
    </View>
  );
}
