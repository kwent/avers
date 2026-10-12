import Ionicons from '@expo/vector-icons/Ionicons';
import { Image } from 'expo-image';
import { Children, ComponentProps, Fragment, isValidElement, ReactNode } from 'react';
import { ActivityIndicator, Pressable, PressableProps, Text, TextProps, View, ViewStyle } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';
import { colors, glow as glowShadow, metals, wellShadow } from '../theme';
import { success, thud, tick } from '../lib/platform/haptics';

type IconName = ComponentProps<typeof Ionicons>['name'];

export const cn = (...classes: (string | false | null | undefined)[]) => classes.filter(Boolean).join(' ');

export { success, thud, tick };

// ---------------------------------------------------------------- text

const variants = {
  display: 'font-heavy text-display tracking-tight',
  title: 'font-heavy text-title',
  heading: 'font-strong text-heading',
  body: 'font-regular text-body',
  bodyStrong: 'font-strong text-body',
  small: 'font-regular text-small',
  smallStrong: 'font-strong text-small',
  button: 'font-strong text-button',
};

const tones = {
  ink: 'text-cream', // body text
  soft: 'text-cream-soft', // secondary text
  gold: 'text-gold', // money
  accent: 'text-gold', // links, actions
  onAccent: 'text-on-gold', // text on a gold fill
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-danger',
};

export type Tone = keyof typeof tones;

/** Text in one of the type styles and tones of the theme (className is for layout). */
export function T({
  variant = 'body',
  tone = 'ink',
  className,
  ...props
}: TextProps & { variant?: keyof typeof variants; tone?: Tone; className?: string }) {
  return <Text className={cn(variants[variant], tones[tone], className)} {...props} />;
}

// ---------------------------------------------------------------- press feedback

/** Pressable that sinks slightly under the finger and ticks, like a physical button. */
export function Press({
  children,
  className,
  haptic = true,
  scaleTo = 0.97,
  onPressIn,
  ...props
}: PressableProps & { className?: string; children: ReactNode; haptic?: boolean; scaleTo?: number }) {
  const scale = useSharedValue(1);
  const style = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  return (
    <Animated.View style={style}>
      <Pressable
        {...props}
        className={className}
        onPressIn={(e) => {
          scale.value = withSpring(scaleTo, { damping: 20, stiffness: 400 });
          if (haptic) tick();
          onPressIn?.(e);
        }}
        onPressOut={() => {
          scale.value = withSpring(1, { damping: 15, stiffness: 300 });
        }}
      >
        {children}
      </Pressable>
    </Animated.View>
  );
}

// ---------------------------------------------------------------- buttons

const buttons = {
  primary: { box: 'bg-gold border-gold active:bg-gold-deep', tone: 'onAccent', icon: colors['on-gold'] },
  secondary: { box: 'bg-transparent border-gold active:bg-gold-tint', tone: 'accent', icon: colors.gold },
  quiet: { box: 'border-transparent active:opacity-60', tone: 'accent', icon: colors.gold },
  danger: { box: 'border-transparent active:opacity-60', tone: 'danger', icon: colors.danger },
} as const;

export function Button({
  title,
  onPress,
  variant = 'primary',
  icon,
  loading,
  disabled,
  className,
  testID,
}: {
  title: string;
  onPress: () => void;
  variant?: keyof typeof buttons;
  icon?: IconName;
  loading?: boolean;
  disabled?: boolean;
  className?: string;
  testID?: string;
}) {
  const v = buttons[variant];
  const compact = variant === 'quiet' || variant === 'danger';
  return (
    <Press
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={title}
      accessibilityState={{ disabled: !!(disabled || loading), busy: !!loading }}
      onPress={onPress}
      disabled={disabled || loading}
      className={cn(
        'flex-row items-center justify-center gap-3 rounded-full border-2 px-6',
        compact ? 'min-h-touch' : 'min-h-action',
        v.box,
        disabled && 'opacity-40',
        className,
      )}
    >
      {loading ? <ActivityIndicator color={v.icon} /> : icon && <Ionicons name={icon} size={26} color={v.icon} />}
      <T variant="button" tone={v.tone}>
        {title}
      </T>
    </Press>
  );
}

