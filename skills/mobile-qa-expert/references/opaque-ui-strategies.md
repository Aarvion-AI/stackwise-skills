# Opaque UI Trees: React Native, Flutter, and Coordinate Strategies

React Native and Flutter apps frequently expose an accessibility tree that
looks nothing like the visual UI: deeply nested `ViewGroup`s, few or no
resource-ids, and - the critical trap - visible, tappable things whose nodes
report `clickable="false"` because the real touch handler lives on an
unlabeled ancestor.

## The silent no-op tap

`element.click()` on a `clickable=false` node **does not throw**. Appium
dispatches, nothing handles it, your test "passes" the tap and fails three
steps later on the wrong screen. Symptoms:

- Tap runs, no exception, screen unchanged.
- Every node near the target reports `clickable="false"`.
- The `text`/`content-desc` you can see lives on a leaf; the touchable is a
  bare ancestor `ViewGroup` with no text and no id.

Rule: **never trust a tap that didn't throw - assert the post-tap state.**

```python
before = driver.page_source
element.click()
WebDriverWait(driver, 10).until(lambda d: d.page_source != before)  # minimum bar
```

## The durable primitive: live bounds + clickGesture

Read the live page source, find the target text's bounds, tap the center via
`mobile: clickGesture` (UiAutomator2). This works regardless of which ancestor
owns the touch handler, and it self-adapts to any device resolution because
bounds come from the running device.

```python
import re
from selenium.webdriver.support.ui import WebDriverWait

BOUNDS = r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'

def find_bounds(driver, text, attr="text"):
    """Center of the first node whose text/content-desc matches. LIVE source only."""
    src = driver.page_source                     # never cache: bounds shift on scroll,
    pat = rf'{attr}="{re.escape(text)}"[^>]*{BOUNDS}'  # keyboard, and orientation
    m = re.search(pat, src)
    if not m and attr == "text":
        return find_bounds(driver, text, attr="content-desc")
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2

def tap_text(driver, text, timeout=15):
    center = WebDriverWait(driver, timeout).until(lambda d: find_bounds(d, text))
    driver.execute_script("mobile: clickGesture", {"x": center[0], "y": center[1]})
```

iOS/XCUITest equivalent: nodes carry `x`,`y`,`width`,`height` attributes;
gesture is `mobile: tap` with the computed center.

Why not `find_element(By.XPATH, '//*[@text="..."]').click()`? It clicks the
non-clickable leaf - the exact no-op above. The gesture at coordinates goes
through the OS input pipeline and hits whatever is actually touchable there.

### Off-screen targets

Bounds only exist for rendered nodes. Scroll first, then locate:

```python
driver.execute_script("mobile: scrollGesture", {
    "left": 100, "top": 400, "width": 600, "height": 1200,
    "direction": "down", "percent": 0.8,
})
```

Loop scroll-then-search until `find_bounds` hits or a max-scroll budget runs
out; treat exhaustion as a real failure with an evidence capture.

## Pure coordinate scripts: the pinning rule

Sometimes even text is absent (custom-rendered canvases, image buttons with no
labels). Hardcoded coordinates are then the last resort - and they are **only
valid on the exact device model and resolution they were authored on**. If a
suite contains any raw coordinates:

- Pin the cloud device pool to that one model, and record the model +
  resolution in the suite (assert it at session start and fail fast).
- Prefer proportional coordinates (`x = int(0.5 * width)`) via
  `driver.get_window_size()` - survives resolution changes, not layout changes.
- Screenshot immediately after every raw-coordinate tap; blind taps with no
  evidence are undebuggable.

## Flutter specifics

Flutter renders to its own canvas; the a11y tree exists only when semantics
are enabled and is often a flat list of `android.view.View` nodes whose
`content-desc` holds the visible text. `find_bounds(..., attr="content-desc")`
is usually the working path. If the tree is empty, ask the app team to build
with semantics enabled (debug/profile builds usually have it; some release
configs strip it). The Flutter-specific Appium driver requires an app built
with the enabler package - for a prod .apk you were handed, bounds+gesture on
the semantics tree is the realistic option.

## React Native specifics

`testID` mapping differs by platform and RN version: on iOS it surfaces as the
accessibility identifier (use `AppiumBy.ACCESSIBILITY_ID`); on Android it maps
to `resource-id` on newer RN, or only to `content-desc` when
`accessible={true}` combines child labels. Check what actually appears in the
page source before writing locators. Composite accessibility
(`accessible={true}` on a parent) collapses children into one node - the label
you target may be a concatenation of several visible strings.

## WebViews

Hybrid screens expose a `WEBVIEW_<pkg>` context. Switching contexts
(`driver.switch_to.context`) gives real DOM locators - but requires a
debuggable WebView, which prod builds usually disable. When you cannot switch
context, the native-side tree still shows text nodes with bounds:
bounds+gesture works there too.

## Verification discipline for opaque UIs

Because locators are weak, state assertions carry the suite:

1. After every gesture, wait for a concrete state marker (target text
   appears/disappears) - never proceed on "no exception".
2. Capture screenshot + page-source XML at every asserted state (the XML shows
   what the tree looked like when the assertion ran).
3. When a `find_bounds` returns None unexpectedly, dump the full source to the
   evidence dir before failing - the diff against the last-good XML usually
   names the regression (renamed label, new modal, changed layout).
