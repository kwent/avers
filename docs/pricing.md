# How Avers prices a coin

Plain code, no AI: `backend/app/pricing.py` (the rules), `backend/app/pipeline.py` (which data goes in),
`backend/app/metals.py` (gold and silver prices). The vision model only reads the coin; it never sets a price.

## 1. Which prices count

- **Catalog listings of that exact coin**: same country, face value, year and mint letter (and Gadoury number
  when both sides know it), confirmed by the photos looking like the listing's (`app/matching.py`). A listing
  still for sale is an asking price; one no longer in stock counts as sold.
- **Numista**, only when the catalog has no listing of the coin: Numista's price for each grade, treated like
  listings.
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

So the app shows about 2 008 € although the listing says 1 540 €: the 1 540 € was paid when gold was worth a third
of today's price.

## Known limits

- **One old listing decides alone.** With a single listing from 2014, the premium of that one sale is carried over
  ten years. Collector premiums do not necessarily follow gold; when there is only old data the figure is less
  sure.
- **Listings do not always rise with the grade.** An old listing with a big premium can price a TTB above a recent
  SUP (40 Francs Louis XVIII 1817 A). The range shown is kept in order, the table shows the data as it is.
- **The grade is read from photos**, and a grade apart changes the price a lot. Check it on the coin.
- **Numista's prices** are its own estimates per grade; when it has only one grade, other grades are bounded by
  the metal value and that one price.
