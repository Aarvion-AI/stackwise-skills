# Unattended Authenticated Flows: Email OTP, Secrets, Session Reuse

Most consumer apps gate everything behind an OTP wall. A suite that needs a
human to type a code is not automation. The reliable unattended path is
**email OTP read over IMAP** from a dedicated test inbox.

## Account discipline (non-negotiable)

- Use a **dedicated test/UAT account**, never a personal one. Screenshots of
  the logged-in app - orders, addresses, names - land in evidence bundles and
  cloud dashboards. A personal account leaks PII into every artifact store.
- The inbox needs programmatic access: an **app password** (mail providers
  require this for IMAP when 2FA is on) or OAuth token.
- **No secrets in code or repo.** Everything arrives via environment variables
  or a secret store, resolved at runtime:

```python
import os
TEST_EMAIL = os.environ["QA_TEST_EMAIL"]
IMAP_APP_PASSWORD = os.environ["QA_IMAP_APP_PASSWORD"]  # app password, not login pw
```

In CI, source these from the platform's secret mechanism. On AWS, prefer
runtime resolution from Secrets Manager over baking values into files.

## The email-first gotcha

Login screens usually default to a **phone number** field; SMS OTP is not
automatable without paid SMS-inbox services and is flaky. Apps almost always
offer an email path - but you must **switch to it explicitly** before
submitting. The flow the suite must encode:

1. On the login screen, find and tap the "use email" toggle/link (often small,
   often `clickable=false` on RN - use bounds+gesture, see
   `opaque-ui-strategies.md`).
2. Enter the test email, submit, and note the submit time.
3. Poll IMAP for the OTP mail, extract the code.
4. Enter the code programmatically and assert the logged-in landing state.

## Reading the OTP over IMAP

```python
import email, imaplib, re, time
from email.header import decode_header

def fetch_otp(host, user, app_password, since_ts, sender_hint="",
              otp_len=6, timeout=120):
    """Poll for an OTP email newer than since_ts; return the code."""
    deadline = time.time() + timeout
    pat = re.compile(rf"\b(\d{{{otp_len}}})\b")
    while time.time() < deadline:
        m = imaplib.IMAP4_SSL(host)
        m.login(user, app_password)
        m.select("INBOX")
        crit = f'(FROM "{sender_hint}")' if sender_hint else "ALL"
        _, data = m.search(None, crit)
        for uid in reversed(data[0].split()[-10:]):          # newest few only
            _, msg_data = m.fetch(uid, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            if email.utils.parsedate_to_datetime(msg["Date"]).timestamp() < since_ts:
                continue                                     # stale OTP from a past run
            body = _text_of(msg)
            subj = str(decode_header(msg["Subject"])[0][0])
            hit = pat.search(subj) or pat.search(body)
            if hit:
                m.logout()
                return hit.group(1)
        m.logout()
        time.sleep(5)
    raise TimeoutError("OTP email did not arrive")

def _text_of(msg):
    if msg.is_multipart():
        return "".join(
            p.get_payload(decode=True).decode(errors="ignore")
            for p in msg.walk() if p.get_content_type() == "text/plain")
    return msg.get_payload(decode=True).decode(errors="ignore")
```

Hard-won details baked in above:

- **Timestamp filter**: without `since_ts`, reruns happily read the previous
  run's expired OTP. Record `time.time()` immediately before submitting the
  email in the app.
- **Subject first**: many senders put the code in the subject line; bodies are
  often HTML-heavy multipart.
- **Poll, don't sleep once**: delivery is 5-60s; poll every ~5s with a hard
  deadline, and fail loudly with an evidence capture if it never arrives.

## Entering the code

OTP inputs are often N separate single-digit boxes. Try `send_keys` of the
full code into the first box (most implementations auto-advance); if the tree
is opaque, tap the first box's bounds then use
`driver.execute_script("mobile: type", {"text": code})` or per-digit
`press_keycode` (Android keycodes 7-16 map to digits 0-9).

## Session persistence: log in once, reuse everywhere

The asymmetry that shapes suite structure:

- `terminate_app` / `activate_app` (or relaunching the session with
  `appium:noReset: True`) → **session survives**, still logged in.
- Clearing app data (`appium:noReset: False`, `driver.reset()`, fresh install,
  `adb pm clear`) → **session destroyed**, OTP wall returns.

Therefore:

```python
@pytest.fixture(scope="session")
def logged_in_driver():
    driver = make_driver(no_reset=True)
    if not is_logged_in(driver):          # cheap check: look for a home marker
        do_email_otp_login(driver)        # ONCE per suite run
    yield driver
    driver.quit()

@pytest.fixture(autouse=True)
def clean_slate(logged_in_driver):
    """Between tests: restart the app, keep the session."""
    logged_in_driver.terminate_app(APP_ID)
    logged_in_driver.activate_app(APP_ID)
    wait_for_home(logged_in_driver)
```

- `is_logged_in` first: on reruns the device may already hold a session -
  skipping the OTP saves a minute and an email per run.
- Never "reset for isolation" mid-suite; terminate/relaunch is the correct
  clean-enough state. Reserve data-clearing for tests that explicitly test
  first-run/logout, and run those **last**.
- OTPs are rate-limited server-side. A suite that logs in per-test will get
  the account throttled or flagged; once-per-run stays under every limit seen
  in practice.

## Verification checklist for the auth module

1. Run the login flow standalone: fresh state → logged-in home, no human
   input. Fix and re-run until it passes clean.
2. Run the whole suite twice back-to-back: second run must reuse the session
   (assert the OTP path was skipped).
3. Grep the repo and artifacts for the test email, password, and codes:
   secrets must appear nowhere. Evidence screenshots of the OTP screen are
   fine only because the account is a disposable test identity.
