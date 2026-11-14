---
lat:
  require-code-mention: true
---
# Source engine tests

Retained engine specifications bind to the namespaced tests in [[source-lab/engine/tests]]. Run `python3 -m pytest` from `source-lab/engine`; [[source-lab]] describes runtime boundaries.

## Evidence schema

Schema tests pin the V2 serialization contract that the UI and reports depend on.

### Finding round trip

A Finding serializes to `schema_version: 2` with enum values as strings, and `from_dict` restores the same id, state, target and span line.

### Finding validation

A well-formed finding validates with no errors; removing `finding_id` yields exactly the "finding_id is required" message.

### Coverage serialization

Coverage serializes with `schema_version: 2` and keeps scanned and skipped file counts unchanged.

## Correlator

Correlator tests fix the confidence arithmetic and the three state transitions documented in [[source-lab#Runtime evidence]].

### Confidence formula

With default weights and a 0.1 discount, static 0.6 with no runtime scores 0.21/1.1 and static 0.8 with full runtime scores 0.93/1.1.

### State transitions

Two static leads and two events yield three findings: one `correlated_behavior`, one `not_observed_under_test` and one unattributed `runtime_observation`.

The matched script-injection lead gains a `dynamic_event` span; the spare `prototype_tamper` event on `window.fetch` becomes the unattributed finding.

### Live canary event names

Real canary events `property_tamper` and `listener_proxy` confirm the fetch-wrapping and listener-proxy leads, leaving no unattributed runtime findings.

### Replay script

The generated replay script embeds the requested test URL and the finding id.

## Platform detection

Detection tests pin how the CLI routes a target to an analyzer before any analysis runs.

### Browser extension

A directory with `manifest.json` is detected as a browser extension.

### Android app

A directory with `AndroidManifest.xml` is detected as an Android app.

### iOS app

An Xcode project or an `Info.plist` carrying `LSRequiresIPhoneOS`/`UIDeviceFamily` is detected as iOS before the macOS `Info.plist` fallback.

### macOS app

An `.app` bundle whose `Info.plist` has no iOS markers is detected as a macOS app.

### Windows app

A directory with a `.sln` solution file is detected as a Windows app.

### Electron app

A directory whose `package.json` declares an Electron entry point or dependency is detected as a Windows app instead of falling through to the browser analyzer.

## Static analyzers

Analyzer tests run each platform analyzer on its fixture and assert that the expected finding ids appear.

### Browser positive and clean

The positive extension yields broad host permissions, content-script registration, DOM script injection and fetch wrapping; the clean extension yields neither call-site finding.

### Android project

The Android fixture yields `debuggable`, an exported activity, `SYSTEM_ALERT_WINDOW`, a JavaScript interface bridge and universal file access.

### iOS project

The iOS fixture yields arbitrary-loads, a custom URL scheme, WKWebView user-script injection and method swizzling.

### iOS plist parse failure

An unreadable `Info.plist` produces no plist findings and records a `Failed to parse Info.plist` Coverage limitation instead of silently reporting nothing.

### Windows Electron

The Electron fixture yields `nodeIntegration`, disabled context isolation and a WebView2 document-created script.

### macOS sources

The macOS analyzer, run on the iOS fixture's Objective-C source, yields method swizzling and a WKWebView user script.

## Runtime sessions

Session tests cover key resolution, integrity verification and the CLI's fail-closed behaviour.

### Missing key fails closed

With neither key variable set, both the writer and the reader raise a configuration error instead of signing or trusting a bundle.

### Tampered bundle fails verification

Appending a line to `events.jsonl` after sealing makes `verify_integrity` report an invalid bundle and name `events.jsonl` as a mismatch.

### Conflicting key sources

Setting the env var and the key file to different keys raises a configuration error rather than silently preferring one.

### Short key rejected

A key shorter than 32 bytes is rejected with a message stating the minimum.

### Static-only run has no runtime limitation

A run with no runtime flags and no key writes static reports without recording a runtime limitation, because no runtime evidence was requested.

### CLI skips runtime evidence without a key

With no key and a requested session, `main` still writes static reports and records "runtime evidence skipped: no session key configured"; no finding becomes `correlated_behavior`.

### CLI refuses a tampered session

With a key but a tampered bundle, the CLI records an integrity limitation naming `events.jsonl` and does not correlate its events.

## CSV merge

Merger tests use temporary catalogs and check the default data paths after the split.

### Explicit directories

Passing `--sources`-equivalent directories joins the monitored catalog with `manifest-analysis.json` and writes the merged file and its mirror.

### Default data paths

The module defaults resolve to `doc/resources/iExtensionCrawler/sources` and `.../ext-analysis`, not to folders inside `engine/`.

## Reports

Report tests cover the STIX export and its CLI wiring.

### STIX platform pattern

A bundle with browser and Windows findings produces one indicator per finding, and each pattern carries that finding's own platform.

### STIX CLI format

`--format stix` writes `report.stix.json` with a bundle and indicators, and does not write the JSON artifacts from the other formats.

## Collectors

Collector tests check that every producer writes a bundle that passes integrity verification and contains its signature event types.

### Browser canary bundle

Without Playwright or an extension directory the runner writes a synthetic bundle whose files exist, whose integrity is valid and whose first event is `session_start`.

### Unique session ids

Two importer runs with the same timestamp produce distinct session directories, each with its own valid bundle and a single `session_start`.

### Refuse existing session directory

A writer refuses to open a session directory that already exists instead of appending to and re-sealing the previous bundle.

### Windows importer

PE-sieve hooks and unbacked memory plus an ETW event 8 produce `memory_hook`, `unbacked_exec` and `remote_thread` events in a valid bundle.

### macOS importer

A foreign framework image and a swizzled `NSURLSession` method produce `foreign_image_mapped` and `objc_swizzle` events.

### Android importer

A Frida agent mapping and Frida thread names produce `hook_library_mapped` and `instrumentation_thread` events.

### iOS importer

A MobileSubstrate tweak dylib and an ARM64 trampoline produce `tweak_framework_detected` and `arm64_trampoline` events.

## Binary parsers

Tests build small PE, Mach-O, ASAR and APK files in memory with `engine/tests/builders.py` and check what the stdlib parsers read from them.

### PE import and export tables

The PE parser returns imports by DLL, exports, export forwarders, the Authenticode and CLR flags and the machine width.

### A string is not an import

A symbol that appears only as text is not in the parsed import table.

### Malformed input is rejected

Truncated or non-matching input yields None or an empty result in every parser instead of raising.

### Mach-O load commands and signature

The Mach-O parser reads dylib, re-export and rpath commands, sections, undefined symbols, DYLD environment commands and the code signature with its flags, team id and entitlements.

### ASAR contents

The ASAR reader lists packed and unpacked entries and yields the text of packed source files.

### APK signing block

The signing-block reader reports the schemes present and the SHA-256 of the signing certificate, and an unsigned APK yields none.

## Browser research rules

Tests cover the manifest, source and userscript rules added from the research.

### Privileged permissions and content-script flags

Privileged permissions, MAIN-world and document_start content scripts, broad matches and externally_connectable produce capability findings; ordinary permissions do not.

### CSP, background and header stripping

CSP relaxations, persistent MV2 backgrounds and declarativeNetRequest rules that remove CSP headers are reported; an event page is not.

### Native API wrapping and remote code

WebSocket, EventTarget, Response, defineProperty, Proxy and toString hooks, the debugger and blocking webRequest, remote code loading and the userScripts API are reported as static leads with line-precise spans.

### Clean code stays clean

Ordinary extension code triggers none of the research rules.

### Multi-extension shims

The qx/shim.js and cs/<slug>-<idx>.js layouts are reported as multiplexer signatures; unrelated folders are not.

### Userscripts

==UserScript== metadata yields broad-match, document-start, page-world, privileged-grant and wildcard-connect findings, and a scoped @grant none script is page-world but not broad.

## Windows research rules

Tests cover the PE-structure, chain, proxy, hook-engine and Electron rules.

### Imports versus strings

An import-table entry gets higher confidence than a text-only reference, which carries a limitation.

### Injection chains

The classic injection, process hollowing and Early Bird APC chains are recognised from the import table and a benign binary is silent.

### DLL proxy and signature

A system-named DLL that forwards exports is a proxy; an unsigned system-named DLL is a weaker lead and a signed one is not flagged.

### Hook engines and CLR weaving

Detours, MinHook, Harmony, startup hooks and WebView2 calls inside a binary are reported.

### Electron fuses and ASAR

Dangerous fuse switches, ASAR-packed sources with the path inside the archive, and an unpacked app folder are reported; safe fuse states are not.

## macOS research rules

Tests cover entitlement, load-command, symbol, plist and source rules read from synthetic Mach-O files.

### Entitlements and signature flags

Entitlements, the ad-hoc flag and a missing hardened runtime come from the code signature; false entitlements are ignored.

### Load commands and rpaths

Re-exported and user-path dylibs and missing or writable rpaths are reported; system umbrella re-exports and existing directories are not.

### Interposition constructors and injection symbols

A parsed __interpose section, constructors, injection symbols and embedded DYLD environment are reported; a string alone is a low-confidence lead.

### LSEnvironment and source rules

DYLD variables in Info.plist and launchd plists, fishhook, constructors and WKUserScript timing and world are reported.

## Android research rules

Tests cover signing, injected libraries, manifest and WebView rules on synthetic APKs and source trees.

### APK signing block

Signing schemes and the certificate digest are recorded with a limitation, an unsigned APK is flagged and a v1-only signature is called out.

### Injected libraries and DEX hooks

Hooking libraries by file name, compiled-manifest permissions, DEX hook strings and apktool metadata are reported; ordinary libraries are not.

### Manifest services and providers

Accessibility services and startup-provider shims are reported; androidx and ordinary providers are not.

### WebView origins and bridges

Wildcard origins, JavaScript with a native bridge, message listeners and key listeners in injected script are reported; a listener without an injection API is not.

## iOS research rules

Tests cover provisioning identity, injected frameworks, hook symbols and user-script worlds.

### Provisioning identity and profile type

The Team ID, enterprise, development and ad-hoc profile types and dynamic-codesigning are reported with a comparison limitation; an App Store profile yields no profile finding.

### Injected frameworks and hook symbols

Hook frameworks by name and load command, hook symbols and binary entitlements are reported once each; ordinary frameworks and symbols are not.

### User-script worlds and in-app listeners

WKContentWorld.page is MAIN and defaultClient is ISOLATED, with document-start timing, key listeners and jailbreak paths reported.

### IPA archives

An IPA's binaries, framework names, plists and provisioning profile are inspected without extraction.

## Research scorecard

Tests cover the H1-H5 matrix, the decision matrix and how both reach the reports.

### Every platform maps into H1-H5

Rule ids of all five platforms map to the dimensions the research assigns, and unknown ids map to none.

### Scoring arithmetic

A dimension sums severity weight times confidence capped at 10, the total sums the five, and unmapped findings are counted but not scored.

### Decision matrix enrichment

Findings gain their dimension, benign context and verification test without overwriting existing values, and the new fields round-trip.

### Reports carry the scorecard

analysis-v2.json, summary.md and SARIF carry the scorecard, dimension and verification, and no finding's state changes.

### A lone userscript

A single .user.js file is analysed without a manifest.

## Repo map

Tests cover the structural map, its adapters, resolution, roles, filters, targets and ranking.

### Python symbols

The Python adapter records classes, methods, decorators, async functions, annotations, alias imports and `__all__` exports.

### TypeScript symbols

The TypeScript adapter records default components, arrow components, hooks, re-exports and multi-line imports with a specifier.

### Import resolution

Relative paths, `@/` aliases and external packages resolve to the expected file or external flag.

### Role cascade

Framework paths beat symbol and graph evidence, stores and database clients keep their roles, and unmatched files stay unknown.

### Filtering

Role and kind filters are ANDed across dimensions, values are ORed, and edges, entrypoints and cycles stay identical to the full map.

### Filtering without symbols

A kind filter on a `detail: files` artifact matches nothing and the CLI explains that symbol detail is required.

### Type index

Two same-named type definitions stay separate, only resolved imports count as references, and each definition keeps its file and line.

### Target segmentation

A monorepo yields separate browser-extension and Android targets, and a target filter narrows the files to one subtree.

### Binary-only target

A package with no source yields a target and `not_applicable` coverage instead of an empty clean tree.

### Determinism

Two runs over the same tree produce byte-identical JSON.

### Caps and coverage

Large files, minified bundles and budget stops are recorded in coverage, and a budget stop marks the map truncated.

### CLI generation and query

Generate writes the requested artifact, and query applies a filter without rewriting the map.

### Markup adapters

Astro frontmatter, Svelte scripts, HTML ids and assets, and CSS selectors and custom properties are extracted.

### PHP and Rust resolution

PSR-4 `use` statements and Rust `mod` and `crate::` paths resolve to files in the tree.

### Ranking

PageRank identifies an entrypoint with no importers and strongly connected components become cycles.

### Legacy AST fallback

The old AST stage keeps a multi-line import specifier, sees Python `def` and `export default function`, and labels an oversized file as not parsed.

## Repo map adapters

Tests for the missing adapters: the shared VFS, the Electron asar archive, Swift, Objective-C, Android and iOS. They bind to [[source-lab/engine/tests/test_sourcemap_vfs.py]], [[source-lab/engine/tests/test_sourcemap_asar.py]], [[source-lab/engine/tests/test_sourcemap_swift.py]], [[source-lab/engine/tests/test_sourcemap_objc.py]], [[source-lab/engine/tests/test_sourcemap_android.py]], [[source-lab/engine/tests/test_sourcemap_ios.py]] and [[source-lab/engine/tests/test_sourcemap_core.py]], one fixture per adapter built in the test.

### VFS disk contract

`DiskFS` exposes the `FileSystem` contract (`list`, `read`, `exists`, `stat`) with sorted deterministic listings and a label from the root.

### VFS traversal rejection

`FileSystem.normalize` rejects absolute paths, `..` segments and backslash traversal on every implementation, and `DiskFS` containment rejects resolved escapes.

### VFS archive and overlay

`ArchiveFS` serves lazy member slices under a `<archive>!/` prefix without extraction, never serves unpacked members, and `OverlayFS` unions listings with first-hit reads.

### Asar header and mount

`asar.read_header` parses the 8/16-byte Chromium pickle header, and `load_asar` flattens the JSON directory into packed offsets plus unpacked members.

### Asar header validation

A short, wrong-magic or truncated header raises `AsarError` instead of mounting garbage.

### Asar path traversal rejection

Members with `..`, absolute or backslash paths are dropped and reported in limitations, never mounted.

### Asar caps

Entry-count and uncompressed-size caps stop the mount and record a named limitation.

### Asar generation

`RepoMap.generate` walks an Electron tree and emits virtual paths such as `resources/app.asar!/main.js`, while the container and `.node` binaries land in `coverage.skipped`.

### Asar resolution and entrypoints

Relative imports resolve inside the asar first, then the `app.asar.unpacked` overlay on disk, and `node_modules` stays external; `package.json` `main` and `preload` become explicit entrypoints.

### Asar applicability

An asar with no JS is `partial`; a PE with no asar and no source is `not_applicable` with a named reason.

### Swift symbols

The Swift extractor records class/struct/enum/protocol/extension/property/typealias declarations with access levels, `@objc`/`@MainActor` attributes, parameters and return types.

### Swift resolution and roles

`import Module` and `@testable import` stay external under the Swift module policy, and folder and symbol conventions classify AppDelegate as entrypoint plus view, view_model, model, service and test roles.

### Swift targets

`.xcodeproj` `SDKROOT` plus `Info.plist` hints split macOS from iOS, source roots come from the `project.pbxproj` heuristic, and a binary `.app` is `not_applicable`.

### Swift provisioning evidence

`.mobileprovision` and `.entitlements` files fold into the iOS target as named evidence.

### ObjC symbols

The ObjC extractor records `@interface`, `@implementation`, categories, `@protocol`, `@property`, methods and C functions, with `+` methods counted as exported.

### ObjC header disambiguation

`.h` files parse as ObjC only inside Apple targets or when `looks_like_objc` finds tokens; otherwise they are skipped with an `ambiguous header` reason.

### ObjC pairing and imports

Quoted `#import "Local.h"` resolves to a file, `<Framework/Header.h>` and `@import Module;` stay external, and [[source-lab/engine/source_lab/sourcemap/headers.py#pair_implementation]] adds the missing implementation-to-header edge.

### ObjC binary-only app

A `.app` bundle with only plists and a binary reports `not_applicable` coverage and zero symbols.

### Android symbols

Kotlin and Java extractors record classes, interfaces, methods and properties, and `toolchain.languages` shows `regex` provenance per language.

### Android resolution

Package imports resolve across `app/src/main/java` and library modules, wildcards resolve to the package directory, and androidx stays external.

### Android manifest

`AndroidManifest.xml` yields permissions and components with exported and launcher flags, the LAUNCHER activity becomes the entrypoint, and manifest evidence drives roles.

### Android skips

`R.kt`, `BuildConfig.java` and databinding outputs are skipped with named generated reasons, and `build/` directories are pruned wholesale.

### Android binary-only apk

An `.apk` with no source is a binary-only `android-app` target with `not_applicable` coverage, and the APK is never extracted.

### iOS target detection

Info.plist iOS hints, `SDKROOT iphoneos`, entitlements and the pbxproj heuristic converge on one `ios-app` target with full applicability.

### iOS symbols and header resolution

Swift and ObjC adapters run together, quoted headers resolve through the pbxproj source roots, and Swift module imports stay external.

### iOS storyboard edges

Storyboard `customClass` references become resolved edges to the declaring header or Swift file through the type index, and unresolved classes stay `missing`.

### iOS binary ipa

An `.ipa` with no source is `not_applicable` with a no-extraction reason; no IPA VFS is implied.

### Core python and typescript symbols

The Python adapter records decorators, annotations and `__all__`, and the TS adapter records components, hooks, exports and multi-line imports with a specifier.

### Core resolution and roles

`@/` aliases, missing relative imports and external packages resolve to the documented reasons, and unmatched files stay `unknown`.

### Core filtering

`MapFilter(targets=("android-app",))` maps platform names to target roots before path filtering, and edges, entrypoints and cycles stay identical to the full map.

### Core type index

Two same-named interface definitions stay separate entries and only resolved imports count as references.

### Core determinism and caps

Two runs produce byte-identical JSON, size-cap overruns and minified bundles land in `coverage.skipped` with named reasons.

### Core cli and query

Generate writes the artifact, query applies a filter without rewriting the map, and a kind filter on a `files` artifact asks for `--map-detail full`.

### Core ranking

PageRank identifies a no-importer entrypoint and a three-file import cycle becomes one strongly connected component.


## Distribution

Distribution tests cover the local launcher, private state, package isolation and honest evidence labels.

### Read-only readiness

Status must not create directories or require optional resources; explicit setup creates private state without downloads.

### Five-platform CLI reports

Each of the five platform fixtures must produce every supported report and preserve static evidence states and coverage.

### Per-target output isolation

Targets with the same basename must receive separate default output folders; a missing target must not create output.

### Module isolation

Namespaced engine imports must work even when the Android host has already loaded top-level modules with the same names.

### Unsupported VM commands

VM start, resize, shell and reset must fail without creating state because Source Lab runs local analysis rather than a VM.

### Synthetic evidence stays static

Signed but simulated canary sessions must carry an explicit synthetic label and never promote findings to observed behavior.

### Catalog inputs remain unchanged

CSV joining can write into mutable state without modifying operator-supplied resource catalogs.

### Standalone PE input

A single executable path must be parsed directly and counted in coverage, rather than treated as an empty directory scan.

## Contracts

Contract tests validate actual engine output and keep generated schemas/types synchronized with the Python models.

### Evidence artifact compatibility

Produced V2 findings and coverage must validate against exported contracts; unsupported schema versions must be rejected.

### Malformed findings rejected

Out-of-range or non-finite confidence, unknown states, empty evidence and missing target identities must fail contract validation.

### Structural map compatibility

Generated structural maps must satisfy the V1 contract and reject evidence-contract version numbers.

### Generated contracts stay current

Committed JSON Schema and frontend TypeScript must match regeneration from the engine models without manual duplicate definitions.

## Workspace fixtures

Owned scenarios generate reports, maps, merge output and synthetic signed sessions in temporary folders without remote acquisition.

### Offline integration workspace

The fixture generator must produce valid contracts, a verifiable synthetic session, a loadable-format MV3 archive and matching provenance hashes without persisting the ephemeral signing key.

### Existing workspace preserved

Fixture generation must refuse an existing workspace without overwriting operator files.

## Artifact API

Console tests exercise the read-only evidence routes over localhost HTTP with generated first-party workspace data.

### Evidence and session review

Evidence listing/detail and session timelines return generated fixture data with no-store headers and explicit unverified session-integrity labels.

### Report allowlist

Only the five planned HTTP report formats may download with safe attachment names; session seals and CLI-only STIX stay inaccessible.

### Host and parameter boundaries

Foreign Host headers, traversal, duplicate or unknown parameters and missing targets must fail; excluded integrations have no endpoints.

### Symlinks and nonregular files refused

Directory/file symlinks and named pipes must be refused without following outside paths or blocking a request.

### Bounded and malformed artifacts

Oversized JSON/reports, malformed shapes, non-finite values and unsupported evidence versions must return explicit errors instead of successful empty results.

### Event timeline truncation

Session responses cap events at 500 and distinguish an exactly-full timeline from a truncated one.

### Aggregate response budget

Multiple individually small artifact files must still fail when their combined bytes exceed the per-request response budget.

### Directory listing cap

Target listings must stop at the configured cap and report truncation without reading every workspace directory.
