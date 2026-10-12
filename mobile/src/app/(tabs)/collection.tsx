import Ionicons from '@expo/vector-icons/Ionicons';
import { Image } from 'expo-image';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { Button, Card, Label } from '../../components/ui';
import { errorText, useI18n } from '../../i18n';
import { CollectionResponse, getCollection, Item, photoUrl } from '../../lib/api';
import { gradeName, money, range } from '../../lib/format';
import { useSettings } from '../../lib/settings';
import { colors, font } from '../../lib/theme';

type Sort = 'value' | 'year' | 'recent';
const SORTS: Sort[] = ['value', 'year', 'recent'];

export default function CollectionScreen() {
  const { settings } = useSettings();
  const { m, locale } = useI18n();
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
    const mid = (i: Item) => ((i.value_low ?? 0) + (i.value_high ?? 0)) / 2;
    if (sort === 'value') list.sort((a, b) => mid(b) * b.quantity - mid(a) * a.quantity);
    if (sort === 'year') list.sort((a, b) => (a.year ?? 9999) - (b.year ?? 9999));
    return list;
  }, [data, sort]);

  const cur = data?.currency ?? settings.currency;

  return (
    <FlatList
      contentContainerStyle={styles.container}
      data={items}
      keyExtractor={(i) => String(i.id)}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
      ListHeaderComponent={
        <View style={{ gap: 16 }}>
          {error && (
            <Card style={{ borderColor: colors.danger }}>
              <Text style={styles.body}>{error}</Text>
            </Card>
          )}
          {data && (
            <Card style={{ backgroundColor: colors.brassLight, borderColor: colors.brass }}>
              <Label>{m.collection.total}</Label>
              <Text style={styles.hero}>{range(data.totals.value_low, data.totals.value_high, cur, locale)}</Text>
              <Text style={styles.body}>
                {m.collection.summary(data.totals.count, money(data.totals.melt, cur, locale))}
              </Text>
            </Card>
          )}
          {items.length > 1 && (
            <View style={styles.sorts}>
              <Text style={styles.sortLabel}>{m.collection.sortBy}</Text>
              {SORTS.map((key) => (
                <Pressable key={key} onPress={() => setSort(key)} style={[styles.sort, sort === key && styles.sortActive]}>
                  <Text style={[styles.sortText, sort === key && { color: '#fff' }]}>{m.collection.sort[key]}</Text>
                </Pressable>
              ))}
            </View>
          )}
        </View>
      }
      ListEmptyComponent={
        data ? (
          <View style={styles.empty}>
            <Ionicons name="albums-outline" size={72} color={colors.muted} />
            <Text style={styles.emptyText}>{m.collection.empty}</Text>
            <Button title={m.collection.scanFirst} onPress={() => router.push('/scan')} />
          </View>
        ) : null
      }
      renderItem={({ item }) => (
        <Pressable onPress={() => router.push({ pathname: '/item/[id]', params: { id: String(item.id) } })}>
          <Card style={styles.item}>
            <Image source={{ uri: photoUrl(settings, item.photo_front) }} style={styles.thumb} contentFit="cover" />
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={styles.itemTitle} numberOfLines={2}>
                {item.quantity > 1 ? `${item.quantity} × ` : ''}
                {item.title}
              </Text>
              <Text style={styles.itemMeta}>{item.grade ? gradeName(item.grade, m) : ''}</Text>
              <Text style={styles.itemValue}>{range(item.value_low, item.value_high, cur, locale)}</Text>
            </View>
            <Ionicons name="chevron-forward" size={28} color={colors.muted} />
          </Card>
        </Pressable>
      )}
    />
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, gap: 12, paddingBottom: 48 },
  hero: { fontSize: font.title + 2, fontWeight: '800', color: colors.brassDark },
  body: { fontSize: font.body, color: colors.text },
  sorts: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  sortLabel: { fontSize: font.body, color: colors.muted },
  sort: { borderWidth: 2, borderColor: colors.brass, borderRadius: 999, paddingHorizontal: 16, paddingVertical: 8 },
  sortActive: { backgroundColor: colors.brass },
  sortText: { fontSize: font.small, fontWeight: '700', color: colors.brassDark },
  item: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 12 },
  thumb: { width: 80, height: 80, borderRadius: 40, backgroundColor: colors.border },
  itemTitle: { fontSize: font.body, fontWeight: '700', color: colors.text },
  itemMeta: { fontSize: font.small, color: colors.muted },
  itemValue: { fontSize: font.large, fontWeight: '800', color: colors.brassDark },
  empty: { alignItems: 'center', gap: 16, paddingTop: 40 },
  emptyText: { fontSize: font.large, color: colors.muted },
});
