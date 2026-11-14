# linux-lab bonus tools

Small, **read-only** helpers that close recurring gaps students and instructors
hit when running the Open Source OS lab. They are shipped, working reference
implementations — study them as worked examples of the lab's script style
(`set -euo pipefail`, clear exit codes, no side effects, portable between macOS
and Linux). They are **not** reservable vize tasks.

None of these connect anywhere, write files, export values or print the contents
of a `.env` value or an SSH key. Each exits `0` when clean, `1` when it finds a
problem, and `2` on a usage or I/O error, so they drop straight into a check
pipeline.

| Tool | What it does | Why it exists |
|------|--------------|---------------|
| `env-doctor.sh` | Compares a lab `.env` against its `.env.example`: missing keys, empty values, unknown/extra keys, duplicate keys. | Labs ship `.env.example` but nothing verifies a copied `.env` still matches — a silent drift that breaks `docker compose` with a confusing error. |
| `port-check.sh` | Reports whether a lab's host ports (`WEB_PORT`/`SSH_PORT` or ports you pass) are free on `127.0.0.1`, using only bash `/dev/tcp`. | "port is already allocated" is the most common lab-start failure; this catches it before `make up`, with no `nc`/`lsof`/`ss` dependency. |
| `ssh-config-doctor.sh` | Summarises each `~/.ssh/config` Host block and flags a missing `HostName`, an `IdentityFile` that is absent on disk, or a key with group/other-readable permissions. | Remote-SSH (OS-02/OS-17/OS-20) breaks constantly on these three faults; a key with loose permissions is silently ignored by `ssh`. |
| `shell-lint.sh` | Runs `bash -n` (the repo's required gate) over the `*.sh` you touched, plus `shellcheck` advisories when it is installed. | `run-tests.sh` checks the whole repo; there was no quick, scoped syntax check for just your change before a PR. |
| `md-linkcheck.sh` | Checks that local (non-http) links in Markdown resolve on disk, resolving each relative to the file it appears in. | PRs add `VERIFY.md`/`REPORT.md` with relative links; a typo'd path is caught by nothing and only shows up as a dead link later. |
| `secret-scan.sh` | Scans for known credential signatures (PEM/OpenSSH keys, AWS/GitHub/Slack/Google tokens, bearer assignments) and reports `file:line` + rule with the value **redacted**; `--staged` for pre-commit. | The release scripts only refuse *tracked* keys; contributors had nothing to catch a pasted token/key *before* committing. |

## Usage

```bash
# from the linux-lab directory
scripts/bonus/env-doctor.sh                      # ./.env vs ./.env.example
scripts/bonus/env-doctor.sh --lab ../win-lab     # any lab that has a .env.example
scripts/bonus/env-doctor.sh --json               # machine-readable

scripts/bonus/port-check.sh                      # WEB_PORT/SSH_PORT from .env
scripts/bonus/port-check.sh 8006 2222 5900       # explicit ports
scripts/bonus/port-check.sh --lab ../win-lab

scripts/bonus/ssh-config-doctor.sh               # ~/.ssh/config
scripts/bonus/ssh-config-doctor.sh --host lab    # one Host block
scripts/bonus/ssh-config-doctor.sh --file ./ssh_config

scripts/bonus/shell-lint.sh linux-lab/scripts    # bash -n (+ shellcheck if present)
scripts/bonus/md-linkcheck.sh linux-lab          # local Markdown links resolve?
scripts/bonus/secret-scan.sh --staged            # scan your staged changes
```

Every tool supports `-h`/`--help`.

## Verify

```bash
# syntax (same check scripts/run-tests.sh runs repo-wide)
bash -n scripts/bonus/*.sh

# env-doctor: a clean copy passes, a broken one fails
cp .env.example /tmp/ok.env
scripts/bonus/env-doctor.sh --env /tmp/ok.env --example .env.example   # [ok], exit 0
printf 'DUP=1\nDUP=2\nEMPTY=\n' >> /tmp/ok.env
scripts/bonus/env-doctor.sh --env /tmp/ok.env --example .env.example   # [fail], exit 1

# port-check: a port nothing listens on is free
scripts/bonus/port-check.sh 65000                                      # [free], exit 0

# ssh-config-doctor: your real config
scripts/bonus/ssh-config-doctor.sh
```