// ---------------------------------------------------------------- surfaces

/** The header area that opens the main screens. */
export function Band({ children, className, style }: { children: ReactNode; className?: string; style?: ViewStyle }) {
  return (
    <View className={cn('gap-4 bg-ground px-gutter py-6', className)} style={style}>
      {children}
    </View>
  );
}

/**
 * A coin well: a round, recessed hollow with a thin gold rim, as in a coin cabinet tray. Holds a photo, or an icon
 * while empty. Pressable when given onPress (the empty well on the home screen is the camera button).
 */
export function CoinWell({
  size,
  uri,
  icon,
  label,
  onPress,
  accessibilityLabel,
  testID,
  glow,
}: {
  size: number;
  uri?: string | null;
  icon?: IconName;
  label?: string;
  onPress?: () => void;
  accessibilityLabel?: string;
  testID?: string;
  glow?: boolean; // warm light around it (the home screen's camera well)
}) {
  const circle = { width: size, height: size, borderRadius: size / 2 };
  const content = (
    <View style={[circle, glow && { boxShadow: glowShadow }]} className="bg-well">
      <View style={circle} className="overflow-hidden">
        {uri ? (
          <Image source={{ uri }} style={circle} contentFit="cover" transition={150} />
        ) : (
          <View style={circle} className="items-center justify-center gap-1">
            {icon && <Ionicons name={icon} size={size * 0.26} color={colors.gold} />}
            {label && (
              <T variant="bodyStrong" tone="accent">
                {label}
              </T>
            )}
          </View>
        )}
        {/* the rim and inner shadow sit above the photo */}
        <View pointerEvents="none" className="absolute inset-0" style={[circle, { boxShadow: wellShadow }]} />
      </View>
    </View>
  );
  if (!onPress) return content;
  return (
    <Press
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      onPress={onPress}
      scaleTo={0.95}
    >
      {content}
    </Press>
  );
}

