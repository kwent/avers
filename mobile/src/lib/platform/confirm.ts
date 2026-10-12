import { Alert } from 'react-native';

/** Ask before a destructive action. Resolves true when confirmed. */
export const confirm = (title: string, message: string, confirmLabel: string, cancelLabel: string) =>
  new Promise<boolean>((resolve) =>
    Alert.alert(title, message, [
      { text: cancelLabel, style: 'cancel', onPress: () => resolve(false) },
      { text: confirmLabel, style: 'destructive', onPress: () => resolve(true) },
    ]),
  );
