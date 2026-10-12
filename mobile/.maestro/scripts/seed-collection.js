// Fills the throwaway test collection with four saved coins of different metals, grades and years (no AI call).
// Deletes whatever an earlier run left first, so counts are exact.
const headers = { 'Content-Type': 'application/json' };
const old = json(http.get(`${API_URL}/collection`).body).items;
for (const item of old) http.request(`${API_URL}/collection/${item.id}`, { method: 'DELETE' });

const coins = [
  ['20 Francs Napoléon Ier 1812 A', 'FR', 1812, '20 Francs', 'gold', 0.9, 6.45, 'SUP', 420, 480],
  ['Écu de Louis XV au bandeau 1765', 'FR', 1765, '1 Écu', 'silver', 0.917, 29.49, 'TB', 180, 240],
  ['5 Francs Semeuse 1960', 'FR', 1960, '5 Francs', 'silver', 0.835, 12, 'TTB', 14, 18],
  ['10 Centimes Napoléon III 1855', 'FR', 1855, '10 Centimes', 'bronze', null, 10, 'B', null, null],
];
for (const [title, country_iso, year, denomination, metal, fineness, weight_g, grade, low, high] of coins) {
  const estimate = {
    currency: 'EUR',
    identification: { title, country_iso, year, denomination, metal, fineness, weight_g, grade },
    valuation: low == null ? null : { value_low: low, value_high: high },
  };
  const r = http.post(`${API_URL}/collection`, { headers, body: JSON.stringify({ estimate }) });
  if (r.status !== 200) throw new Error(`seeding ${title}: HTTP ${r.status} ${r.body}`);
}
