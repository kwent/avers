import { Image } from 'expo-image';
import * as Linking from 'expo-linking';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Comparable, Estimate } from '../lib/api';
import { confidenceLabel, GRADES_FR, METALS_FR, money, range, sourceLabel } from '../lib/format';
import { colors, font } from '../lib/theme';
import { Card, Label, Pill, Row } from './ui';

export function EstimateView({ est, photos }: { est: Estimate; photos: (string | undefined)[] }) {
  const coin = est.identification;
  const cur = est.currency;
  const conf = confidenceLabel(coin.confidence);
  const best = new Set(est.valuation?.best_match_ids ?? []);
  const comparables = [...est.comparables].sort((a, b) => Number(best.has(b.id)) - Number(best.has(a.id)));

  return (
    <View style={{ gap: 16 }}>
      <View style={styles.photos}>
        {photos.filter(Boolean).map((uri) => (
          <Image key={uri} source={{ uri }} style={styles.photo} contentFit="cover" />
        ))}
      </View>

      <View style={{ gap: 8 }}>
        <Text style={styles.title}>{coin.title}</Text>
        {!!coin.type_name && <Text style={styles.subtitle}>{coin.type_name}</Text>}
        <Pill text={conf.text} tone={conf.tone} />
      </View>

      {!!coin.authenticity_notes && (
        <Card style={{ borderColor: colors.danger, borderWidth: 2 }}>
          <Text style={[styles.body, { color: colors.danger, fontWeight: '700' }]}>Attention</Text>
          <Text style={styles.body}>{coin.authenticity_notes}</Text>
        </Card>
      )}

      {!!est.already_owned && (
        <Card style={{ borderColor: colors.warning, borderWidth: 2 }}>
          <Text style={styles.body}>
            Vous avez déjà {est.already_owned > 1 ? `${est.already_owned} pièces` : 'une pièce'} comme celle-ci dans votre collection.
          </Text>
        </Card>
      )}

      <Card style={{ backgroundColor: colors.brassLight, borderColor: colors.brass }}>
        <Label>Valeur estimée</Label>
        {est.valuation ? (
          <>
            <Text style={styles.hero}>{range(est.valuation.value_low, est.valuation.value_high, cur)}</Text>
            {est.valuation.retail_low != null && (
              <Text style={styles.body}>
                Prix en boutique : {range(est.valuation.retail_low, est.valuation.retail_high, cur)}
              </Text>
            )}
            <Text style={styles.explain}>{est.valuation.explanation}</Text>
          </>
        ) : (
          <Text style={styles.body}>Estimation indisponible pour le moment.</Text>
        )}
      </Card>

      {est.melt && (
        <Card>
          <Label>Valeur du métal (minimum)</Label>
          <Text style={styles.big}>{money(est.melt.value, cur, 2)}</Text>
          <Text style={styles.explain}>
            {est.melt.pure_metal_g.toLocaleString('fr-FR')} g de {METALS_FR[est.melt.metal]?.toLowerCase()} pur ×{' '}
            {money(est.melt.spot_per_gram, cur, 2)}/g, cours du jour.
          </Text>
        </Card>
      )}

      <Card>
        <Label>Détails</Label>
        <Row label="Pays" value={coin.country_name ?? '—'} />
        <Row label="Année" value={coin.year ?? '—'} />
        {!!coin.mint_mark && <Row label="Atelier" value={coin.mint_mark} />}
        <Row label="Valeur faciale" value={coin.denomination ?? '—'} />
        <Row label="Métal" value={METALS_FR[coin.metal] ?? coin.metal} />
        {coin.fineness != null && <Row label="Titre" value={`${Math.round(coin.fineness * 1000)} ‰`} />}
        {coin.weight_g != null && <Row label="Poids" value={`${coin.weight_g.toLocaleString('fr-FR')} g`} />}
        {coin.catalog_refs.length > 0 && <Row label="Références" value={coin.catalog_refs.join(', ')} />}
        <Row label="État estimé" value={GRADES_FR[coin.grade] ?? coin.grade} />
        {!!coin.grade_notes && <Text style={styles.explain}>{coin.grade_notes}</Text>}
        {!!coin.notes && <Text style={styles.explain}>{coin.notes}</Text>}
      </Card>

      {comparables.length > 0 && (
        <View style={{ gap: 10 }}>
          <Label>Pièces comparables chez les marchands</Label>
          {comparables.slice(0, 8).map((c) => (
            <ComparableRow key={c.id} c={c} highlighted={best.has(c.id)} />
          ))}
        </View>
      )}
    </View>
  );
}

function ComparableRow({ c, highlighted }: { c: Comparable; highlighted: boolean }) {
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
            {c.grade ?? '—'} · {c.in_stock ? 'En vente' : `Vendu (${c.listed.slice(0, 4)})`} · {sourceLabel(c.source)}
          </Text>
          <Text style={styles.compPrice}>{money(c.price, c.currency)}</Text>
        </View>
      </Card>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  photos: { flexDirection: 'row', gap: 12, justifyContent: 'center' },
  photo: { width: 150, height: 150, borderRadius: 75, borderWidth: 3, borderColor: colors.brass, backgroundColor: '#000' },
  title: { fontSize: font.title, fontWeight: '800', color: colors.text },
  subtitle: { fontSize: font.body, color: colors.muted },
  hero: { fontSize: font.hero, fontWeight: '800', color: colors.brassDark },
  big: { fontSize: font.title, fontWeight: '800', color: colors.text },
  body: { fontSize: font.body, color: colors.text, lineHeight: 26 },
  explain: { fontSize: font.small, color: colors.muted, lineHeight: 22 },
  comp: { flexDirection: 'row', gap: 12, alignItems: 'center', padding: 12 },
  compImg: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.border },
  compName: { fontSize: font.small, fontWeight: '700', color: colors.text },
  compMeta: { fontSize: 15, color: colors.muted },
  compPrice: { fontSize: font.large, fontWeight: '800', color: colors.text },
});
