import * as Linking from 'expo-linking';
import { ReactNode } from 'react';
import { View } from 'react-native';
import { useI18n } from '../i18n';
import type { Messages } from '../i18n/fr';
import { Comparable, Estimate, GradePrice } from '../lib/api';
import { gradeName, money, sourceLabel } from '../lib/format';
import { CoinWell, cn, Row, Section, T } from './ui';

/** Shop and resale price for each grade the catalog has, the coin's own grade highlighted. */
export function PriceTable({
  rows,
  grade,
  upper,
  currency,
  explanation,
  sources = [],
}: {
  rows: GradePrice[];
  grade: string;
  /** the next grade up when the coin sits between two: both rows are the coin's */
  upper?: string | null;
  currency: string;
  explanation: string;
  /** the prices the table rests on (PriceSources), listed under it */
  sources?: ReactNode[];
}) {
  const { m, locale } = useI18n();
  const known = rows.filter((r) => r.retail != null);
  if (!known.length) {
    return explanation ? (
      <Section title={m.estimate.whyTitle}>
        <Row label={explanation} />
      </Section>
    ) : null;
  }
  const tr = 'flex-row items-center gap-2 px-4';
  return (
    <Section
      title={m.estimate.whyTitle}
      footer={`${explanation} ${m.estimate.priceNote}${sources.length ? ` ${m.estimate.pricesUsedNote}` : ''}`}
    >
      <View
        className={cn(tr, 'min-h-[40px]')}
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
      >
        <T variant="small" tone="soft" className="flex-[1.1]">
          {m.estimate.colGrade}
        </T>
        <T variant="small" tone="soft" className="flex-1 text-right">
          {m.estimate.colShop}
        </T>
        <T variant="small" tone="soft" className="flex-1 text-right">
          {m.estimate.colResale}
        </T>
      </View>
      {known.map((r) => {
        const mine = r.grade === grade || r.grade === upper;
        return (
          <View
            key={r.grade}
            className={cn(tr, 'min-h-touch py-2', mine && 'bg-gold-tint')}
            testID={`price-${r.grade}`}
            accessible
            accessibilityLabel={`${r.grade}, ${gradeName(r.grade, m)}${mine ? `, ${m.estimate.yourGrade}` : ''} : ${m.estimate.colShop} ${money(r.retail, currency, locale)}, ${m.estimate.colResale} ${money(r.resale, currency, locale)}`}
          >
            <View className="flex-[1.1]">
              <T variant="bodyStrong">{r.grade}</T>
              <T variant="small" tone="soft">
                {mine ? m.estimate.yourGrade : gradeName(r.grade, m)}
              </T>
            </View>
            <T variant={mine ? 'bodyStrong' : 'body'} className="flex-1 text-right">
              {money(r.retail, currency, locale)}
            </T>
            <T variant={mine ? 'bodyStrong' : 'body'} tone={mine ? 'gold' : 'ink'} className="flex-1 text-right">
              {money(r.resale, currency, locale)}
            </T>
          </View>
        );
      })}
      {sources.length > 0 && (
        <View key="sources-title" className="px-4 pb-1 pt-4">
          <T variant="smallStrong" tone="soft" accessibilityRole="header">
            {m.estimate.pricesUsed}
          </T>
        </View>
      )}
      {sources}
    </Section>
  );
}

