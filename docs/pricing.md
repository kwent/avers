# How Avers prices a coin

Plain code, no AI: `backend/app/pricing.py` (the rules), `backend/app/pipeline.py` (which data goes in),
`backend/app/metals.py` (gold and silver prices). The vision model only reads the coin; it never sets a price.

## 1. Which prices count

- **Catalog listings of that exact coin**: same country, face value, year and mint letter (and Gadoury number
  when both sides know it), confirmed by the photos looking like the listing's (`app/matching.py`). A listing
  still for sale is an asking price; one no longer in stock counts as sold.
- **Numista**, only when the catalog has no listing of the coin: Numista's price for each grade, treated like
  listings.
- The catalog is read again every week (new listings, new prices, listings gone out of stock), so recent prices
  reach the estimates without a redeploy.
- Nothing else. No listing and no Numista price means no price: the app says so and shows the metal value as a
  floor ("Elle vaut au moins …").

## 2. Old prices brought to today's metal price

A gold coin's price is its metal plus a collector premium. Gold has moved a lot (about 1 270 $/oz in 2014,
about 4 000 $/oz now), so a 2014 price says little on its own. For each dated price of a gold or silver coin:

```
premium        = price then − metal value then      (metal value at that year's average gold/silver price)
today's price  = premium + metal value today         (live spot price)
```

The premium is kept in euros. Prices from this year are used as they are.

Why this rule: the backtest below compared it with other ways of bringing an old price to today, and it predicts
today's prices best.

## 3. One price per grade

Grades: B, TB, TTB, SUP, SPL, FDC. For each grade, the weighted median of its prices:

- recent prices weigh more (a price 3 years old counts half as much as this year's);
- sold prices weigh 1.5× an asking price; undated ones little;
- a half grade ("TTB-SUP", "TTB+") counts for both neighbours.

Grades with no price between two that have one are filled in geometrically (prices rise by a factor per grade).
Every grade's shop price is at least the metal value + 5 %.

## 4. The estimate for the coin's grade

- **Shop price** (what a dealer would ask): from half a grade below to half a grade above the coin's grade
  (geometric midpoints with the neighbouring grades).
- **Between private collectors** (the big number in the app): 80 % of the shop price, as dealers buy about 20 %
  under their selling price. Never below the metal value.
- **Few or old prices** (a single price, or the newest 7+ years old): Numista's current price per grade is added
  to the listings, and the range reaches down to the price ÷ 1.4, never below the metal value. The backtest shows
  such estimates miss by ~40% and come out too high. The app says so under the price.
- **Sure value**: the metal value is shown under the price as what a dealer pays for the metal in the coin.
- **Graded below every listed grade**: between the metal value and the next listed grade's price.
- **Graded above every listed grade**: no price (nothing to bound it).
- No grade read: no price.

## 5. Worked example: 40 Francs Napoléon Ier 1812 A, TTB

The catalog's only listing: [FRANCE-1812A-40 FRANCS or-TTB](https://www.gadoury.com/fr/monnaies/france-1812a-40-francs-or-ttb),
**1 540 €, sold in 2014**.

| Step | Value |
|---|---|
| Gold in the coin | 12.9 g at 900/1000 = 11.61 g |
| Its metal value in 2014 (gold ≈ 1 266 $/oz) | 423 € |
| Premium in 2014 | 1 540 − 423 = 1 117 € |
| Its metal value today | 1 392 € |
| Shop price today | 1 117 + 1 392 = **2 509 €** |
| Between private collectors (80 %) | **2 007 €** |
| Only one price, from 2014: range reaches down to 2 509 ÷ 1.4 | shop 1 792–2 509 €, private 1 434–2 007 € |

So the app shows about 1 434–2 007 € although the listing says 1 540 €: the 1 540 € was paid when gold was worth a
third of today's price, and a single old sale makes the figure less sure.

## Backtest

`uv run python -m bench.pricing` (from `backend/`) prices each French gold coin's 2025–2026 listings from its
older listings only, with the production code, and compares. On 43 such listings (October 2026):

| Old price brought to today by | Median error | Median bias | Within 15 % |
|---|---|---|---|
| nothing (the old price as is) | 33 % | −24 % | 19 % |
| **premium kept + today's metal value** (the rule) | **18 %** | **≈ 0 %** | **44 %** |
| the whole price scaled with gold | 72 % | +68 % | 16 % |
| the premium halving every 8 years | 23 % | −14 % | 35 % |

| Data behind the estimate | Median error | Median bias |
|---|---|---|
| newest price 1–6 years old | 14–18 % | ≈ 0 % |
| newest price 7+ years old | 38 % | +18 % |
| a single price | 45 % | |

The sample is small; rerun it when the catalog is refreshed.

## Known limits

- **One old listing decides alone.** With a single listing from 2014, the premium of that one sale is carried over
  twelve years; the range is widened downward (above), but the central figure is still that sale's.
- **Listings do not always rise with the grade.** An old listing with a big premium can price a TTB above a recent
  SUP (40 Francs Louis XVIII 1817 A). The range shown is kept in order, the table shows the data as it is.
- **The grade is read from photos**, and a grade apart changes the price a lot. Check it on the coin.
- **Numista's prices** are its own estimates per grade; when it has only one grade, other grades are bounded by
  the metal value and that one price.
