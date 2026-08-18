# Platform Integration: Channels, Pigeon, FFI

Three ways to leave Dart, in order of preference:

1. **Pigeon** - type-safe generated channels for your own Android/iOS code. Default choice.
2. **Raw MethodChannel/EventChannel** - quick one-offs, dynamic cases.
3. **dart:ffi (+ ffigen)** - C/C++/Rust libraries, synchronous native calls, no platform UI thread involved.

Check pub.dev first - most needs (battery, camera, secure storage) already have a
maintained federated plugin. Write native code only when no plugin fits.

## Raw MethodChannel

Dart side:

```dart
class BatteryApi {
  static const _channel = MethodChannel('com.example.app/battery');

  Future<int> level() async {
    try {
      // Generic argument matters: platform ints arrive as int, maps as
      // Map<Object?, Object?> - cast explicitly, never trust raw types.
      final level = await _channel.invokeMethod<int>('getBatteryLevel');
      return level ?? -1;
    } on PlatformException catch (e) {
      throw BatteryReadException(e.code, e.message);
    } on MissingPluginException {
      // Channel not registered on this platform (or running in a plain test).
      return -1;
    }
  }
}
```

Android (Kotlin, `MainActivity.kt`):

```kotlin
class MainActivity : FlutterActivity() {
  override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
    super.configureFlutterEngine(flutterEngine)
    MethodChannel(flutterEngine.dartExecutor.binaryMessenger,
        "com.example.app/battery").setMethodCallHandler { call, result ->
      when (call.method) {
        "getBatteryLevel" -> {
          val bm = getSystemService(BATTERY_SERVICE) as BatteryManager
          result.success(bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY))
        }
        else -> result.notImplemented()
      }
    }
  }
}
```

iOS (Swift, `AppDelegate.swift`):

```swift
let controller = window?.rootViewController as! FlutterViewController
let channel = FlutterMethodChannel(name: "com.example.app/battery",
                                   binaryMessenger: controller.binaryMessenger)
channel.setMethodCallHandler { call, result in
  guard call.method == "getBatteryLevel" else {
    result(FlutterMethodNotImplemented); return
  }
  UIDevice.current.isBatteryMonitoringEnabled = true
  result(Int(UIDevice.current.batteryLevel * 100))
}
```

Rules:

- Channel names must match exactly on both sides; prefix with your app/package id.
- Handlers run on the **platform main thread** - dispatch heavy work to a
  background thread natively, then call `result.success` back on main.
- Every code path must call exactly one of `result.success` / `result.error` /
  `result.notImplemented`, or the Dart future hangs forever.
- Supported payload types only (null, bool, int, double, String, Uint8List &
  friends, List, Map). Serialize models as JSON strings or maps - you cannot
  pass Dart objects.

## EventChannel (native -> Dart streams)

```dart
static const _events = EventChannel('com.example.app/battery_events');
Stream<int> get levelStream =>
    _events.receiveBroadcastStream().map((e) => e as int);
```

Native side implements `StreamHandler` (`onListen` gets an `EventSink`; emit with
`events.success(value)`, finish with `events.endOfStream()`). Cancel your native
listeners in `onCancel` or you leak sensors/receivers.

## Pigeon (preferred for owned native code)

```yaml
dev_dependencies:
  pigeon: ^22.0.0
```

Define the API once in Dart (`pigeons/battery.dart`):

```dart
import 'package:pigeon/pigeon.dart';

@ConfigurePigeon(PigeonOptions(
  dartOut: 'lib/src/battery_api.g.dart',
  kotlinOut: 'android/app/src/main/kotlin/com/example/app/BatteryApi.g.kt',
  swiftOut: 'ios/Runner/BatteryApi.g.swift',
))
class BatteryInfo {
  BatteryInfo({required this.level, required this.isCharging});
  int level;
  bool isCharging;
}

@HostApi() // Dart -> native
abstract class BatteryHostApi {
  BatteryInfo getInfo();
  @async
  bool requestPowerSaver();
}

@FlutterApi() // native -> Dart callbacks
abstract class BatteryFlutterApi {
  void onLevelChanged(int level);
}
```

Generate: `dart run pigeon --input pigeons/battery.dart`. Implement the generated
`BatteryHostApi` interface in Kotlin/Swift and register it
(`BatteryHostApi.setUp(binaryMessenger, impl)`); call it from Dart via the
generated client class. You get typed models, null-safety, and error propagation
with zero hand-written channel code - this removes the whole class of
"wrong argument map key" bugs.

