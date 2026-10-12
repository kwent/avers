import Ionicons from '@expo/vector-icons/Ionicons';
import { Image } from 'expo-image';
import * as Linking from 'expo-linking';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useI18n } from '../i18n';
import type { Messages } from '../i18n/fr';
import { Comparable, Estimate } from '../lib/api';
import { confidence, gradeName, metalName, money, number, range, sourceLabel } from '../lib/format';
import { colors, font } from '../lib/theme';
import { CopyButton, CopyProvider, CopyRow, useCopy } from './Copy';
import { MatchCard, PriceTable } from './Market';
import { Card, Label, Pill } from './ui';

type Field = { id: string; label: string; value: string };

/** Detail fields shown (and copied) for an estimate, in display order; empty values are skipped. */
function detailFields(est: Estimate, m: Messages, locale: string): Field[] {
  const coin = est.identification;
  const fields: (Field | false)[] = [
    { id: 'country', label: m.estimate.country, value: coin.country_name ?? '' },
    { id: 'year', label: m.estimate.year, value: coin.year != null ? String(coin.year) : '' },
    { id: 'mint', label: m.estimate.mint, value: coin.mint_mark ?? '' },
    { id: 'face', label: m.estimate.faceValue, value: coin.denomination ?? '' },
    { id: 'metal', label: m.estimate.metal, value: metalName(coin.metal, m) },
    coin.fineness != null && {
      id: 'fineness',
      label: m.estimate.fineness,
      value: `${Math.round(coin.fineness * 1000)} ‰`,
    },
    coin.weight_g != null && { id: 'weight', label: m.estimate.weight, value: `${number(coin.weight_g, locale)} g` },
    { id: 'refs', label: m.estimate.refs, value: coin.catalog_refs.join(', ') },
    { id: 'grade', label: m.estimate.grade, value: gradeName(coin.grade, m) },
  ];
  return fields.filter((f): f is Field => !!f && !!f.value);
}

