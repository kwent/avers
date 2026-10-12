// Raw token values for code that cannot take a className (icon colours, navigation options, Reanimated).
// Everything else styles with Tailwind classes built from the same tokens (tailwind.config.js).
import { colors, fonts, metals, type } from './tokens';

export { colors, fonts, metals, type };

/** A coin well: the photo sits below the surface, lit from above. */
export const wellShadow = 'inset 0 6px 16px rgba(0, 0, 0, 0.8), inset 0 0 0 1.5px rgba(238, 193, 78, 0.55)';

/** Warm light around the coin on the home screen. */
export const glow = '0 0 60px rgba(238, 193, 78, 0.22)';

/** Title style of the navigation headers. */
export const headerTitleStyle = { fontFamily: fonts.strong, fontSize: type.heading[0], color: colors.cream };
