/** Ask before a destructive action (react-native-web has no multi-button Alert: the browser's dialog). */
export const confirm = async (title: string, message: string, _confirmLabel: string, _cancelLabel: string) =>
  window.confirm(`${title}\n${message}`);
