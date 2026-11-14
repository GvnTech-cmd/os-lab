# PENT-21 report: Authorization & Scope-Guard Library

- **Course / task:** MYO062 midterm, roadmap task PENT-21
- **Student:** Mahmut Çirka · 2520191026 ([@mahmutcirka](https://github.com/mahmutcirka))
- **Pull request:** [#128](https://github.com/keyvanarasteh/os-lab/pull/128) · reservation [#127](https://github.com/keyvanarasteh/os-lab/pull/127)
- **Verification:** [VERIFY.md](VERIFY.md)
- **Proof video:** linked in the pull request description (2 min 12 s, not committed)

## What the task asked for

A shared guard that lab tools import to assert that a target (host, package, path, device) is inside
the declared lab scope, refusing with a clear reason otherwise, plus unit tests for allow and deny of
hosts, packages and device serials. It puts the course rule "no testing without authorization, lab
targets only" into code.

## What was built

| File | Purpose |
|---|---|
| `console/scope_guard.py` | Scope-manifest loader, `check()`, `assert_in_scope()`, `scope_status()` and a command line |
| `console/scope.example.json` | Starting manifest; the operator copies it to `scope.json` (git-ignored) |
| `console/oslab.py`, `android-lab/lab/web_ui.py` | Read-only `scope_status()` and `GET /api/scope` so the console can show the declared scope |
| `android-lab/lab/tests/test_scope_guard.py` | Tests for hosts, packages, devices, paths, manifests and the command line |
| `lat.md/tooling.md` | "Scope guard" section of the knowledge graph |

A tool calls `scope_guard.assert_in_scope("host", "10.25.130.14")`. It gets back a decision naming
the manifest rule that allowed the target, or a `ScopeError` whose message says why it was refused.
The module uses only the Python standard library, never resolves DNS and never opens a connection.

## Design decisions

- **Fail closed.** No manifest, an unreadable, invalid or expired manifest, an unknown target kind
  and a malformed target are all refusals. A broken configuration can never widen the scope.
- **A scope must name its targets.** `*`, `0.0.0.0/0`, `*.com` and `com.*` are rejected when the
  manifest is loaded. Public address ranges need an explicit `allowPublic`, and every manifest must
  state who authorized the testing.
- **Only the host part of a target is matched.** `host:port` and URLs are accepted, but URL user
  info (`http://localhost@evil.com/`), `inet_aton` spellings (`127.1`, `2130706433`), non-ASCII
  look-alike names, `file:` URLs and addresses with an interface zone are refused, because each can
  make a tool contact something other than what the check appeared to approve.
- **Nothing is trimmed or repaired.** Control characters and surrounding whitespace are refused,
  since the tool would use the raw value and not a cleaned-up copy.
- **Paths are resolved the way the operating system opens them**, with links followed, so `..`,
  a sibling folder with the same name prefix and a link that leaves the lab folder are refused.

## Review feedback

The automated review on the pull request raised ten points. Eight were fixed with tests in commit
`4488475` (whitespace-padded targets, `file:` URLs, interface zones and brackets, CIDR entries with
host bits, IPv4-mapped rules, bounded manifest reads, deep nesting, duplicate fields). Two are
documented instead: a link swapped in between the check and the tool's own `open()` cannot be
prevented by a check-only library, and absolute folders in the manifest are intended because the
manifest is the operator's own declaration.

## Limitations

- Host names are matched as text. A tool that connects by name should also check the address it
  resolved.
- A decision describes the target at the moment of the check; tools should use the normalized
  target the decision returns.
- No existing lab tool calls the guard yet. This change provides the library and shows the declared
  scope in the console; wiring it into individual tools belongs to their own tasks (for example
  PENT-20).

## AI use

The code, tests and documentation in this pull request were written with the help of Claude Code;
the commits carry a `Co-Authored-By` line. I chose the task and reviewed each change before it was
pushed. The test runs recorded in [VERIFY.md](VERIFY.md) were done on my own machine and in a
GitHub codespace of my fork. The proof video records a small script, written with the same help,
that types each command and runs it for real on my machine; the recording is not edited afterwards.
