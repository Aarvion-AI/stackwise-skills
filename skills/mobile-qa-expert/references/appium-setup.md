# Appium 2.x Setup and Emulator-First Development

Appium 2.x split drivers out of core: `appium` is a thin server, drivers install
separately, and every non-W3C capability requires the `appium:` prefix. Most
stale examples online are Appium 1.x and will fail against a 2.x server.

## Install server + drivers

```bash
npm install -g appium@2   # server only, no drivers bundled
appium driver install uiautomator2   # Android
appium driver install xcuitest       # iOS (macOS host only)
appium driver list --installed       # verify
```

Driver versions are coupled to the Appium major. If `appium driver install`
warns about peer compatibility, pin an explicit version:

```bash
appium driver install uiautomator2@3.x
```

If a machine has an older Appium preinstalled on PATH (common on CI images and
AWS Device Farm hosts), the global npm install must shadow it - confirm with:

```bash
which appium && appium --version   # must print 2.x, not 1.x
```

An Appium 1.x binary has no `driver` subcommand at all; `appium driver install`
erroring with "unknown command" means you are still hitting the old wrapper.

## Start the server

```bash
appium --base-path / --port 4723 --log-timestamp --log appium.log
```

- `--base-path /` matters: Appium 1.x defaulted to `/wd/hub`, 2.x defaults to
  `/`. The client's path must match the server's or every session request 404s.
- Keep `appium.log` - it is the first artifact to read when a session dies.

## Capabilities (W3C, 2.x style)

Only `platformName`, `browserName`, and a few W3C keys are bare; everything
else needs `appium:`.

```python
from appium import webdriver
from appium.options.android import UiAutomator2Options

opts = UiAutomator2Options().load_capabilities({
    "platformName": "Android",
    "appium:automationName": "UiAutomator2",
    "appium:app": os.environ["APP_PATH"],          # .apk path; omit to attach
    "appium:appPackage": "com.example.app",        # with appActivity, skips reinstall
    "appium:appActivity": ".MainActivity",
    "appium:noReset": True,                        # keep app data (login state)
    "appium:autoGrantPermissions": True,
    "appium:newCommandTimeout": 300,               # long OCR/analysis gaps
    "appium:adbExecTimeout": 60000,
})
driver = webdriver.Remote("http://127.0.0.1:4723", options=opts)  # path = base-path
```

iOS equivalent:

```python
from appium.options.ios import XCUITestOptions
opts = XCUITestOptions().load_capabilities({
    "platformName": "iOS",
    "appium:automationName": "XCUITest",
    "appium:udid": os.environ["UDID"],
    "appium:bundleId": "com.example.app",
    "appium:noReset": True,
})
```

Real iOS devices additionally need code signing for WebDriverAgent
(`appium:xcodeOrgId`, `appium:xcodeSigningId`) when running outside a device
cloud; clouds handle WDA signing for you.

## Emulator-first loop

Develop on a local emulator: sessions start in seconds, `adb` gives you full
introspection, and iteration is free. Promote to real devices only once the
flow is green locally (see `device-farm-cloud.md` for what changes there).

```bash
sdkmanager "system-images;android-35;google_apis;arm64-v8a"
avdmanager create avd -n qa35 -k "system-images;android-35;google_apis;arm64-v8a"
emulator -avd qa35 -no-snapshot -no-audio &
adb wait-for-device
```

Caveat: apps with Play Integrity / attestation or cert pinning may refuse to
run on emulators entirely (blank screen, forced logout, or hard exit). If the
prod build won't open locally, do NOT root or patch it - develop against a
debug/UAT build locally and treat real, non-rooted cloud devices as the only
runtime for the prod build.

## Locator discipline

Order of preference - cheaper and more durable first:

1. `AppiumBy.ACCESSIBILITY_ID` - maps to `content-desc` (Android) /
   `accessibilityIdentifier` (iOS); React Native `testID` surfaces here on iOS
   and as `resource-id`/`content-desc` on Android depending on RN version.
2. `AppiumBy.ID` (Android `resource-id`).
3. `-android uiautomator` / `-ios predicate string` scoped text matches.
4. XPath - last resort, only short relative forms, never absolute trees.
5. Coordinates - see `opaque-ui-strategies.md`; only when 1-4 are impossible.

Push the app team to add `testID` / accessibility labels for anything a test
must touch. Ten minutes of app-side labeling saves hours of bounds-parsing.

## Waits

Never `time.sleep()` as a strategy. Use explicit waits keyed on state:

```python
from selenium.webdriver.support.ui import WebDriverWait

WebDriverWait(driver, 20).until(
    lambda d: "Order placed" in d.page_source
)
```

Real devices are 2-5x slower than emulators; budget wait ceilings for the
device pool, not your laptop.

## Evidence capture

After every asserted state, save both a screenshot and the live hierarchy:

```python
def capture(driver, outdir, name):
    driver.save_screenshot(f"{outdir}/{name}.png")
    with open(f"{outdir}/{name}.xml", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
```

The XML answers "why didn't the locator match" without re-running; the PNG is
what QA reviews. Together they are the audit trail for every assertion.

## Server-side sanity checklist

- `appium --version` is 2.x and `appium driver list --installed` shows your driver.
- Client URL path equals server `--base-path`.
- One manual session opens and `driver.page_source` returns the app's tree
  (not a launcher/home screen - wrong `appPackage` if so).
- `adb devices` shows exactly the device you think you're driving.
