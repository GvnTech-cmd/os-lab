# Runtime collectors and imported sessions

Use only telemetry from targets you own or are authorized to assess. No archive,
dataset, binary or telemetry export is bundled. Sessions remain in private storage.

The browser canary runs only on explicit request. Live collection needs separately
installed Playwright and Chromium and an unpacked authorized extension. Missing
tooling or a clean baseline uses `synthetic` mode; these events cannot establish
live behavior. Browser failures use `collection_failed`; partial events are not
correlated. Static analysis remains usable in either case.

The engine retains four Python libraries:

| Module under `source_lab.collectors` | Inputs |
|---|---|
| `windows.importer.WindowsTelemetryImporter` | Operator PE-sieve results and ETW events |
| `macos.importer.MacOSTelemetryImporter` | dyld image lists and Objective-C swizzles |
| `android.importer.AndroidTelemetryImporter` | Process maps, thread names and logcat |
| `ios.importer.IOSTelemetryImporter` | Loaded dylibs and trampoline observations |

Each accepts `output_root` and `TargetIdentity` on construction and writes a signed
bundle through `import_session(...)`. Pass `synthetic=True` for generated or
simulated telemetry. Imported telemetry includes an explicit limitation: these
libraries do not launch native collectors or independently attest input origin.
Native collection workflows remain NEXT-02, not an installed capability.

Configure `IQ_SESSION_HMAC_KEY` or `IQ_SESSION_HMAC_KEY_FILE` before importing.
Keys must contain at least 32 bytes; console-managed files are mode 0600 where
supported. Matching environment and file values are accepted; conflicting values
fail closed. Never put keys in CLI arguments, catalog data or version control.

Put operator-reviewed session bundles in the matching target's
`analysis/<slug>/runtime-sessions/<session>/` directory. Evidence GET can review
metadata/events, explicitly labeled unverified. Preview and confirm
`settings/runtime` with `action=verify-session`, `slug`, `session` for local HMAC
and hash verification; a successful job validates integrity, not whether a
collector's claims are true. Use detection's `session` option to correlate.
Correlation requires valid signed metadata/events, matching target and platform,
and a nonsynthetic, successful collection. Rotation requires the original key
for old bundles; rotation never rewrites old signatures.
