import Ionicons from '@expo/vector-icons/Ionicons';
import { Image } from 'expo-image';
import * as Linking from 'expo-linking';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useI18n } from '../i18n';
import { CatalogMatch, GradePrice } from '../lib/api';
import { gradeName, money, sourceLabel } from '../lib/format';
import { colors, font } from '../lib/theme';
import { Card, Label } from './ui';

/** The catalog entry the coin was matched to: the reference for its facts and prices. */
export function MatchCard({ match }: { match: CatalogMatch }) {
  const { m } = useI18n();
  return (
    <Pressable
      onPress={() => Linking.openURL(match.url)}
      accessibilityRole="link"
      accessibilityLabel={`${m.estimate.match} : ${match.name}`}
      testID="catalog-match"
    >
      <Card style={{ borderColor: colors.success, borderWidth: 2 }}>
        <View style={styles.matchHeader}>
          <Ionicons name="checkmark-circle" size={24} color={colors.success} />
          <Label style={{ color: colors.success }}>{m.estimate.match}</Label>
        </View>
        <View style={styles.matchRow}>
          {match.images.slice(0, 2).map((uri) => (
            <Image key={uri} source={{ uri }} style={styles.matchImg} contentFit="cover" />
          ))}
        </View>
        <Text style={styles.matchName} selectable>
          {match.name}
        </Text>
        <Text style={styles.small}>
          {sourceLabel(match.source)} · {match.reason ?? m.estimate.matchWhy(match.criteria ?? [], match.similarity ?? null)}
        </Text>
      </Card>
    </Pressable>
  );
}

export function PriceTable({ rows, grade, currency }: { rows: GradePrice[]; grade: string; currency: string }) {
  const { m, locale } = useI18n();
  const known = rows.filter((r) => r.retail != null);
  if (!known.length) return null;
  return (
    <Card>
      <Label>{m.estimate.priceByGrade}</Label>
      <View style={[styles.tr, styles.th]}>
        <Text style={[styles.td, styles.gradeCol, styles.thText]} />
        <Text style={[styles.td, styles.thText]}>{m.estimate.colShop}</Text>
        <Text style={[styles.td, styles.thText]}>{m.estimate.colResale}</Text>
      </View>
      {known.map((r) => {
        const mine = r.grade === grade;
        return (
          <View key={r.grade} style={[styles.tr, mine && styles.mine]} testID={`price-${r.grade}`}>
            <View style={[styles.td, styles.gradeCol]}>
              <Text style={[styles.gradeText, mine && styles.bold]}>{gradeName(r.grade, m).split(' — ')[0]}</Text>
              {mine && <Text style={styles.mineText}>{m.estimate.yourGrade}</Text>}
            </View>
            <Text style={[styles.td, styles.num, mine && styles.bold]}>{money(r.retail, currency, locale)}</Text>
            <Text style={[styles.td, styles.num, mine && styles.bold]}>{money(r.resale, currency, locale)}</Text>
          </View>
        );
      })}
      <Text style={styles.small}>{m.estimate.priceNote}</Text>
    </Card>
  );
}

const styles = StyleSheet.create({
  matchHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  matchRow: { flexDirection: 'row', gap: 12, justifyContent: 'center' },
  matchImg: { width: 110, height: 110, borderRadius: 55, backgroundColor: colors.border },
  matchName: { fontSize: font.body, fontWeight: '700', color: colors.text },
  small: { fontSize: 15, color: colors.muted, lineHeight: 20 },
  tr: { flexDirection: 'row', alignItems: 'center', minHeight: 44, borderRadius: 8, paddingHorizontal: 6 },
  th: { minHeight: 28 },
  thText: { fontSize: 15, color: colors.muted, fontWeight: '700', textAlign: 'right' },
  td: { flex: 1 },
  gradeCol: { flex: 0.8 },
  gradeText: { fontSize: font.body, color: colors.text },
  num: { fontSize: font.body, color: colors.text, textAlign: 'right' },
  bold: { fontWeight: '800', color: colors.brassDark },
  mine: { backgroundColor: colors.brassLight },
  mineText: { fontSize: 13, color: colors.brassDark, fontWeight: '700' },
});
