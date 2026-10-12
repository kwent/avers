/**
 * Avers design tokens, the single source of truth: Tailwind (tailwind.config.js) and code that needs raw values
 * (icon colours, navigation headers, Reanimated) both read this file.
 *
 * "Noir & or", the palette of the app icon: a coin under a lamp on a black-brown ground.
 * - Ground and surfaces are warm near-blacks taken from the icon; text is a warm cream (≥ 12:1, readable for
 *   older eyes).
 * - Gold is the accent: actions, and every amount of money, so a price is always recognisable at a glance.
 * - Coins sit in dark round wells with a thin gold rim, like trays in a coin cabinet.
 * - The coin's own metal has its colour, shown as a small swatch next to its name.
 * - Lexend: drawn to reduce visual stress and help reading fluency.
 */

const colors = {
  ground: '#110E0A', // page background (the icon's black-brown, a shade deeper)
  surface: '#1C1813', // grouped lists, cards
  raised: '#272119', // pressed rows, inputs
  line: '#382F23', // hairlines
  well: '#0A0806', // coin wells, photo backdrops
  cream: '#F5EEDF', // text
  'cream-soft': '#B8AC96', // secondary text (≥ 7:1 on ground)
  gold: '#EEC14E', // accent and money (the icon's gold)
  'gold-deep': '#BE7E27', // pressed accent, coin rims
  'gold-tint': '#2E2513', // selected rows, soft fills
  'on-gold': '#1A1408', // text on gold buttons
  success: '#7BCB8F',
  warning: '#E8A54B',
  danger: '#EE6F5F',
};

/** Swatch for the coin's metal (decorative; always paired with the metal's name). */
const metals = {
  gold: '#C9A227',
  silver: '#A9B1B6',
  platinum: '#C9CCCB',
  palladium: '#BFC3C1',
  billon: '#9C9A8C',
  copper: '#B0683A',
  bronze: '#9A6A3A',
  nickel: '#A4A9A5',
  aluminium: '#C4C8CA',
  steel: '#8E9497',
  zinc: '#9FA5A6',
};

/** Font family names, as registered with expo-font in app/_layout.tsx. */
const fonts = {
  regular: 'Lexend-Regular',
  strong: 'Lexend-SemiBold',
  heavy: 'Lexend-Bold',
};

/** Type ramp for older readers (Lexend runs wide: body 18 reads like 19-20 elsewhere). [size, lineHeight] */
const type = {
  display: [44, 52],
  title: [27, 34],
  heading: [20, 27],
  body: [18, 27],
  small: [15.5, 23],
  button: [19, 26],
};

module.exports = { colors, metals, fonts, type };
