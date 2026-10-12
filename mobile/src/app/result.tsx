import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { EstimateView } from '../components/EstimateView';
import { YearCheck } from '../components/YearCheck';
import { ActionBar, Button, CoinWell, Notice, success, T } from '../components/ui';
import { errorText, useI18n } from '../i18n';
import { addItem, correctYear, Estimate, estimate } from '../lib/api';
import { resetScan, scan } from '../lib/scanStore';
import { useSettings } from '../lib/settings';
import { colors } from '../theme';

export default function ResultScreen() {
  const { settings } = useSettings();
  const { m, language } = useI18n();
  const insets = useSafeAreaInsets();
  const [est, setEst] = useState<Estimate | null>(scan.estimate);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // kept in the scan too, so coming back to this screen shows the same estimate
  const show = (e: Estimate) => {
    scan.estimate = e;
    setEst(e);
  };

  const run = () => {
    if (!scan.front) return setError(m.result.noPhoto);
    setError(null);
    estimate(settings, scan.front, scan.back, language)
      .then((e) => {
        show(e);
        success();
      })
      .catch((e) => setError(errorText(e, m)));
  };

  useEffect(() => {
    if (!est) run();
  }, []);

  const setYear = async (year: number) => {
    if (!est) return;
    try {
      const e = await correctYear(settings, est, year);
      show(e);
      if (e.valuation) success();
    } catch (e) {
      setError(errorText(e, m));
    }
  };

  const save = async () => {
    if (!est) return;
    setSaving(true);
    try {
      const item = await addItem(settings, est);
      success();
      resetScan();
      router.dismissAll();
      router.push({ pathname: '/item/[id]', params: { id: String(item.id) } });
    } catch (e) {
      setError(errorText(e, m));
    } finally {
      setSaving(false);
    }
  };

  if (error) {
    return (
      <View className="flex-1 justify-center gap-4 p-gutter">
        <Notice tone="danger">{error}</Notice>
        <Button title={m.result.retry} icon="refresh" onPress={run} />
        <Button title={m.result.retake} variant="secondary" onPress={() => router.replace('/scan')} />
      </View>
    );
  }

  if (!est) {
    return (
      <View className="flex-1 items-center justify-center gap-4 p-gutter">
        <View>
          <CoinWell size={160} uri={scan.front} />
          <View className="absolute inset-0 items-center justify-center rounded-full bg-well/45">
            <ActivityIndicator size="large" color={colors.cream} />
          </View>
        </View>
        <T variant="heading" className="text-center" accessibilityLiveRegion="polite">
          {m.result.analyzing}
        </T>
        <T tone="soft" className="text-center">
          {m.result.analyzingHint}
        </T>
      </View>
    );
  }

  const coin = est.identification;
  if (coin.status !== 'identified') {
    const notCoin = coin.status === 'not_a_coin';
    return (
      <ScrollView contentContainerClassName="grow justify-center gap-4 p-gutter">
        <View className="items-center">
          <CoinWell size={140} uri={scan.front} />
        </View>
        <T variant="title" className="text-center" testID="not-identified" accessibilityRole="header">
          {notCoin ? m.result.notCoin : m.result.unidentifiable}
        </T>
        <T className="text-center">{coin.status_reason || m.result.unidentifiableFallback}</T>
        {!notCoin && (
          <T tone="soft" className="text-center">
            {m.result.unidentifiableHint}
          </T>
        )}
        <Button title={m.result.retake} icon="camera" onPress={() => router.replace('/scan')} />
        <Button title={m.home.fromLibrary} variant="secondary" onPress={() => router.replace('/pick')} />
      </ScrollView>
    );
  }

  // the local photos, in the order the API settled on (obverse first)
  const shown = est.photos.swapped ? [scan.back, scan.front] : [scan.front, scan.back];

  return (
    <View className="flex-1">
      <ScrollView contentContainerClassName="pb-6">
        <EstimateView est={est} photos={shown.map((p) => p ?? undefined)}>
          {est.year_check && (
            <YearCheck read={est.year_check.read} suggestions={est.year_check.suggestions} onYear={setYear} />
          )}
        </EstimateView>
        <View className="gap-4 px-gutter">
          <Button
            title={m.result.scanAnother}
            variant="secondary"
            icon="camera-outline"
            onPress={() => router.replace('/scan')}
          />
          <T variant="small" tone="soft" className="text-center">
            {m.result.disclaimer}
          </T>
        </View>
      </ScrollView>
      {/* the main action stays within thumb reach while reading the details */}
      <ActionBar bottomInset={insets.bottom}>
        <Button title={m.result.add} icon="add-circle-outline" onPress={save} loading={saving} />
      </ActionBar>
    </View>
  );
}
