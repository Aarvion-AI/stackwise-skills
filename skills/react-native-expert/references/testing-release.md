# Testing & Release (Jest + RNTL, Maestro, EAS Build/Update)

## Test stack layers

| Layer | Tool | What it proves |
|-------|------|----------------|
| Unit/component | Jest + `@testing-library/react-native` | Logic and screen behavior in isolation |
| E2E smoke | Maestro | Real app on a real simulator/emulator boots and core flows work |
| Type safety | `npx tsc --noEmit` | Compile-time contract, incl. typed routes |

## Jest + React Native Testing Library

Setup (`jest-expo` handles transforms for Expo SDK packages):

```jsonc
// package.json
{
  "jest": {
    "preset": "jest-expo",
    "transformIgnorePatterns": [
      "node_modules/(?!((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|expo-router|@shopify/flash-list)"
    ],
    "setupFilesAfterEnv": ["./jest.setup.ts"]
  }
}
```

Component test - query the way a user (or screen reader) finds things:

```tsx
import { render, screen, userEvent } from '@testing-library/react-native';
import { AddToCart } from '@/components/AddToCart';

test('adds the product to the cart', async () => {
  const onAdd = jest.fn();
  render(<AddToCart product={{ id: '42', title: 'Mug' }} onAdd={onAdd} />);

  const user = userEvent.setup();
  await user.press(screen.getByRole('button', { name: 'Add to cart' }));

  expect(onAdd).toHaveBeenCalledWith('42');
  expect(await screen.findByText('In cart')).toBeOnTheScreen(); // findBy* awaits async UI
});
```

Rules:
- Prefer `getByRole(..., { name })` (reads `accessibilityRole` + label) → `getByLabelText` → `getByTestId`. If a component is hard to query, it is inaccessible - fix the component, not the test.
- Use `userEvent` over `fireEvent` (realistic event sequences); always `await` its calls.
- `findBy*` / `waitFor` for async updates - never `act()` gymnastics or arbitrary `setTimeout`.
- Testing expo-router screens: use `renderRouter` from `expo-router/testing-library` to mount a route tree and assert on `screen` plus the router state.
- Mock native modules at the JS boundary (`jest.mock('expo-haptics')`); don't mock your own components.

Run: `npx jest --ci` - fix failures and re-run until the suite is green.

## Accessibility + testID discipline

This is what makes the app automatable (Maestro, RNTL, QA crawlers) and screen-reader usable - one habit serves all three:

```tsx
<Pressable
  accessibilityRole="button"
  accessibilityLabel="Remove Mug from cart"   // human-meaningful, includes context
  accessibilityState={{ disabled: isBusy }}
  testID="cart-remove-42"                     // stable, kebab-case, id-suffixed in lists
  onPress={remove}
/>
```

- Every interactive element: `accessibilityRole`, `accessibilityLabel` (if the visible text isn't self-explanatory), `testID`.
- `testID` naming convention: `<screen|component>-<action>[-<id>]` - stable across copy changes and locales, which is precisely why Maestro flows should target ids, not text.
- Screens: give the root a `testID` (`screen-checkout`) so E2E can assert arrival.
- Images that convey meaning need `accessibilityLabel`; decorative ones get `accessibilityElementsHidden`/`importantForAccessibility="no"`.

## Maestro smoke flows

Flows live in `.maestro/*.yaml`; they drive the real dev build.

```yaml
# .maestro/checkout-smoke.yaml
appId: com.acme.shop
---
- launchApp:
    clearState: true
- assertVisible:
    id: "screen-home"
- tapOn:
    id: "tab-search"
- inputText: "mug"
- tapOn:
    id: "product-42"
- tapOn:
    id: "add-to-cart"
- assertVisible: "In cart"
- takeScreenshot: checkout-smoke
```

- Run locally: `maestro test .maestro/` against a booted simulator/emulator with the dev build installed. Fix failures and re-run until every flow passes.
- Keep smoke flows short (launch, auth, one revenue path); deep matrices belong to dedicated QA runs.
- `tapOn: { id: ... }` matches `testID`; text matching is the fallback, not the default.
- CI: `eas build` a simulator build, then run Maestro on it (EAS Workflows has a maestro job type).

## EAS Build

```jsonc
// eas.json
{
  "cli": { "appVersionSource": "remote" },
  "build": {
    "development": { "developmentClient": true, "distribution": "internal" },
    "preview":     { "distribution": "internal", "channel": "preview" },
    "production":  { "autoIncrement": true, "channel": "production" }
  },
  "submit": { "production": {} }
}
```

- `eas build --profile development --platform ios` → dev client (needed for any custom native code; Expo Go can't load it).
- `eas build --profile production --platform all` then `eas submit` for stores.
- Secrets: `eas env:create` / EAS environment variables, never committed `.env` for production keys.
- Version bumping: let `autoIncrement` + remote `appVersionSource` own `buildNumber`/`versionCode`; humans own the marketing `version` in `app.json`.
- After a build fails, read the phase logs on the EAS dashboard (install-deps vs prebuild vs gradle/xcode phase tells you whether it's a JS dep, config plugin, or native problem).

## EAS Update (OTA)

- `eas update --channel preview --message "fix: cart total"` ships JS + assets to builds on that channel with a matching `runtimeVersion`.
- `runtimeVersion` is the native compatibility contract. Use `{ "policy": "fingerprint" }` in `app.json` so it changes automatically whenever native code would change; then an OTA can never land on an incompatible binary.
- OTA CAN ship: JS/TS changes, styling, assets, config that lives in JS. OTA CANNOT ship: new native modules, config-plugin changes, SDK upgrades, app icon/splash, permission declarations - those need a new build + store release.
- Channels map builds to update streams (`preview`, `production`); `eas update:rollback` reverts a bad update.
- Release checklist: `tsc --noEmit` clean → `expo-doctor` clean → jest green → maestro smoke green on the exact build profile → then build/update.
