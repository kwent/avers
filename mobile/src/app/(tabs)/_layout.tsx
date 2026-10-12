import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';
import { colors, font } from '../../lib/theme';

export default function TabsLayout() {
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
          title: 'Scanner',
          headerTitle: 'Avers',
          tabBarIcon: ({ color }) => <Ionicons name="camera" size={30} color={color} />,
        }}
      />
      <Tabs.Screen
        name="collection"
        options={{
          title: 'Ma collection',
          tabBarIcon: ({ color }) => <Ionicons name="albums" size={30} color={color} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Réglages',
          tabBarIcon: ({ color }) => <Ionicons name="settings" size={30} color={color} />,
        }}
      />
    </Tabs>
  );
}
