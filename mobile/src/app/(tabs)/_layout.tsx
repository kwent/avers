import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';
import { useI18n } from '../../i18n';
import { colors, font } from '../../lib/theme';

export default function TabsLayout() {
  const { m } = useI18n();
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.brassDark,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: { fontSize: 14, fontWeight: '600' },
        tabBarStyle: { height: 90, paddingTop: 8, backgroundColor: colors.card },
        headerStyle: { backgroundColor: colors.bg },
        headerTitleStyle: { fontSize: font.large, color: colors.text },
        sceneStyle: { backgroundColor: colors.bg },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: m.tabs.scanner,
          headerTitle: 'Avers',
          tabBarButtonTestID: 'tab-scanner',
          tabBarIcon: ({ color }) => <Ionicons name="camera" size={30} color={color} />,
        }}
      />
      <Tabs.Screen
        name="collection"
        options={{
          title: m.tabs.collection,
          tabBarButtonTestID: 'tab-collection',
          tabBarIcon: ({ color }) => <Ionicons name="albums" size={30} color={color} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: m.tabs.settings,
          tabBarButtonTestID: 'tab-settings',
          tabBarIcon: ({ color }) => <Ionicons name="settings" size={30} color={color} />,
        }}
      />
    </Tabs>
  );
}
