# Real-Device Clouds: AWS Device Farm and BrowserStack App Automate

Real, non-rooted cloud devices are the release gate - and for prod builds with
Play Integrity / attestation or cert pinning, they are the ONLY place the app
will run at all. Plan around two consequences:

- **Rooted/emulated detection**: the app may open on an emulator or rooted
  device and then blank out, force logout, or exit. Never debug that - move to
  a real, non-rooted device.
- **Pinned-blind network**: cert pinning blocks MITM proxying on devices you
  don't control. Do not build assertions on intercepted traffic; assert on
  what's on screen (screenshots, page source, OCR).

## AWS Device Farm (custom environment)

Always use **custom environment mode** with your own testspec - the standard
environment's parsing and lifecycle are too opaque for real suites.

### The preinstalled-Appium trap

Device Farm hosts ship an `appium` on PATH that is an **Appium 1.x CLI
wrapper with no `driver` subcommands**. `appium driver install ...` fails with
an unknown-command error. The fix, in the testspec install phase: install
Appium 2.x globally so it shadows the wrapper, then install the driver at a
version compatible with your Appium major, then start with `--base-path /`.

### testspec.yml skeleton

```yaml
version: 0.1
phases:
  install:
    commands:
      - export APPIUM_SKIP_CHROMEDRIVER_INSTALL=1
      - npm install -g appium@2            # shadow the preinstalled 1.x wrapper
      - which appium && appium --version   # MUST print 2.x
      - appium driver install uiautomator2@3.x   # pin compatible with appium major
      - pip3 install -r $DEVICEFARM_TEST_PACKAGE_PATH/requirements.txt
  pre_test:
    commands:
      - appium --base-path / --port 4723 --log-timestamp
        --log $DEVICEFARM_LOG_DIR/appium.log >/dev/null 2>&1 &
      # wait for the server, not a fixed sleep
      - >-
        for i in $(seq 1 30); do
          curl -sf http://127.0.0.1:4723/status && break; sleep 1;
        done
  test:
    commands:
      - cd $DEVICEFARM_TEST_PACKAGE_PATH
      - export APP_PATH=$DEVICEFARM_APP_PATH
      - export DEVICE_UDID=$DEVICEFARM_DEVICE_UDID
      - python3 -m pytest tests/ -x --tb=short
  post_test:
    commands:
      - cp -r $DEVICEFARM_TEST_PACKAGE_PATH/artifacts $DEVICEFARM_LOG_DIR/ || true
artifacts:
  - $DEVICEFARM_LOG_DIR
```

Client connects to `http://127.0.0.1:4723` with path `/` - matching
`--base-path /`. A mismatch shows up as 404s on `POST /session`.

### Packaging and scheduling

```bash
# package: zip your tests (Device Farm unpacks to $DEVICEFARM_TEST_PACKAGE_PATH)
zip -r test_bundle.zip tests/ requirements.txt

aws devicefarm create-upload --project-arn $PROJECT_ARN \
  --name app.apk --type ANDROID_APP
aws devicefarm create-upload --project-arn $PROJECT_ARN \
  --name test_bundle.zip --type APPIUM_PYTHON_TEST_PACKAGE
aws devicefarm create-upload --project-arn $PROJECT_ARN \
  --name testspec.yml --type APPIUM_PYTHON_TEST_SPEC
# PUT each file to the returned presigned URL, wait for status SUCCEEDED, then:
aws devicefarm schedule-run --project-arn $PROJECT_ARN \
  --app-arn $APP_ARN --device-pool-arn $POOL_ARN \
  --test type=APPIUM_PYTHON,testPackageArn=$PKG_ARN,testSpecArn=$SPEC_ARN
```

- The app under test is `$DEVICEFARM_APP_PATH` - do not bake an .apk into the
  test bundle.
- Secrets: Device Farm has no native secret store for testspecs; inject via a
  pre-encrypted file in the bundle or fetch at runtime. Never commit them.
- Device pools: pin exact models if any step is coordinate-dependent
  (`opaque-ui-strategies.md`); a "Top devices" pool will vary resolution
  between runs and silently break coordinate taps.
- Artifacts: everything copied into `$DEVICEFARM_LOG_DIR` is downloadable per
  device after the run - put your evidence bundles there.

## BrowserStack App Automate

BrowserStack runs YOUR Appium client from your machine/CI against their hosted
device + server. No testspec: upload the app, point the client at their hub.

```bash
curl -u "$BS_USER:$BS_KEY" -X POST \
  "https://api-cloud.browserstack.com/app-automate/upload" \
  -F "file=@app.apk"          # returns {"app_url": "bs://<hash>"}
```

```python
opts = UiAutomator2Options().load_capabilities({
    "platformName": "Android",
    "appium:automationName": "UiAutomator2",
    "appium:app": "bs://<hash>",
    "bstack:options": {
        "userName": os.environ["BS_USER"],
        "accessKey": os.environ["BS_KEY"],
        "deviceName": "Google Pixel 8",
        "osVersion": "15.0",
        "appiumVersion": "2.6.0",       # request a 2.x server explicitly
        "realMobile": True,
        "debug": True,                   # screenshots per command
        "networkLogs": False,            # pinned apps yield nothing useful anyway
    },
})
driver = webdriver.Remote("https://hub-cloud.browserstack.com/wd/hub", options=opts)
```

Note the hub path is `/wd/hub` on BrowserStack - their server, their base
path. Mark results so the dashboard is triageable:

```python
driver.execute_script('browserstack_executor: {"action": "setSessionStatus", '
                      '"arguments": {"status": "passed", "reason": "smoke ok"}}')
```

## Choosing between them

- **Device Farm**: pay-per-device-minute or private fleets, IAM-native, runs
  your whole test process on the host next to the device (low latency, offline
  CI). More setup friction (uploads, testspec, the Appium 1.x trap).
- **BrowserStack**: fastest to first run, huge public device matrix, good
  dashboards. Client runs remotely from the device (every command crosses the
  internet - raise waits), and concurrency is plan-limited.

## Cloud-run triage

When a locally-green suite fails in the cloud, classify before touching code:

1. **Environment gap** - Appium version, base path, missing driver: read the
   server log first (`appium.log` / BrowserStack "Raw logs").
2. **Attestation/pinning** - app opens then blanks or logs out: confirm the
   device is real and non-rooted; assert via screenshot/OCR, not network.
3. **Timing** - real devices are slower; raise explicit-wait ceilings.
4. **Resolution** - coordinate taps drifted: re-pin the device model or derive
   coordinates from live bounds.
5. **Actual app bug** - reproduce with the evidence bundle before filing.

Fix, re-run the pool, and repeat until the run is clean three consecutive
times - that is the bar for calling a device pool a release gate.
