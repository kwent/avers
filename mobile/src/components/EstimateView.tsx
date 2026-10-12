import Ionicons from '@expo/vector-icons/Ionicons';
import { ReactNode } from 'react';
import { useWindowDimensions, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useI18n } from '../i18n';
import type { Messages } from '../i18n/fr';
import { Estimate } from '../lib/api';
import { confidence, gradeLabel, metalName, money, number, range } from '../lib/format';
import { colors } from '../theme';
import { CopyAllButton, CopyProvider, CopyRow } from './Copy';
import { CatalogSection, PriceTable } from './Market';
import { Band, CoinWell, Metal, Notice, Row, Section, T, Tone } from './ui';

type Field = { id: string; label: string; value: string };

/** Record fields shown (and copied) for an estimate, in display order; empty values are skipped. */
function detailFields(est: Estimate, m: Messages, locale: string): Field[] {
  const coin = est.identification;
  const fields: (Field | false)[] = [
    {
      id: 'country',
      label: m.estimate.country,
      value: coin.country_name ?? '',
    },
    {
      id: 'year',
      label: m.estimate.year,
      value: coin.year != null ? String(coin.year) : '',
    },
    { id: 'mint', label: m.estimate.mint, value: coin.mint_mark ?? '' },
    { id: 'face', label: m.estimate.faceValue, value: coin.denomination ?? '' },
    { id: 'metal', label: m.estimate.metal, value: metalName(coin.metal, m) },
    coin.fineness != null && {
      id: 'fineness',
      label: m.estimate.fineness,
      value: `${Math.round(coin.fineness * 1000)} ‰`,
    },
    coin.weight_g != null && {
      id: 'weight',
      label: m.estimate.weight,
      value: `${number(coin.weight_g, locale)} g`,
    },
    { id: 'refs', label: m.estimate.refs, value: coin.catalog_refs.join(', ') },
    { id: 'grade', label: m.estimate.grade, value: gradeLabel(coin.grade, m) },
  ];
  return fields.filter((f): f is Field => !!f && !!f.value);
}

/** Plain-text summary of the whole estimate, for "Copy the record". */
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
  const years =
    first_year && last_year ? (first_year === last_year ? `${first_year}` : `${first_year}–${last_year}`) : null;
  const parts = [m.estimate.basisListings(listings, years)];
  if (est.melt && metal_share != null)
    parts.push(m.estimate.basisMetal(money(est.melt.value, est.currency, locale), Math.round(metal_share * 100)));
  parts.push(m.estimate.basisResale);
  return parts.join(' ');
}

/**
 * The estimate of one coin. `children` (e.g. the collection controls of a saved coin) is placed right after the
 * answer, before the details.
 */
export function EstimateView(props: { est: Estimate; photos: (string | undefined)[]; children?: ReactNode }) {
  return (
    <CopyProvider>
      <EstimateContent {...props} />
    </CopyProvider>
  );
}