/** A titled group of rows on a raised surface, separated by hairlines (iOS grouped list). */
export function Section({
  title,
  action,
  footer,
  children,
  className,
}: {
  title?: string;
  action?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const rows = Children.toArray(children).filter(isValidElement);
  return (
    <View className={cn('gap-2', className)}>
      {(title || action) && (
        <View className="flex-row items-center justify-between gap-3 px-1">
          {title && (
            <T variant="heading" accessibilityRole="header" className="shrink">
              {title}
            </T>
          )}
          {action}
        </View>
      )}
      <View className="overflow-hidden rounded-md bg-surface">
        {rows.map((row, i) => (
          <Fragment key={row.key ?? i}>
            {i > 0 && <View className="ml-4 h-px bg-line" />}
            {row}
          </Fragment>
        ))}
      </View>
      {typeof footer === 'string' ? (
        <T variant="small" tone="soft" className="px-1">
          {footer}
        </T>
      ) : (
        footer
      )}
    </View>
  );
}

/** A row in a Section: label on the left, value (or anything) on the right. */
export function Row({
  label,
  value,
  leading,
  onPress,
  chevron,
  selected,
  testID,
  accessibilityLabel,
  accessibilityRole,
  stacked,
}: {
  label: ReactNode;
  value?: ReactNode;
  leading?: ReactNode;
  onPress?: () => void;
  chevron?: boolean;
  selected?: boolean;
  testID?: string;
  accessibilityLabel?: string;
  accessibilityRole?: 'button' | 'radio' | 'link';
  stacked?: boolean; // label above value, for long values
}) {
  const labelNode =
    typeof label === 'string' ? (
      <T variant={stacked ? 'small' : 'body'} tone={stacked ? 'soft' : 'ink'} className="shrink">
        {label}
      </T>
    ) : (
      label
    );
  const valueNode =
    typeof value === 'string' || typeof value === 'number' ? (
      <T variant="bodyStrong" className={stacked ? undefined : 'shrink text-right'} selectable={!onPress}>
        {value}
      </T>
    ) : (
      value
    );
  const body = (
    <>
      {leading}
      <View className={stacked ? 'flex-1 gap-0.5' : 'flex-1 flex-row items-center justify-between gap-3'}>
        {labelNode}
        {valueNode}
      </View>
      {selected && <Ionicons name="checkmark" size={26} color={colors.gold} />}
      {chevron && <Ionicons name="chevron-forward" size={24} color={colors['cream-soft']} />}
    </>
  );
  const box = 'min-h-touch flex-row items-center gap-3 px-4 py-3';
  if (!onPress) return <View className={box}>{body}</View>;
  return (
    <Pressable
      testID={testID}
      accessibilityRole={accessibilityRole ?? 'button'}
      accessibilityLabel={accessibilityLabel}
      accessibilityState={selected != null ? { selected } : undefined}
      onPress={onPress}
      onPressIn={tick}
      className={cn(box, 'active:bg-raised')}
    >
      {body}
    </Pressable>
  );
}

const notices = {
  info: { edge: 'border-l-gold', tone: 'accent', icon: 'information-circle', color: colors.gold },
  warning: { edge: 'border-l-warning', tone: 'warning', icon: 'alert-circle', color: colors.warning },
  danger: { edge: 'border-l-danger', tone: 'danger', icon: 'warning', color: colors.danger },
} as const;

/** An inline message with a coloured edge (already owned, same side twice, possible copy...). */
export function Notice({
  tone = 'info',
  title,
  children,
}: {
  tone?: keyof typeof notices;
  title?: string;
  children: ReactNode;
}) {
  const t = notices[tone];
  return (
    <View
      className={cn('flex-row items-start gap-3 rounded-sm border-l-[5px] bg-surface p-4', t.edge)}
      accessibilityRole="alert"
    >
      <Ionicons name={t.icon} size={26} color={t.color} />
      <View className="flex-1 gap-0.5">
        {title && (
          <T variant="bodyStrong" tone={t.tone}>
            {title}
          </T>
        )}
        <T>{children}</T>
      </View>
    </View>
  );
}

/** Metal name with its colour swatch. */
export function Metal({ metal, name }: { metal: string; name: string }) {
  return (
    <View className="flex-row items-center gap-2">
      {metals[metal] && (
        <View
          className="h-[18px] w-[18px] rounded-full border border-black/15"
          style={{ backgroundColor: metals[metal] }}
        />
      )}
      <T variant="bodyStrong">{name}</T>
    </View>
  );
}

/** A toggle chip for filters and sorting: an optional metal swatch or icon, a label, an optional count. */
export function Chip({
  label,
  selected,
  onPress,
  swatch,
  icon,
  count,
  testID,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
  swatch?: string;
  icon?: IconName;
  count?: number;
  testID?: string;
}) {
  return (
    <Press
      testID={testID}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      accessibilityLabel={count != null ? `${label}, ${count}` : label}
      className={cn(
        'min-h-[56px] flex-row items-center gap-2 rounded-full border-2 px-4',
        selected ? 'border-gold bg-gold' : 'border-line bg-surface',
      )}
    >
      {swatch && (
        <View className="h-[16px] w-[16px] rounded-full border border-black/15" style={{ backgroundColor: swatch }} />
      )}
      <T variant="smallStrong" tone={selected ? 'onAccent' : 'ink'}>
        {label}
      </T>
      {count != null && (
        <T variant="small" tone={selected ? 'onAccent' : 'soft'}>
          {count}
        </T>
      )}
      {icon && <Ionicons name={icon} size={16} color={selected ? colors['on-gold'] : colors.gold} />}
    </Press>
  );
}

/** Bottom action bar pinned above the home indicator, within thumb reach. */
export function ActionBar({ children, bottomInset }: { children: ReactNode; bottomInset: number }) {
  return (
    <View
      className="gap-2 border-t border-line bg-ground px-gutter pt-3"
      style={{ paddingBottom: Math.max(bottomInset, 12) }}
    >
      {children}
    </View>
  );
}
