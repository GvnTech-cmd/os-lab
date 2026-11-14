# PENT-21 verification

Scope guard (`console/scope_guard.py`): the commands below were run on the commit under review and
their output is pasted unedited.

## Environment A: local Windows

- Windows 11, Python 3.12.3, Git Bash
- Commit: `44884755` on `feat/scope-guard`
- Date: 2026-11-12
- The guard only compares the target with the manifest: no host, app or device named below is contacted.

### 1. No scope declared: everything is refused

```console
$ py console/scope_guard.py check host 127.0.0.1
Refused: No lab scope is declared (E:\İleri_Sızma_Vize\os-lab\scope.json does not exist). Copy console/scope.example.json to scope.json, or point $OSLAB_SCOPE_FILE at your manifest, and list only targets you may test
```

Exit code: `2`

A scope is then declared by copying the example manifest: `cp console/scope.example.json scope.json`.

### 2. The declared scope

```console
$ py console/scope_guard.py show
os-lab local lab  (E:\İleri_Sızma_Vize\os-lab\scope.json)
authorization: Replace this: who owns these targets, or who gave you written permission to test them.
expires: 2027-01-31
hosts: 127.0.0.0/8, ::1, localhost, 172.16.0.0/12, *.lab.internal
packages: com.testlab.vulnerable, com.testlab.*
devices: emulator-*, 127.0.0.1:5555
paths: android-lab/lab/artifacts, android-lab/lab/apks
```

Exit code: `0`

### 3. In scope: a lab host

```console
$ py console/scope_guard.py check host 127.0.0.1
In scope: host 127.0.0.1 matches "127.0.0.0/8" in the lab scope "os-lab local lab"
```

Exit code: `0`

### 4. In scope: a lab host given as a URL

```console
$ py console/scope_guard.py check host http://172.20.0.5:8080/api
In scope: host 172.20.0.5 matches "172.16.0.0/12" in the lab scope "os-lab local lab"
```

Exit code: `0`

### 5. In scope: the lab app and the emulator

```console
$ py console/scope_guard.py check package com.testlab.vulnerable && py console/scope_guard.py check device emulator-5554
In scope: app com.testlab.vulnerable matches "com.testlab.vulnerable" in the lab scope "os-lab local lab"
In scope: device emulator-5554 matches "emulator-*" in the lab scope "os-lab local lab"
```

Exit code: `0`

### 6. Refused: a host outside the lab

```console
$ py console/scope_guard.py check host https://www.google.com
Refused: host www.google.com is outside the lab scope "os-lab local lab". Allowed hosts: 127.0.0.0/8, ::1, localhost, 172.16.0.0/12, *.lab.internal. Only test targets you own or are authorized to assess
```

Exit code: `1`

### 7. Refused: a lab name used as URL user info

```console
$ py console/scope_guard.py check host 'http://localhost@evil.com/'
Refused: host evil.com is outside the lab scope "os-lab local lab". Allowed hosts: 127.0.0.0/8, ::1, localhost, 172.16.0.0/12, *.lab.internal. Only test targets you own or are authorized to assess
```

Exit code: `1`

### 8. Refused: an address written as one number

```console
$ py console/scope_guard.py check host 2130706433
Refused: the host is a non-standard numeric address; write it as a dotted IPv4 address
```

Exit code: `1`

### 9. Refused: a file URL passed as a host

```console
$ py console/scope_guard.py check host file://localhost/etc/passwd
Refused: a file URL names a local path, not a network host; check it as a path
```

Exit code: `1`

### 10. Refused: an app that is not a lab app

```console
$ py console/scope_guard.py check package com.whatsapp
Refused: app com.whatsapp is outside the lab scope "os-lab local lab". Allowed packages: com.testlab.vulnerable, com.testlab.*. Only test targets you own or are authorized to assess
```

Exit code: `1`

### 11. Refused: a physical device serial that was not declared

```console
$ py console/scope_guard.py check device R58M12ABCDE
Refused: device R58M12ABCDE is outside the lab scope "os-lab local lab". Allowed devices: emulator-*, 127.0.0.1:5555. Only test targets you own or are authorized to assess
```

Exit code: `1`

### 12. Refused: a path that leaves the lab folders

```console
$ py console/scope_guard.py check path ../outside.txt
Refused: path E:\İleri_Sızma_Vize\outside.txt is outside the lab scope "os-lab local lab". Allowed paths: android-lab/lab/artifacts, android-lab/lab/apks. Only test targets you own or are authorized to assess
```

Exit code: `1`

### 13. Machine-readable decision

