import * as Haptics from 'expo-haptics';

const feel = (haptic: () => Promise<void>) => {
  haptic().catch(() => {});
};

/** A light tap: a selection. */
export const tick = () => feel(Haptics.selectionAsync);
/** A firm tap: the shutter. */
export const thud = () => feel(() => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium));
/** Done: the estimate is in. */
export const success = () => feel(() => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success));
