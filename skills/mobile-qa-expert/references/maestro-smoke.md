# Maestro Smoke Flows

Maestro is the fast layer of the pyramid: declarative YAML flows that run in
seconds, with built-in waiting and tolerance for minor UI shifts. Use it for
the 3-5 critical paths on every PR; keep Appium for the deep, evidence-heavy
release gate on real-device clouds.

## When Maestro, when Appium

| Need | Tool |
|------|------|
| PR-level smoke: app launches, core screens render, happy path works | Maestro |
| Conditional logic, IMAP/OTP integration, computed coordinates | Appium |
| Evidence bundles (screenshot + hierarchy per assertion) for QA review | Appium |
| Real-device cloud release gate with device-pool control | Appium (or Maestro via supported cloud runners) |
| Quickly reproducing a reported flow by hand-writing 10 lines | Maestro |

Maestro's text matching is resilient on RN/Flutter trees (it matches visible
text/accessibility and taps the right touchable), which makes it ideal for
smoke coverage of opaque UIs - but its scripting model (JS snippets, env vars)
is too thin for OTP-over-IMAP or bounds math. Don't force it past smoke scope.

## Install and run

```bash
curl -Ls https://get.maestro.mobile.dev | bash
maestro --version
maestro test flows/smoke/           # runs every flow in the dir on the connected device
maestro test -e APP_ID=com.example.app flows/smoke/launch.yaml
```

Runs against whatever `adb devices` / connected simulator shows. For real
devices in the cloud, use a cloud runner that supports Maestro flows, or keep
Maestro local/emulator-only and let Appium own the cloud gate.

## Flow anatomy

`flows/smoke/launch.yaml`:

```yaml
appId: ${APP_ID}
name: cold-launch-home
tags: [smoke]
---
- clearState          # ONLY in flows allowed to log out - see below
- launchApp
- assertVisible:
    text: "Home"
    timeout: 20000    # real devices need headroom
- takeScreenshot: artifacts/launch-home
```

`flows/smoke/browse.yaml` - session-preserving flow:

```yaml
appId: ${APP_ID}
name: browse-catalog
tags: [smoke]
---
- launchApp:
    stopApp: true      # terminate + relaunch: session SURVIVES (no clearState)
- tapOn: "Search"
- inputText: "shoes"
- pressKey: enter
- assertVisible:
    text: ".*results.*"   # regex match
    timeout: 15000
- tapOn:
    index: 0
    below: ".*results.*"
- assertVisible: "Add to .*"
- takeScreenshot: artifacts/browse-pdp
```

Key commands that carry most smoke flows:

```yaml
- tapOn: "Visible text"            # matches text OR accessibility label
- tapOn:
    id: "com.example:id/submit"    # resource-id when one exists
- tapOn:
    point: "50%, 92%"              # proportional coords - last resort, still
                                   # resolution-tolerant unlike raw pixels
- scrollUntilVisible:
    element: "Terms"
    direction: DOWN
- inputText: "hello"
- assertVisible: { text: "Done", timeout: 10000 }
- assertNotVisible: "Error"
- runFlow: ../shared/dismiss-popups.yaml   # reuse fragments
- repeat:
    while: { notVisible: "Home" }
    commands: [ - back ]
```

## Session rules carry over from Appium

The same persistence asymmetry applies (see `auth-flows-unattended.md`):

- `launchApp` with `stopApp: true` terminates and relaunches - logged-in
  session survives. This is the default reset between smoke flows.
- `clearState` wipes app data - session destroyed, OTP wall returns. Use it
  only in the one flow that tests cold first-run, and never before flows that
  assume login.

For smoke suites that need an authenticated state, run the Appium login
module once to establish the session on the device, then run Maestro flows
with `stopApp: true` resets on top of it. Do not attempt OTP retrieval inside
Maestro.

## Conditionals and popups

Real apps interrupt smoke flows with rating prompts, permission dialogs, and
promos. Centralize dismissal:

`flows/shared/dismiss-popups.yaml`:

```yaml
appId: ${APP_ID}
---
- runFlow:
    when: { visible: "No thanks" }
    commands: [ - tapOn: "No thanks" ]
- runFlow:
    when: { visible: "Not now" }
    commands: [ - tapOn: "Not now" ]
```

Call it after `launchApp` in every flow. `when:` blocks are Maestro's whole
conditional vocabulary - if a flow needs more logic than this, it has outgrown
smoke scope and belongs in Appium.

## CI wiring

```bash
maestro test --format junit --output artifacts/maestro-report.xml \
  -e APP_ID=com.example.app flows/smoke/
```

- Exit code is nonzero on any failed flow; JUnit XML plugs into CI reporters.
- On failure Maestro saves a screenshot and hierarchy automatically under
  `~/.maestro/tests/` - upload that directory as a CI artifact.
- Budget: a smoke suite should stay under ~5 minutes on an emulator. If it
  grows past that, flows are doing release-gate work that belongs to Appium.

## Flake handling in smoke flows

- Prefer `assertVisible` with generous `timeout` over `waitForAnimationToEnd`
  or fixed waits; Maestro polls internally.
- `scrollUntilVisible` instead of fixed swipe counts.
- Retry policy: retry a failed flow once at the runner level
  (`maestro test` per-flow in a shell loop or CI retry step); a flow that
  needs two retries to pass is quarantined and investigated, not shipped as a
  gate. Track quarantined flows in a visible list with an owner - silent
  retries are how smoke suites rot.
- Keep every flow independently runnable (own `launchApp`, no ordering
  assumptions) so retries and single-flow debugging stay trivial.
