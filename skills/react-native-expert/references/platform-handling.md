# Platform-Specific Code (iOS / Android / Web)

Order of preference: (1) write once with cross-platform primitives, (2) branch values with `Platform.select`, (3) fork files with platform extensions, (4) gate whole features. Fork as little as possible - every fork is a divergence to test twice.

## Platform module

```tsx
import { Platform, StyleSheet } from 'react-native';

const styles = StyleSheet.create({
  header: {
    paddingTop: Platform.select({ ios: 0, android: 8, default: 0 }),
    ...Platform.select({
      ios: { shadowColor: '#000', shadowOpacity: 0.1, shadowRadius: 6, shadowOffset: { width: 0, height: 2 } },
      android: { elevation: 3 },
    }),
  },
});

if (Platform.OS === 'android' && Platform.Version >= 33) {
  // runtime POST_NOTIFICATIONS permission needed (API 33+); Platform.Version is a number on Android
}
// Platform.Version is a STRING on iOS ("17.4") - compare with parseFloat, not <.
```

`Platform.select` accepts `ios`, `android`, `web`, `native`, `default`. Use `default` so web doesn't fall through to `undefined`.

## Platform file extensions

Metro resolves the most specific file automatically:

```
components/
  MapView.tsx          # shared types + default (often the web fallback)
  MapView.ios.tsx      # Apple Maps implementation
  MapView.android.tsx  # Google Maps implementation
  analytics.native.ts  # native (ios+android), while analytics.ts serves web
```

- Import as `./MapView` - never import the platform file directly.
- Keep a single shared `types.ts` for the props so forks can't drift.
- `.native.ts` vs `.ts` is the standard split for web-incompatible libraries (e.g. modules touching `react-native` internals): web bundlers pick `.ts`, Metro-native picks `.native.ts`.

## Safe areas

Use `react-native-safe-area-context` (installed by default in Expo templates). Never hard-code notch/status-bar heights.

```tsx
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

// Whole screens NOT inside a native-header Stack:
<SafeAreaView style={{ flex: 1 }} edges={['top', 'bottom']}>...</SafeAreaView>

// Custom positioning (floating buttons, bottom bars):
const insets = useSafeAreaInsets();
<View style={{ position: 'absolute', bottom: insets.bottom + 16, right: 16 }} />
```

- Screens under a native Stack header or Tabs bar already have those edges handled - adding `SafeAreaView` there double-pads. Choose `edges` deliberately.
- Android edge-to-edge is the norm on SDK 53+ new projects (and mandatory on Android 16 targets): the app draws behind system bars, so `insets.top/bottom` are nonzero on Android too. Do not assume insets are an iOS thing.
- The provider (`SafeAreaProvider`) is included by Expo Router; do not add a second one.

## Keyboard handling

```tsx
import { KeyboardAvoidingView, Platform } from 'react-native';

<KeyboardAvoidingView
  behavior={Platform.OS === 'ios' ? 'padding' : undefined}
  keyboardVerticalOffset={headerHeight} // useHeaderHeight() from @react-navigation/elements
  style={{ flex: 1 }}
>
  {form}
</KeyboardAvoidingView>
```

- iOS needs `behavior="padding"`; Android usually handles it via `android:windowSoftInputMode="adjustResize"` (Expo default) and works best with `behavior={undefined}`.
- For scrollable forms and chat UIs, prefer `react-native-keyboard-controller` (`KeyboardAwareScrollView`, `KeyboardStickyView`) - it animates with the keyboard on the UI thread and behaves identically on both platforms.
- Dismiss on background tap: `<ScrollView keyboardShouldPersistTaps="handled">` - `"never"` makes taps on buttons require two touches while the keyboard is up.

## Permissions

Declare at config time, request at runtime, always through Expo APIs:

```jsonc
// app.json - config-time declarations
{
  "expo": {
    "ios": { "infoPlist": { "NSCameraUsageDescription": "Scan receipts to add expenses." } },
    "plugins": [
      ["expo-camera", { "cameraPermission": "Scan receipts to add expenses." }],
      ["expo-location", { "locationWhenInUsePermission": "Show nearby stores." }]
    ]
  }
}
```

```tsx
import { useCameraPermissions } from 'expo-camera';

const [status, requestPermission] = useCameraPermissions();
if (!status?.granted) {
  const res = await requestPermission();
  if (!res.granted && !res.canAskAgain) {
    // permanently denied - deep-link to settings via Linking.openSettings()
  }
}
```

- iOS kills the app at review (or runtime) if a permission is used without its `Info.plist` usage string; the plugin props above generate them.
- Android 13+ notification permission (`POST_NOTIFICATIONS`) must be requested at runtime; Android photo access uses scoped `READ_MEDIA_IMAGES` - `expo-image-picker`/`expo-media-library` plugins handle the manifest.
- Ask **in context** (when the user taps the camera button), never in a permissions wall at launch.

## Platform behavior differences that bite

- **Text**: Android adds font padding - `<Text style={{ includeFontPadding: false }}>` for precise vertical centering; iOS/Android default font weights render differently, load explicit weights via `expo-font`.
- **Shadows**: iOS uses `shadow*` props, Android uses `elevation`; RN 0.76+ adds cross-platform `boxShadow` style - prefer it for new code.
- **Pressables**: `android_ripple={{ color: '...' }}` for native ripple; iOS has no ripple - provide a pressed style via the `style={({ pressed }) => ...}` function form so both platforms give feedback.
- **Back handling**: Android hardware/gesture back pops the router stack automatically; intercept only for unsaved-changes guards (`usePreventRemove` from @react-navigation/native), and always test the Android back path - iOS-only testing misses it.
- **Date/number formatting**: Hermes ships `Intl` on both platforms now - use `Intl.NumberFormat`/`DateTimeFormat` instead of manual formatting, but verify output on both platforms (ICU versions differ).
- **Web**: only if the project targets it - guard native-only libraries behind `.native.ts` forks and check `Platform.OS === 'web'` before touching APIs like `Haptics`.