/** Plain-text summary of the whole estimate, for "Copy all". */
function summary(est: Estimate, m: Messages, locale: string): string {
  const coin = est.identification;
  const cur = est.currency;
  const v = est.valuation;
  const lines = [coin.title, coin.type_name, ''];
  if (v) {
    lines.push(`${m.estimate.value} : ${range(v.value_low, v.value_high, cur, locale)}`);
    if (v.retail_low != null) lines.push(m.estimate.shopPrice(range(v.retail_low, v.retail_high, cur, locale)));
  }
  if (est.melt) lines.push(`${m.estimate.meltShort} : ${money(est.melt.value, cur, locale, 2)}`);
  lines.push('', ...detailFields(est, m, locale).map((f) => `${f.label} : ${f.value}`));
  for (const text of [coin.grade_notes, coin.notes, v && explanation(est, m, locale)]) if (text) lines.push('', text);
  return lines
    .filter((l) => l != null)
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/** Plain-language basis of the price, written from the numbers (no generated text). */
function explanation(est: Estimate, m: Messages, locale: string): string {
  const v = est.valuation;
  if (!v) return '';
  if (!v.basis) return v.explanation ?? '';
  const { listings, first_year, last_year, metal_share } = v.basis;
  const years = first_year && last_year ? (first_year === last_year ? `${first_year}` : `${first_year}–${last_year}`) : null;
  const parts = [m.estimate.basisListings(listings, years)];
  if (est.melt && metal_share != null) parts.push(m.estimate.basisMetal(money(est.melt.value, est.currency, locale), Math.round(metal_share * 100)));
  parts.push(m.estimate.basisResale);
  return parts.join(' ');
}

export function EstimateView(props: { est: Estimate; photos: (string | undefined)[] }) {
  return (
    <CopyProvider>
      <EstimateContent {...props} />
    </CopyProvider>
  );
}

function EstimateContent({ est, photos }: { est: Estimate; photos: (string | undefined)[] }) {
  const { m, locale } = useI18n();
  const { copied, copy } = useCopy();
  const coin = est.identification;
  const cur = est.currency;
  const conf = confidence(coin.confidence, m);
  const best = new Set(est.valuation?.best_match_ids ?? []);
  const comparables = [...est.comparables].sort((a, b) => Number(best.has(b.id)) - Number(best.has(a.id)));
  const valueText = est.valuation ? range(est.valuation.value_low, est.valuation.value_high, cur, locale) : '';
  const meltText = est.melt ? money(est.melt.value, cur, locale, 2) : '';

  return (
    <View style={{ gap: 16 }}>
      <View style={styles.photos}>
        {photos.filter(Boolean).map((uri) => (
          <Image key={uri} source={{ uri }} style={styles.photo} contentFit="cover" />
        ))}
      </View>

      <View style={{ gap: 8 }}>
        <View style={styles.titleRow}>
          <Text style={styles.title} selectable>
            {coin.title}
          </Text>
          <CopyButton id="title" text={coin.title} label={coin.title} />
        </View>
        {!!coin.type_name && (
          <Text style={styles.subtitle} selectable>
            {coin.type_name}
          </Text>
        )}
        <View style={styles.titleRow}>
          <Pill text={conf.text} tone={conf.tone} />
          <Pressable
            testID="copy-all"
            accessibilityRole="button"
            accessibilityLabel={copied === 'all' ? m.common.copied : m.estimate.copyAll}
            onPress={() => copy('all', summary(est, m, locale))}
            style={styles.copyAll}
          >
            <Ionicons
              name={copied === 'all' ? 'checkmark-circle' : 'copy-outline'}
              size={22}
              color={copied === 'all' ? colors.success : colors.brassDark}
            />
            <Text style={styles.copyAllText}>{copied === 'all' ? m.common.copied : m.estimate.copyAll}</Text>
          </Pressable>
        </View>
      </View>

      {!!coin.authenticity_notes && (
        <Card style={{ borderColor: colors.danger, borderWidth: 2 }}>
          <Text style={[styles.body, { color: colors.danger, fontWeight: '700' }]}>{m.estimate.attention}</Text>
          <Text style={styles.body} selectable>
            {coin.authenticity_notes}
          </Text>
        </Card>
      )}

      {est.photo_warning === 'same_side' && (
        <Card style={{ borderColor: colors.warning, borderWidth: 2 }}>
          <Text style={styles.body}>{m.estimate.sameSide}</Text>
        </Card>
      )}

      {!!est.already_owned && (
        <Card style={{ borderColor: colors.warning, borderWidth: 2 }}>
          <Text style={styles.body}>{m.estimate.alreadyOwned(est.already_owned)}</Text>
        </Card>
      )}

      <Card style={{ backgroundColor: colors.brassLight, borderColor: colors.brass }}>
        <Label>{m.estimate.value}</Label>
        {est.valuation ? (
          <>
            <View style={styles.titleRow}>
              <Text style={styles.hero} selectable>
                {valueText}
              </Text>
              <CopyButton id="value" text={valueText} label={m.estimate.value} light />
            </View>
            {est.valuation.retail_low != null && (
              <Text style={styles.body} selectable>
                {m.estimate.shopPrice(range(est.valuation.retail_low, est.valuation.retail_high, cur, locale))}
              </Text>
            )}
            <Text style={styles.explain} selectable>
              {explanation(est, m, locale)}
            </Text>
          </>
        ) : (
          <Text style={styles.body}>{m.estimate.noPrice}</Text>
        )}
      </Card>

      {est.match ? (
        <MatchCard match={est.match} />
      ) : (
        <Text style={styles.explain}>{m.estimate.noMatch}</Text>
      )}

      {est.melt && (
        <Card>
          <Label>{m.estimate.melt}</Label>
          <View style={styles.titleRow}>
            <Text style={styles.big} selectable>
              {meltText}
            </Text>
            <CopyButton id="melt" text={meltText} label={m.estimate.meltShort} />
          </View>
          <Text style={styles.explain} selectable>
            {m.estimate.meltExplain(
              number(est.melt.pure_metal_g, locale),
              metalName(est.melt.metal, m),
              money(est.melt.spot_per_gram, cur, locale, 2),
            )}
          </Text>
        </Card>
      )}

      <PriceTable rows={est.price_table ?? []} grade={coin.grade} currency={cur} />

      <Card>
        <Label>{m.estimate.details}</Label>
        {detailFields(est, m, locale).map((f) => (
          <CopyRow key={f.id} id={f.id} label={f.label} value={f.value} />
        ))}
        {!!coin.grade_notes && (
          <Text style={styles.explain} selectable>
            {coin.grade_notes}
          </Text>
        )}
        {!!coin.notes && (
          <Text style={styles.explain} selectable>
            {coin.notes}
          </Text>
        )}
      </Card>

      {comparables.length > 0 && (
        <View style={{ gap: 10 }}>
          <Label>{m.estimate.comparables}</Label>
          {comparables.slice(0, 8).map((c) => (
            <ComparableRow key={c.id} c={c} highlighted={best.has(c.id)} />
          ))}
        </View>
      )}
    </View>
  );
}

function ComparableRow({ c, highlighted }: { c: Comparable; highlighted: boolean }) {
  const { m, locale } = useI18n();
  const price = money(c.price, c.currency, locale);
  return (
    <Pressable onPress={() => Linking.openURL(c.url)} accessibilityRole="link">
      <Card style={[styles.comp, highlighted && { borderColor: colors.brass, borderWidth: 2 }]}>
        {c.images[0] ? (
          <Image source={{ uri: c.images[0] }} style={styles.compImg} contentFit="cover" />
        ) : (
          <View style={styles.compImg} />
        )}
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={styles.compName} numberOfLines={2}>
            {c.name}
          </Text>
          <Text style={styles.compMeta}>
            {c.grade ?? '—'} · {c.in_stock ? m.estimate.inStock : m.estimate.sold(c.listed.slice(0, 4))} ·{' '}
            {sourceLabel(c.source)}
          </Text>
          <Text style={styles.compPrice}>{price}</Text>
        </View>
        <CopyButton id={`comp-${c.id}`} text={`${c.name} — ${price}\n${c.url}`} label={c.name} />
      </Card>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  photos: { flexDirection: 'row', gap: 12, justifyContent: 'center' },
  photo: { width: 150, height: 150, borderRadius: 75, borderWidth: 3, borderColor: colors.brass, backgroundColor: '#000' },
  titleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  title: { fontSize: font.title, fontWeight: '800', color: colors.text, flexShrink: 1 },
  subtitle: { fontSize: font.body, color: colors.muted },
  copyAll: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    minHeight: 44,
    paddingHorizontal: 12,
    borderRadius: 999,
    borderWidth: 2,
    borderColor: colors.brass,
  },
  copyAllText: { fontSize: font.small, fontWeight: '700', color: colors.brassDark },
  hero: { fontSize: font.hero, fontWeight: '800', color: colors.brassDark, flexShrink: 1 },
  big: { fontSize: font.title, fontWeight: '800', color: colors.text },
  body: { fontSize: font.body, color: colors.text, lineHeight: 26 },
  explain: { fontSize: font.small, color: colors.muted, lineHeight: 22 },
  comp: { flexDirection: 'row', gap: 12, alignItems: 'center', padding: 12 },
  compImg: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.border },
  compName: { fontSize: font.small, fontWeight: '700', color: colors.text },
  compMeta: { fontSize: 15, color: colors.muted },
  compPrice: { fontSize: font.large, fontWeight: '800', color: colors.text },
});
