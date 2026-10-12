import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';
import { ComponentProps } from 'react';
import { ColorValue, View } from 'react-native';
import { tick } from '../../components/ui';
import { useI18n } from '../../i18n';
import { colors, fonts, headerTitleStyle } from '../../theme';

type IconName = ComponentProps<typeof Ionicons>['name'];

// The camera sits in the middle of the tab bar but stays the first screen.
export const unstable_settings = { initialRouteName: 'index' };

const icon =
  (name: string) =>
  ({ color, focused }: { color: ColorValue; focused: boolean }) => (
    <Ionicons name={(focused ? name : `${name}-outline`) as IconName} size={28} color={color as string} />
  );

/** The main action: a round gold camera button raised above the tab bar. */
const cameraIcon = () => (
  <View
    className="mt-3 h-[64px] w-[64px] items-center justify-center rounded-full border-4 border-ground bg-gold"
    style={{ boxShadow: '0 4px 18px rgba(238, 193, 78, 0.35)' }}
  >
    <Ionicons name="camera" size={30} color={colors['on-gold']} />
  </View>
);

export default function TabsLayout() {
  const { m } = useI18n();
  return (
    <Tabs
      initialRouteName="index"
      screenListeners={{ tabPress: tick }}
      screenOptions={{
        tabBarActiveTintColor: colors.gold,
        tabBarInactiveTintColor: colors['cream-soft'],
        tabBarLabelStyle: { fontFamily: fonts.strong, fontSize: 13 },
        tabBarStyle: { height: 92, paddingTop: 8, backgroundColor: colors.surface, borderTopColor: colors.line },
        headerStyle: { backgroundColor: colors.ground },
        headerShadowVisible: false,
        headerTitleStyle,
        sceneStyle: { backgroundColor: colors.ground },
      }}
    >
      <Tabs.Screen
        name="collection"
        options={{
          title: m.tabs.collection,
          headerShown: false,
          tabBarButtonTestID: 'tab-collection',
          tabBarIcon: icon('albums'),
        }}
      />
      <Tabs.Screen
        name="index"
        options={{
          title: m.tabs.scanner,
          headerShown: false,
          tabBarButtonTestID: 'tab-scanner',
          tabBarAccessibilityLabel: m.home.takePhoto,
          tabBarLabel: () => null, // the raised button speaks for itself
          tabBarIcon: cameraIcon,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{ title: m.tabs.settings, tabBarButtonTestID: 'tab-settings', tabBarIcon: icon('settings') }}
      />
    </Tabs>
  );
}
