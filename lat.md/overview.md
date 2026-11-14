# Overview

The shared architecture and operating model behind all four labs: one
containerized guest per lab, driven by `make` and the shared CLI [[labctl]],
with mutable state under `storage/` and configuration in `.env` plus compose.

## The four labs

os-lab provides four OS security labs that share one operating model and file
layout, so operating one teaches the others.

| Lab | Guest | Engine | Primary endpoints |
|---|---|---|---|
| [[win-lab]] | Windows | `dockur/windows` | web :8006, RDP :3389 |
| [[android-lab]] | Android | `budtmo/docker-android` + tools | noVNC :6080, ADB :5555, MobSF :8000 |
| [[ios-lab]] | iOS (macOS) | `dockurr/macos` or native | web :8006, VNC :5900 |
| [[linux-lab]] | Linux | `qemux/qemu` | web :8006, SSH :2222 |

## Shared pattern

Every Linux-host VM lab (win, linux, and the Ubuntu path of ios) follows the
same lifecycle and file layout.

- `scripts/preflight.sh` — read-only host checks (OS, KVM, runtime, ports, disk, RAM).
- `scripts/setup-ubuntu.sh` — idempotent host provisioning (KVM + Docker + groups + dirs).
- `scripts/wait-ready.sh` — readiness probing (web viewer, and SSH/VNC/install marker).
- `scripts/backup.sh` / `scripts/restore.sh` — cold, reversible archives of `storage/`.
- `scripts/install-service.sh` — a systemd unit to start the lab at boot.
- `Makefile` — a uniform target set (`preflight`, `boot`, `status`, `backup`, `reset`, ...).
- `profiles/` — `lightweight` / `development` / `performance` presets.

The android lab adds static (KVM-free) and Windows zero-admin paths on top of
this pattern; see [[android-lab#Execution paths]].

## Isolation stance

Guests are treated as untrusted.

The labs never expose their viewers or remote-access ports publicly by default,
and each lab's `knowledge/` directory documents network containment for
detonation-style work. This is a defensive, authorization-only project — see
[[tooling#Security and licensing]].

## Why a monorepo

The labs are siblings with a shared operating model and one CLI ([[labctl]]).

Keeping them together lets `./labctl all status` report every Linux-host lab at
once and lets the common script/Makefile pattern evolve in lockstep.

## Portable Source Lab

[[source-lab]] adds native Python source/package analysis beside the OS guests.
Static detection and structural maps need no VM, Node or container runtime.

The local dashboard provides guarded jobs and file-backed artifact views; public
Pages provides information and first-party workflow docs, without engine polling.
