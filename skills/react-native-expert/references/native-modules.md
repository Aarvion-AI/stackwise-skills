# Native Modules & New Architecture (Expo Modules API, Fabric, TurboModules)

## Decision ladder - exhaust each rung before descending

1. **Existing Expo/community package** - check `npx expo install <pkg>` compatibility first; most needs (camera, filesystem, secure store, haptics) are covered.
2. **Config plugin** - native *configuration* (Info.plist keys, gradle settings, entitlements) without writing native code.
3. **Local Expo Module** - your own Swift/Kotlin, still inside the managed/prebuild workflow.
4. **Bare workflow** - only when the app must own `ios/`/`android/` permanently (brownfield integration, custom build system). This is rare and mostly irreversible.

Under prebuild/CNG (Continuous Native Generation), `ios/` and `android/` are build artifacts: regenerate with `npx expo prebuild --clean`, never hand-edit them. If you must hand-edit, you have left CNG and own upgrades manually.

## New Architecture in practice (RN 0.76+, default on)

- **Fabric** replaces the old UIManager: synchronous layout/measure, C++ shadow tree, view flattening. `measure`/`onLayout` values arrive faster; direct `findNodeHandle`-based tricks and `setNativeProps`-heavy libraries are red flags.
- **TurboModules** replace bridge `NativeModules`: lazy-loaded, JSI-backed, optionally synchronous methods, codegen-typed specs.
- **Bridgeless mode**: there is no serialized JSON bridge; `BatchedBridge`/`MessageQueue` interception no longer works.
- **Interop layer** lets many old-arch libraries run, with warnings. A library crashing only on 0.76+ usually means it needs its New Architecture release - check its changelog/`codegenConfig` before patching around it.
- Opt-out (`newArchEnabled=false` in `gradle.properties` / `RCT_NEW_ARCH_ENABLED=0`) is a temporary escape hatch, disappearing in newer RN releases. Fix the dependency instead.

When writing new native code, prefer the **Expo Modules API** over hand-rolled TurboModules: it targets the New Architecture natively, uses Swift/Kotlin (not Obj-C++/Java), and skips codegen boilerplate.

## Creating a local Expo Module

```bash
npx create-expo-module@latest --local settings-badge
# creates modules/settings-badge/{expo-module.config.json, ios/, android/, src/, index.ts}
```

TypeScript API surface:

```ts
// modules/settings-badge/index.ts
import SettingsBadgeModule from './src/SettingsBadgeModule';

export function setBadgeCount(count: number): Promise<boolean> {
  return SettingsBadgeModule.setBadgeCount(count);
}
export function getTheme(): string {           // synchronous - JSI makes this cheap
  return SettingsBadgeModule.getTheme();
}
```

Swift implementation:

```swift
// modules/settings-badge/ios/SettingsBadgeModule.swift
import ExpoModulesCore

public class SettingsBadgeModule: Module {
  public func definition() -> ModuleDefinition {
    Name("SettingsBadge")

    Function("getTheme") { () -> String in        // sync function
      UITraitCollection.current.userInterfaceStyle == .dark ? "dark" : "light"
    }

    AsyncFunction("setBadgeCount") { (count: Int) -> Bool in
      await UNUserNotificationCenter.current().setBadgeCount(count)
      return true
    }

    Events("onThemeChange")                        // emit with sendEvent("onThemeChange", [...])
  }
}
```

Kotlin implementation:

```kotlin
// modules/settings-badge/android/src/main/java/expo/modules/settingsbadge/SettingsBadgeModule.kt
package expo.modules.settingsbadge

import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class SettingsBadgeModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("SettingsBadge")

    Function("getTheme") {
      val ui = appContext.reactContext?.resources?.configuration?.uiMode
      if ((ui?.and(android.content.res.Configuration.UI_MODE_NIGHT_MASK))
          == android.content.res.Configuration.UI_MODE_NIGHT_YES) "dark" else "light"
    }

    AsyncFunction("setBadgeCount") { count: Int ->
      true // e.g. via ShortcutBadger or notification APIs
    }
  }
}
```

Key facts:
- `Name("SettingsBadge")` must match on both platforms and is the JS module name.
- `Function` = synchronous (keep it fast - it blocks JS), `AsyncFunction` = promise-backed, runs off the JS thread.
- Argument/return types convert automatically (primitives, arrays, maps, `Record` classes, enums). Type mismatches throw typed errors instead of silent bridge coercion.
- Native views: `View(MyView.self) { Prop("url") { ... } }` gives you a Fabric-compatible native component without writing a Fabric C++ shim.
- After adding/changing native code: `npx expo prebuild --clean && npx expo run:ios` (or `run:android`). A plain `npx expo start` with Expo Go **cannot** load your module - you need a dev build (`expo-dev-client`).

## Config plugins

For native config that libraries don't already provide:

```ts
// plugins/withAndroidLargeHeap.ts
import { ConfigPlugin, withAndroidManifest } from 'expo/config-plugins';

const withAndroidLargeHeap: ConfigPlugin = (config) =>
  withAndroidManifest(config, (c) => {
    c.modResults.manifest.application![0].$['android:largeHeap'] = 'true';
    return c;
  });

export default withAndroidLargeHeap;
```

```jsonc
// app.json
{ "expo": { "plugins": ["./plugins/withAndroidLargeHeap"] } }
```

- Plugins run at prebuild time; verify with `npx expo prebuild --clean` then inspect the generated manifest/plist once, and run `npx expo-doctor` to catch plugin/SDK mismatches.
- Common mods: `withInfoPlist`, `withEntitlementsPlist`, `withAndroidManifest`, `withGradleProperties`, `withXcodeProject` (last resort).
- Never commit a hand-edit to generated `ios/`/`android/` alongside plugins - the next prebuild silently reverts it.

## Consuming third-party native modules

- Always `npx expo install <pkg>` (not `npm install`) so the SDK-compatible version is chosen; then `npx expo-doctor` to verify.
- If the package needs native config, it usually ships a config plugin - add it to `app.json` `plugins` with its options; do not follow README instructions that say "edit AppDelegate".
- New Architecture support: look for `codegenConfig` in its package.json or an explicit statement. Interop-layer warnings in Metro logs identify the offenders.
- After any native dependency change: rebuild the dev client. JS-only changes hot-reload; native ones never do.
