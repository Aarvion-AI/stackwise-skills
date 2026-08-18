# Visual Regression: toHaveScreenshot & Aria Snapshots (Playwright 1.5x)

Visual checks catch what functional assertions can't (layout breaks, styling regressions, z-index bugs) but cost maintenance. Use them for stable, high-value surfaces - design-system components, marketing pages, complex layouts - not as a blanket assertion on every page.

## toHaveScreenshot basics

```ts
// Whole viewport
await expect(page).toHaveScreenshot("dashboard.png");

// Element-scoped - strongly preferred: smaller diff surface, fewer false positives
await expect(page.getByTestId("pricing-table")).toHaveScreenshot("pricing-table.png");

// Full scrollable page
await expect(page).toHaveScreenshot("landing.png", { fullPage: true });
```

First run fails with "snapshot doesn't exist" and writes the baseline; commit the generated `*-snapshots/` directory. Subsequent runs compare pixel-by-pixel (per the tolerances below). `toHaveScreenshot` auto-retries: it takes screenshots until two consecutive captures match (waits out animations), then compares with the baseline - another reason never to sleep before it.

Snapshots are stored next to the spec as `<spec>.ts-snapshots/<name>-<project>-<platform>.png` - per-project and per-OS by design, because font rendering differs across platforms.

## Handling dynamic content

Every source of nondeterminism must be masked, hidden, frozen, or excluded:

```ts
await expect(page).toHaveScreenshot("order-summary.png", {
  mask: [page.getByTestId("order-id"), page.getByRole("time")], // pink boxes over dynamic bits
  maskColor: "#FF00FF",
  stylePath: "e2e/screenshot.css",   // injected CSS for screenshot runs only
  animations: "disabled",            // default: finite animations fast-forwarded, infinite ones canceled
  caret: "hide",                     // default: text caret hidden
});
```

```css
/* e2e/screenshot.css - hide what masking can't reach */
.live-chat-widget, [data-ad-slot] { visibility: hidden !important; }
* { transition: none !important; }
```

Freeze the other usual suspects:

- **Time/dates** - `await page.clock.install({ time: new Date("2026-08-18T10:00:00") })` before `goto`.
- **API data** - mock with `page.route`/HAR so lists, avatars, and counts are constant.
- **Randomness in the app** - seed it via a test-env flag, or mask the region.
- **Images still loading** - assert content first (`await expect(hero).toBeVisible()`); screenshot assertions wait for two stable frames, but lazy-loaded images below the fold need `fullPage` scrolling or explicit waits on the `img` locator.
- **Fonts** - bundle fonts with the app; remote font CDNs are a classic CI-only diff source.

## Tolerances

```ts
await expect(page).toHaveScreenshot("chart.png", {
  maxDiffPixelRatio: 0.01,   // ≤1% of pixels may differ
  // or maxDiffPixels: 120,
  threshold: 0.2,            // per-pixel YIQ color distance 0..1 (default 0.2)
});
```

Set suite-wide defaults in config rather than per call:

```ts
expect: {
  toHaveScreenshot: { maxDiffPixelRatio: 0.01, animations: "disabled" },
},
```

Start strict (defaults); loosen only for genuinely anti-aliased content (charts, maps). A rising tolerance is usually a masked-content problem, not a threshold problem.

## Updating baselines

```bash
npx playwright test --update-snapshots            # rewrite all (careful)
npx playwright test visual/pricing.spec.ts -u     # scope updates to the change
npx playwright test -u --update-source-method=3way # writes conflict markers for review
```

Review updated PNGs in the PR like code - the diff image in the HTML report (`expected`/`actual`/`diff` tabs) is the review artifact. Never blanket-update to silence a red build.

## Cross-platform: generate baselines where CI runs

Pixel output differs between macOS, Windows, and Linux. If baselines were committed from a Mac, Linux CI fails forever. Two workable policies:

1. **Docker locally = CI parity (recommended).** Generate/update baselines inside the same image CI uses:

```bash
docker run --rm -v $(pwd):/work -w /work \
  mcr.microsoft.com/playwright:v1.55.0-noble \
  npx playwright test --update-snapshots
```

2. **CI-generated baselines.** A dedicated workflow (manual trigger) runs `--update-snapshots` on CI and commits/uploads the result; developers never generate baselines locally.

Either way: pin the Docker image tag to the exact `@playwright/test` version, and only commit the `-linux.png` variants CI will compare against (skip local-platform snapshots via `ignoreSnapshots: !process.env.CI` in config if local runs shouldn't do visual checks at all).

## Aria snapshots: structure without pixels

When the check is "the right things are on the page in the right order" rather than "it looks identical", `toMatchAriaSnapshot` is cheaper and cross-platform-stable:

```ts
await expect(page.getByRole("main")).toMatchAriaSnapshot(`
  - heading "Your orders" [level=1]
  - table:
    - rowgroup:
      - row "Order Status Total":
        - columnheader "Order"
        - columnheader "Status"
        - columnheader "Total"
`);
```

- Templates are partial - omit rows/regions you don't care about and they're ignored.
- Regex values handle dynamic text: `- cell ${/order-\d+/}`.
- Store large templates in files: `toMatchAriaSnapshot({ name: "orders-table.aria.yml" })`, updated with `--update-snapshots`.
- Rule of thumb: aria snapshot for structure/content regressions (works identically on every OS), pixel screenshot for visual styling. Many suites need only the former.

## Placement in the suite

- Put visual specs in their own project so they can run on one browser/platform (`chromium` on Linux) instead of the full matrix - visual diffs across three engines triple maintenance for little signal.
- Element screenshots + masking beat full-page shots; a full-page baseline invalidates on every unrelated change above the fold.
- A failed visual test on a PR that intentionally changed the UI is the workflow succeeding: update the baseline in that PR, reviewer approves the new image.
