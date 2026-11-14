# labctl

A single Bash CLI, [[labctl]], that manages all Linux-host labs with a uniform
verb set: profiles, lifecycle, config, hardware resize, monitoring and systemd
service management.

Each lab's `Makefile` delegates its `monitor` and `profiles` targets to it.

## Lab dispatch

`set_lab` maps a lab name to its directory and the `all` verb fans out across
labs.

The mappings are `win` -> [[win-lab]], `android` -> [[android-lab/lab]], `ios`
-> [[ios-lab]], `linux` -> [[linux-lab]]. `all` runs a command across `android`,
`win` and `linux` (plus `ios` on Linux). On macOS, `ios` is redirected to the
native `make -C ios-lab mac-*` path.

Source Lab dispatches directly to [[source-lab/run.py#main]] through
`source` or `source-lab`. It is included in `all status`, `all doctor` and
`all monitor`, but not in VM start/stop/restart/profile fan-out.

## Commands

The CLI exposes profiles, config, lifecycle, status/monitor, logs, shell, urls,
resize and service management.

Profiles are applied by writing a preset from the lab's `profiles/` into its
`.env`, or overlaid one-shot with `--profile`. `doctor` runs the lab's
`scripts/preflight.sh`; `service install|uninstall` manages the systemd unit.
`./labctl ui [--port N]` opens the [[dashboard]] (it runs
[[android-lab/lab/web_ui.py]], preferring the checkout's `.venv`).

## Per-lab behavior

`win`, `ios` and `linux` are single-VM labs; `android` is a multi-container
stack with `static` and `dynamic` modes.

The CLI branches on the lab for container names, endpoints, URLs and resize
semantics (SSH for linux, RDP for win, VNC for ios), and normalizes RAM units
per lab. The matching Makefiles are [[win-lab/Makefile]], [[linux-lab/Makefile]],
[[ios-lab/Makefile]] and [[android-lab/lab/Makefile]].

Source CLI verbs also include evidence contracts, detection, maps, crawler/CSV
operations and explicit [[source-lab/IMPORT.md]] dry-run/copy/rollback.
[[source-lab/RUNBOOK.md]] explains local operation and release gates.
