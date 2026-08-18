---
name: mobile-qa-expert
description: Use when testing mobile apps on emulators or real devices - Appium 2.x (UiAutomator2/XCUITest), AWS Device Farm, BrowserStack App Automate, Maestro, .apk/.aab/.ipa files, wdio/appium configs, testspec.yml, or flows blocked by Play Integrity, cert pinning, or OTP logins. Builds device automation suites, debugs flaky real-device runs, automates authenticated flows unattended, and sets up cloud release gates. Invoke for writing Appium tests, Device Farm/BrowserStack runs, Maestro smoke flows, tapping elements that won't click, or OTP/login automation.
license: MIT
metadata:
  version: "0.1.0"
  category: qa
  frameworks: Appium 2.x (UiAutomator2, XCUITest), AWS Device Farm, BrowserStack App Automate, Maestro 1.x
  triggers: appium, uiautomator2, xcuitest, device farm, browserstack, app automate, maestro, real device, emulator, apk, ipa, mobile test, smoke test, otp, cert pinning, play integrity, flaky, testspec
  related: flutter-expert, react-native-expert, playwright-expert
---

# Mobile QA Expert

Turns Claude into a senior mobile automation engineer who ships suites that pass on real cloud devices, not just on the emulator that wrote them.

## When to Use This Skill

- Write or extend an Appium 2.x suite (UiAutomator2 or XCUITest) for an Android/iOS app
- Run an existing suite on AWS Device Farm or BrowserStack App Automate as a release gate
- Automate a login/OTP-gated flow so it runs unattended in CI
- Fix taps that silently do nothing on React Native / Flutter screens
- Add fast Maestro YAML smoke flows alongside a heavier Appium suite
- Diagnose tests that pass on emulator but fail on real devices (attestation, pinning, timing, resolution)
- Capture screenshot + view-hierarchy evidence bundles for QA review

## Core Workflow

1. **Analyze the app and constraints** - Identify the build type (debug vs prod), UI framework (native, React Native, Flutter - determines locator strategy), and blockers: Play Integrity / attestation and cert pinning mean prod builds only run on real, non-rooted devices, and the network layer stays pinned-blind (verify via screenshots/OCR, not proxying). Check for existing `testID`/accessibility labels; request them from the app team before resorting to coordinates.
2. **Set up local Appium 2.x** - Install `appium@2.x` plus the driver (`appium driver install uiautomator2` / `xcuitest`) at a version compatible with your Appium major. Start with `--base-path /` and match the client path. Write W3C capabilities (`appium:` prefixed). Verify: start the server, run `appium driver list --installed`, and open one session against the emulator; fix all reported issues and re-run until clean.
3. **Develop the suite emulator-first** - Build flows on a local emulator for speed. Prefer accessibility-id and testID locators; for opaque RN/Flutter trees use the page-source → bounds → `mobile: clickGesture` pattern (see `references/opaque-ui-strategies.md`). After every asserted state, save screenshot + page-source XML as the evidence bundle. Verify: run the suite locally; fix all reported issues and re-run until clean (zero failures, evidence artifacts present).
4. **Automate auth unattended** - Log in once per suite via email OTP over IMAP with a dedicated test account; secrets come from env/secret store, never hardcoded. Exploit session persistence: terminate/relaunch keeps the session, clearing app data does not. Verify: run the full suite twice back-to-back with no human input; fix all reported issues and re-run until clean.
5. **Promote to real-device cloud** - Package for Device Farm (custom environment testspec - remember to shadow the preinstalled Appium 1.x) or BrowserStack App Automate. Pin device models for any coordinate-dependent steps. Verify: run on the cloud device pool; triage every failure as app bug vs environment gap (attestation, resolution, timing), fix all reported issues and re-run until clean.
6. **Add Maestro smoke layer + flake hardening** - Encode the 3-5 critical paths as Maestro YAML flows for fast PR-level checks; keep Appium as the deep release gate. Add explicit waits (never bare sleeps), retries with evidence on retry, and quarantine rules. Verify: run smoke + full suite 3 consecutive times on the release device pool; fix all reported issues and re-run until clean, then wire both into CI.

