const { colors, fonts, type } = require('./src/theme/tokens');

const px = (n) => `${n}px`;

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  // light only for now; 'class' (not 'media') lets navigation set the scheme on web without NativeWind errors
  darkMode: 'class',
  theme: {
    extend: {
      colors,
      fontFamily: {
        regular: [fonts.regular],
        strong: [fonts.strong],
        heavy: [fonts.heavy],
      },
      fontSize: Object.fromEntries(
        Object.entries(type).map(([name, [size, lineHeight]]) => [name, [px(size), { lineHeight: px(lineHeight) }]]),
      ),
      spacing: { gutter: '20px', touch: '56px', action: '64px' },
      borderRadius: { sm: '10px', md: '14px', lg: '22px' },
    },
  },
  plugins: [],
};