## dart:ffi + ffigen (C interop)

For C ABI libraries (also the path for Rust via `#[no_mangle] extern "C"`).

```yaml
dependencies:
  ffi: ^2.1.0
dev_dependencies:
  ffigen: ^13.0.0
```

Hand-written binding (small cases):

```dart
import 'dart:ffi';
import 'dart:io';
import 'package:ffi/ffi.dart';

final DynamicLibrary _lib = Platform.isAndroid
    ? DynamicLibrary.open('libnative.so')
    : DynamicLibrary.process(); // iOS: statically linked

typedef _SumC = Int32 Function(Int32, Int32);
typedef _SumDart = int Function(int, int);
final sum = _lib.lookupFunction<_SumC, _SumDart>('sum');

String greet(String name) {
  final cName = name.toNativeUtf8();          // malloc - you own it
  try {
    final res = _lib.lookupFunction<Pointer<Utf8> Function(Pointer<Utf8>),
        Pointer<Utf8> Function(Pointer<Utf8>)>('greet')(cName);
    return res.toDartString();
  } finally {
    calloc.free(cName);                        // ALWAYS free what you allocate
  }
}
```

For real headers, don't hand-write - configure ffigen in `pubspec.yaml`
(`ffigen: headers: entry-points: [...]`) and run `dart run ffigen`.

FFI rules:

- FFI calls are synchronous **on the calling isolate** - a slow C call freezes
  the UI. Run long calls in `Isolate.run(() => ...)`, or use native async
  callbacks via `NativeCallable.listener`.
- Memory: Dart GC does not manage native allocations. Pair every
  `malloc`/`toNativeUtf8` with `free` (use `try/finally` or an `Arena`), or
  attach a `NativeFinalizer` for long-lived native objects.
- Bundling: Android - put `.so` files under `android/app/src/main/jniLibs/<abi>/`
  or build with the plugin's CMake; iOS - link via the podspec/xcframework.
- Prefer `dart:ffi` over channels when you need sync calls or the code is
  already C/Rust; prefer channels/Pigeon when you need platform *APIs* (they
  require the platform object model, permissions, main thread).

## Release basics: flavors and signing

Flavors let one codebase ship dev/staging/prod apps side by side.

- Android - `android/app/build.gradle(.kts)`:

```kotlin
android {
  flavorDimensions += "env"
  productFlavors {
    create("dev")  { dimension = "env"; applicationIdSuffix = ".dev"; resValue("string", "app_name", "MyApp Dev") }
    create("prod") { dimension = "env"; resValue("string", "app_name", "MyApp") }
  }
  signingConfigs {
    create("release") {
      val props = Properties().apply { load(rootProject.file("key.properties").inputStream()) }
      keyAlias = props["keyAlias"] as String
      keyPassword = props["keyPassword"] as String
      storeFile = file(props["storeFile"] as String)
      storePassword = props["storePassword"] as String
    }
  }
  buildTypes { getByName("release") { signingConfig = signingConfigs.getByName("release") } }
}
```

Keystore: `keytool -genkey -v -keystore upload-keystore.jks -keyalg RSA -keysize
2048 -validity 10000 -alias upload`. Keep `key.properties` and the `.jks` out of
git. With Play App Signing, this key is only the *upload* key.

- iOS - flavors map to Xcode schemes/configurations named after the flavor
  (Runner scheme per flavor, `Debug-dev`, `Release-prod`, ...); signing is
  per-configuration via provisioning profiles in Xcode.
- Entry points per flavor + compile-time config:

```bash
flutter run --flavor dev -t lib/main_dev.dart --dart-define=API_URL=https://dev.api.example.com
flutter build appbundle --flavor prod -t lib/main_prod.dart   # Play Store wants .aab
flutter build ipa --flavor prod -t lib/main_prod.dart
```

Read defines with `const String.fromEnvironment('API_URL')` - `const` is
required or the value is empty in release builds.

## Testing hooks

- Mock a channel in tests:
  `TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
  .setMockMethodCallHandler(channel, (call) async => 42);`
- Pigeon-generated APIs are plain abstract classes - inject and fake them like
  any dependency; keep channel code behind a repository interface so widget
  tests never touch messengers at all.