## Reference Guide

Load detailed guidance only when the task needs it:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Appium 2.x install, drivers, capabilities, local emulator loop | `references/appium-setup.md` | Setting up or debugging an Appium server/driver/capabilities, emulator-first development |
| AWS Device Farm & BrowserStack real-device runs | `references/device-farm-cloud.md` | Packaging for a device cloud, writing a testspec.yml, cloud run fails that pass locally |
| Locating/tapping elements in RN, Flutter, or WebView trees | `references/opaque-ui-strategies.md` | `element.click()` no-ops, `clickable=false` everywhere, missing testIDs, coordinate taps |
| Unattended login, email OTP over IMAP, session reuse | `references/auth-flows-unattended.md` | Automating a login/OTP wall, secrets handling, suite structure around auth |
| Maestro YAML smoke flows | `references/maestro-smoke.md` | Adding quick smoke coverage, choosing Maestro vs Appium, writing/running flows |

## Key Patterns

**Tap by text bounds when the tree is opaque** (RN/Flutter - the touch handler lives on an unlabeled parent, so `element.click()` silently no-ops):

```python
import re
def tap_text(driver, text):
    src = driver.page_source  # read LIVE source every time; never cache
    m = re.search(rf'text="{re.escape(text)}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', src)
    x1, y1, x2, y2 = map(int, m.groups())
    driver.execute_script("mobile: clickGesture", {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2})
```

**Evidence bundle after every asserted state** - screenshot + hierarchy XML is what QA reviews:

```python
def capture(driver, outdir, name):
    driver.save_screenshot(f"{outdir}/{name}.png")
    with open(f"{outdir}/{name}.xml", "w") as f:
        f.write(driver.page_source)
```

**Login once, reuse the session** - terminating the app keeps auth state; clearing app data destroys it:

```python
driver.terminate_app(APP_ID)   # session survives
driver.activate_app(APP_ID)    # still logged in - safe reset between tests
# driver.reset() / clearing app data => logged out; never use mid-suite
```

**W3C capabilities, Appium 2.x style** - every non-standard key needs the `appium:` prefix:

```python
caps = {
    "platformName": "Android",
    "appium:automationName": "UiAutomator2",
    "appium:app": os.environ["APP_PATH"],
    "appium:noReset": True,        # preserve login between sessions
    "appium:newCommandTimeout": 300,
}
```

## Common Mistakes

- **Trusting an emulator-green suite for a prod build.** Play Integrity / attestation and cert pinning make prod builds refuse emulators and rooted devices. The release gate must run on real, non-rooted cloud devices - and since pinning blocks proxying, assert via screenshots/OCR, not intercepted traffic.
- **Using Device Farm's preinstalled `appium`.** The binary on PATH is an Appium 1.x CLI wrapper with no `driver` subcommands. In the testspec, `npm install -g appium@2.x` to shadow it, install a compatible `uiautomator2` driver, and start with `--base-path /` matching the client path.
- **Believing a tap happened because no error was thrown.** On RN/Flutter trees the target has `clickable=false` and `element.click()` no-ops silently. Verify the post-tap state changed; fall back to bounds-center `mobile: clickGesture` from live page source.
- **Unpinned coordinate scripts.** Raw coordinates only survive on the exact device model/resolution they were written on. Derive coordinates from live bounds, or pin the device pool to one model and say so in the suite.
- **Hardcoding OTP inboxes, passwords, or API keys.** All secrets flow from env vars / a secret store. Use a dedicated test/UAT account - personal accounts leak PII into screenshots that land in QA evidence bundles and cloud dashboards.
- **Resetting app data between tests "for isolation".** That logs you out and re-triggers the OTP wall every test. Structure suites to authenticate once, then terminate/relaunch (session persists) for a clean-enough state.
- **Assuming the phone-number field is the OTP path.** Apps often default login to a phone field; unattended automation must switch to the email option first, then read the OTP over IMAP from the test inbox.