```console
$ py console/scope_guard.py check --json host 8.8.8.8
{"allowed": false, "kind": "host", "target": "8.8.8.8", "reason": "Refused: host 8.8.8.8 is outside the lab scope \"os-lab local lab\". Allowed hosts: 127.0.0.0/8, ::1, localhost, 172.16.0.0/12, *.lab.internal. Only test targets you own or are authorized to assess", "rule": null}
```

Exit code: `1`

### 14. Unit and integration tests for the scope guard

```console
$ (cd android-lab/lab && ../../.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider -k scope)
................................................................s....... [ 57%]
.....................................................                    [100%]
124 passed, 1 skipped, 154 deselected in 4.24s
```

Exit code: `0`

### 15. Knowledge graph

```console
$ lat check
Warning: No init version recorded — run lat init to set up agent hooks and configuration.
All checks passed in 331ms
```

Exit code: `0`

## Environment B: Linux (GitHub Codespaces)

- Ubuntu 24.04.5 LTS, Linux 6.8.0-1070-azure x86_64, Python 3.14.2, bash 5.2.21, `lat` 0.13.8
- Commit: `4488475` on `feat/scope-guard`, a fresh codespace of the fork
- Date: 2026-11-12

### 16. The repository test runner

```console
$ ./scripts/run-tests.sh

== Stage 1: android unit tests (pytest) ==
creating test virtualenv at .venv-test ...
..................................................s..................... [ 25%]
.............s.......................................................... [ 51%]
........................................................................ [ 77%]
...............................................................          [100%]
277 passed, 2 skipped in 14.94s
[ok]   android-lab/lab test suite

== Source Lab engine tests (pytest) ==
........................................................................ [ 40%]
........................................................................ [ 81%]
................................                                         [100%]
176 passed in 3.86s
[ok]   source-lab/engine test suite

== Stage 2: android sample analysis pipeline (smoke) ==
Sample APK generated: /workspaces/os-lab/android-lab/lab/scripts/vulnerable-test.apk (1921 bytes)
=== 📱 Comprehensive Android App Analyzer ===
Target: scripts/vulnerable-test.apk
[*] Scanning APK archive directly: scripts/vulnerable-test.apk

Analysis Complete:
  Security Score: 24/100 (Grade: F)
  Vulnerabilities: 6 total
    - Critical : 1
    - High     : 3
    - Medium   : 0
    - Low      : 2
  Hardcoded Secrets: 5

Data saved to: artifacts/security-scan/app-analysis.json
[*] Loading analysis data from JSON: artifacts/security-scan/app-analysis.json
=== 📄 Generating Multi-Format Security Reports ===

Reports Generated Successfully:
  🌐 Interactive HTML : artifacts/security-scan/security-report.html
  📝 Markdown Summary : artifacts/security-scan/security-report.md
  💾 CI/CD JSON Data  : artifacts/security-scan/security-report.json
[ok]   sample analysis + report generated in android-lab/lab/artifacts/security-scan

== Stage 3: shell script syntax (bash -n) ==
[ok]   all 71 shell scripts parse

== Stage 4: lat.md knowledge graph ==
[ok]   lat check

== Stage 5: dashboard (typecheck + committed build is current) ==
[skip] dashboard dependencies not installed (cd dashboard && npm ci) — skipping

== Summary ==
5 passed, 0 failed, 1 skipped
All required checks passed.
```

Exit code: `0`

The two skipped unit tests are not part of this change: `test_jadx_decompiler.py` needs the JADX
binary and one `test_oslab_console.py` test is macOS only.

### 17. Scope guard tests on Linux

```console
$ python -m pytest tests/test_scope_guard.py -q -rs -p no:cacheprovider
........................................................................ [ 59%]
..................................................                       [100%]
122 passed in 0.19s
```

All 122 pass, including the symlink test that is skipped on Windows (step 14), where this account
cannot create symlinks.

### 18. The dashboard stage

Stage 5 above is skipped because a fresh checkout has no `dashboard/node_modules`. After
`npm ci` in `dashboard/` the runner was started again with these results:

- `dashboard typecheck` passes.
- `dashboard/dist is stale` fails. The same check fails on unmodified upstream `master`
  (`ad130c60`): a fresh `astro build` of that commit differs from its committed `dashboard/dist`
  in 477 files, starting with the `contribute-page` bundle. This pull request changes no dashboard
  input, so `dashboard/dist` is left untouched here.
- In that second run one unit test, `tests/test_app_update.py::test_install_downloads_verifies_and_opens`,
  failed once. It passed in the first run, in five reruns of its file and in three further runs of
  the whole suite (277 passed, 2 skipped each time), and it does not touch the scope guard.