function EstimateContent({
  est,
  photos,
  children,
}: {
  est: Estimate;
  photos: (string | undefined)[];
  children?: ReactNode;
}) {
  const { m, locale } = useI18n();
  const { width } = useWindowDimensions();
  const coin = est.identification;
  const cur = est.currency;
  const v = est.valuation;
  const shown = photos.filter(Boolean);
  const well = Math.min(168, (Math.min(width, 600) - 2 * 20 - 16) / 2);
  const conf = confidence(coin.confidence, m);
  const status: { text: string; tone: Tone; color: string; icon: 'checkmark-circle' | 'help-circle' } = est.match
    ? { text: m.estimate.match, tone: 'success', color: colors.success, icon: 'checkmark-circle' }
    : est.year_check
      ? { text: m.estimate.yearCheck, tone: 'warning', color: colors.warning, icon: 'help-circle' }
      : {
          text: conf.text,
          tone: conf.tone,
          color: colors[conf.tone],
          icon: conf.tone === 'success' ? 'checkmark-circle' : 'help-circle',
        };
  const worth = v ? range(v.value_low, v.value_high, cur, locale) : '';

  return (
    <View>
      <Band className="flex-row justify-center gap-4">
        {shown.map((uri) => (
          <CoinWell key={uri} size={well} uri={uri} />
        ))}
      </Band>

      <View className="gap-6 p-gutter">
        <View className="gap-1">
          <T variant="title" accessibilityRole="header" selectable>
            {coin.title}
          </T>
          {!!coin.type_name && (
            <T tone="soft" selectable>
              {coin.type_name}
            </T>
          )}
          <View className="mt-1 flex-row items-center gap-1">
            <Ionicons name={status.icon} size={22} color={status.color} />
            <T variant="smallStrong" tone={status.tone}>
              {status.text}
            </T>
          </View>
        </View>

        {!!coin.authenticity_notes && (
          <Notice tone="danger" title={m.estimate.attention}>
            {coin.authenticity_notes}
          </Notice>
        )}
        {est.photo_warning === 'same_side' && <Notice tone="warning">{m.estimate.sameSide}</Notice>}
        {!!est.already_owned && <Notice>{m.estimate.alreadyOwned(est.already_owned)}</Notice>}

        {v ? (
          // the one animated moment: the answer settles in
          <Animated.View
            entering={FadeInDown.duration(450)}
            accessible
            accessibilityLabel={`${m.estimate.value} : ${worth}`}
          >
            <T tone="soft">{m.estimate.worthLead}</T>
            <T variant="display" tone="gold" selectable>
              {worth}
            </T>
            <T tone="soft">{m.estimate.worthSub}</T>
            {v.retail_low != null && (
              <T variant="bodyStrong" className="mt-2">
                {m.estimate.shopPrice(range(v.retail_low, v.retail_high, cur, locale))}
              </T>
            )}
          </Animated.View>
        ) : (
          // No reliable price: say so plainly, and give the one sure figure, the metal value, as a floor.
          <View className="gap-3">
            {est.melt ? (
              <View accessible accessibilityLabel={`${m.estimate.worthAtLeast} ${money(est.melt.value, cur, locale)}`}>
                <T tone="soft">{m.estimate.worthAtLeast}</T>
                <T variant="display" tone="gold" selectable>
                  {money(est.melt.value, cur, locale)}
                </T>
                <T tone="soft">{m.estimate.metalFloor(metalName(est.melt.metal, m))}</T>
              </View>
            ) : (
              <T variant="title">{m.estimate.unknownPrice}</T>
            )}
            {/* with a year to check, the question (children) explains instead: the price may follow */}
            {!est.year_check && <Notice>{m.estimate.noPrice}</Notice>}
          </View>
        )}

        {children}

        {v && (
          <PriceTable
            rows={est.price_table ?? []}
            grade={coin.grade}
            currency={cur}
            explanation={explanation(est, m, locale)}
          />
        )}

        {est.melt && (
          <Section
            title={m.estimate.metalTitle}
            footer={m.estimate.meltExplain(
              number(est.melt.pure_metal_g, locale),
              metalName(est.melt.metal, m),
              money(est.melt.spot_per_gram, cur, locale, 2),
            )}
          >
            <Row
              label={m.estimate.metal}
              value={<Metal metal={est.melt.metal} name={metalName(est.melt.metal, m)} />}
            />
            <Row
              label={m.estimate.melt}
              value={
                <T variant="bodyStrong" tone="gold">
                  {money(est.melt.value, cur, locale, 2)}
                </T>
              }
            />
          </Section>
        )}

        <Section
          title={m.estimate.details}
          action={<CopyAllButton text={summary(est, m, locale)} />}
          footer={m.estimate.tapToCopy}
        >
          {detailFields(est, m, locale).map((f) => (
            <CopyRow key={f.id} id={f.id} label={f.label} value={f.value} />
          ))}
        </Section>
        {[coin.grade_notes, coin.notes].filter(Boolean).map((text) => (
          <T key={text} tone="soft" selectable className="px-1">
            {text}
          </T>
        ))}

        <CatalogSection est={est} />
      </View>
    </View>
  );
}