/** Rows for every price the estimate rests on (with its value today), then Numista's for comparison. */
export function priceSources(est: Estimate, m: Messages, locale: string): ReactNode[] {
  const v = est.valuation;
  const grade = est.identification.grade;
  // Numista for comparison, unless its prices are already among those used
  const numista = v?.points?.some((p) => p.source === 'numista') ? null : est.numista;
  const numistaPrice = numista?.prices?.[grade];
  const rows: ReactNode[] = (v?.points ?? []).map((p, i) => {
    const when =
      p.source === 'numista' ? null : p.kind === 'listing' ? m.estimate.inStock : m.estimate.sold(String(p.year ?? ''));
    const moved = Math.abs(p.adjusted - p.price) > p.price * 0.01;
    return (
      <Row
        key={`point-${i}`}
        accessibilityRole={p.url ? 'link' : undefined}
        onPress={p.url ? () => Linking.openURL(p.url!) : undefined}
        chevron={!!p.url}
        stacked
        label={[p.grade, when, sourceLabel(p.source)].filter(Boolean).join(', ')}
        value={
          <View className="gap-0.5">
            {!!p.name && <T numberOfLines={2}>{p.name}</T>}
            <T variant="bodyStrong" tone="gold">
              {money(p.price, est.currency, locale)}
              {moved ? `  →  ${m.estimate.today(money(p.adjusted, est.currency, locale))}` : ''}
            </T>
          </View>
        }
      />
    );
  });
  if (numista && numistaPrice != null) {
    rows.push(
      <Row
        key="numista-compare"
        testID="numista-compare"
        accessibilityRole="link"
        onPress={() => Linking.openURL(numista.url)}
        chevron
        stacked
        label={m.estimate.numistaCompare(grade)}
        value={
          <View className="gap-0.5">
            {!!numista.title && <T numberOfLines={2}>{numista.title}</T>}
            <T variant="bodyStrong">{money(numistaPrice, est.currency, locale)}</T>
          </View>
        }
      />,
    );
  }
  return rows;
}

/** The catalog entry the coin was matched to, then the comparable listings. */
export function CatalogSection({ est, hidePrices }: { est: Estimate; hidePrices?: boolean }) {
  const { m } = useI18n();
  // the listings the price rests on are shown with the prices used
  const used = new Set(est.valuation?.best_match_ids ?? []);
  const comparables = est.comparables.filter((c) => c.id !== est.match?.id && !used.has(c.id)).slice(0, 6);
  const match = est.match;

  return (
    <>
      <Section title={m.estimate.catalogTitle} footer={match ? undefined : m.estimate.noMatch}>
        {match ? (
          <Row
            testID="catalog-match"
            accessibilityRole="link"
            accessibilityLabel={`${m.estimate.match} : ${match.name}. ${m.estimate.seeListing}`}
            onPress={() => Linking.openURL(match.url)}
            chevron
            stacked
            leading={<CoinWell size={64} uri={match.images[0]} icon="ellipse-outline" />}
            label={match.reason ?? m.estimate.matchWhy(match.criteria ?? [], match.similarity ?? null)}
            value={
              <View className="gap-0.5">
                <T variant="bodyStrong">{match.name}</T>
                <T variant="smallStrong" tone="accent">
                  {m.estimate.seeListing} {sourceLabel(match.source)}
                </T>
              </View>
            }
          />
        ) : est.numista ? (
          <Row
            testID="numista-link"
            accessibilityRole="link"
            onPress={() => Linking.openURL(est.numista!.url)}
            chevron
            stacked
            label={est.numista.title ?? m.estimate.seeNumista}
            value={
              <T variant="smallStrong" tone="accent">
                {m.estimate.seeNumista}
              </T>
            }
          />
        ) : (
          <Row label={m.estimate.noMatch} />
        )}
      </Section>

      {/* comparable listings are prices: none with prices hidden */}
      {comparables.length > 0 && !hidePrices && (
        <Section title={m.estimate.comparables}>
          {comparables.map((c) => (
            <ComparableRow key={c.id} c={c} />
          ))}
        </Section>
      )}
    </>
  );
}

function ComparableRow({ c }: { c: Comparable }) {
  const { m, locale } = useI18n();
  const when = c.in_stock ? m.estimate.inStock : m.estimate.sold(c.listed.slice(0, 4));
  return (
    <Row
      accessibilityRole="link"
      onPress={() => Linking.openURL(c.url)}
      chevron
      stacked
      leading={<CoinWell size={56} uri={c.images[0]} icon="ellipse-outline" />}
      label={[c.grade, when, sourceLabel(c.source)].filter(Boolean).join(', ')}
      value={
        <View className="gap-0.5">
          <T numberOfLines={2}>{c.name}</T>
          <T variant="bodyStrong" tone="gold">
            {money(c.price, c.currency, locale)}
          </T>
        </View>
      }
    />
  );
}
