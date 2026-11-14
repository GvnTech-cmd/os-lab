# ios-lab

An iOS Simulator lab with two paths: a macOS VM in `dockurr/macos` on Ubuntu
Server, or native Xcode / `xcrun simctl` / Appium on real macOS (Apple's EULA
restricts macOS virtualization to Apple hardware).

See [[ios-lab]], the Ubuntu service [[ios-lab/docker-compose.yml]], the native
scripts [[ios-lab/mac]] and the runbook [[ios-lab/README.md]].

## Ubuntu path (macOS VM)

The `macos` service exposes a web viewer (:8006) and VNC (:5900) and requires
KVM, following the shared VM pattern.

Host provisioning is [[ios-lab/scripts/setup-ubuntu.sh]]; readiness is
[[ios-lab/scripts/wait-ready.sh]]; a GPU override is
[[ios-lab/docker-compose.gpu.yml]]. Research is in
[[ios-lab/knowledge/setup-ubuntu.md]].

## Native macOS path

On macOS the lab drives the real Simulator toolchain through `make -C ios-lab
mac-*`.

Environment checks [[ios-lab/mac/doctor-mac.sh]], setup
[[ios-lab/mac/setup-mac.sh]], simulator control [[ios-lab/mac/run-simulator.sh]]
and [[ios-lab/mac/stop-simulator.sh]], Appium [[ios-lab/mac/appium.sh]], idb
[[ios-lab/mac/idb.sh]] and the XCUITest smoke run
[[ios-lab/mac/xcuitest.sh]]; device presets in [[ios-lab/mac/profiles]].
`labctl` refuses the Ubuntu path on macOS — see [[labctl#Lab dispatch]].

Optional automation follows the same install/start/stop pattern as Appium:
`idb.sh install` puts the client in `~/.oslab/idb` and takes the companion
from Homebrew, `idb.sh start` runs a companion for the booted simulator, and
`xcuitest.sh smoke` creates a real XCUITest session through the running
Appium server to prove the whole chain. All of them appear on the iOS Lab
page as previewed actions and stay optional — the simulator runs without
them.

The macOS Lab shares this directory but drives **macOS applications**, not
the simulator: [[ios-lab/mac/macos-app.sh]] reports status and doctor state and
runs one Appium mac2 session that activates Finder
(`macos-app.sh smoke`). Its only requirements are Homebrew, Node and
Appium (mac2 driver) — Xcode and the iOS runtimes belong to the iOS Lab —
and mac2 needs Accessibility permission in System Settings to control
applications. `appium.sh install` installs both the XCUITest and mac2
drivers, so one Appium server serves both lab pages.

Beyond the one-shot smoke run, [[ios-lab/mac/macos-repl.mjs]] keeps a mac2
session open for interactive work from a terminal
(`make -C ios-lab mac-app-repl APP=<bundle-id>`): it prints the app's
accessibility tree, finds elements by label and clicks or types into them
by number, and saves screenshots into artifacts/. It is a local operator
tool — the web console never runs interactive sessions and keeps its
preview → confirm model for every action it does run.

The dashboard's simulator panel (see [[dashboard]]) drives the same scripts:
`start` accepts a `device` (a UDID or unique name, validated against
`xcrun simctl` by the console) so the panel can boot the device picked in its
frame, and read-only `/api/labs/ios/simulator` and
`/api/labs/ios/screenshot` endpoints feed the panel's device list and live
screen.

## Research

The top iOS-in-Docker options, networking and operational limits.

They are documented across [[ios-lab/knowledge]] (docker-options, networking,
operations, usecases, references) and [[ios-lab/knowledge/setup-mac.md]].
