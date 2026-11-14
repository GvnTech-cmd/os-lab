# Source Lab import and publication policy

Source Lab is part of public os-lab and uses the repository's Apache-2.0 license.
The source owner explicitly authorized porting their first-party iQ-SourceContol
code into os-lab on 2026-11-09 after the public distribution and licensing
question was raised. This does not grant rights to other authors' material.

## Included first-party material

Only tracked first-party Python modules, the browser probe, readable synthetic
source fixtures and engine tests are imported from the pinned revision in
[PROVENANCE.json](PROVENANCE.json). The original extraction manifest is retained
as [UPSTREAM-MANIFEST.csv](UPSTREAM-MANIFEST.csv), with CRLF normalized to LF;
it is historical metadata, not
a promise that every listed asset is bundled. Relocated files have full source
and current SHA-256 values in the new provenance manifest.

The core runtime requires Python 3.11+ standard library only. No package, browser,
parser grammar or executable is installed or downloaded by setup or readiness.
Optional tools are operator-installed and remain under their own licenses.

## Exclusions

The port excludes `doc/resources/` in its entirety: upstream archives, datasets,
repository snapshots, cloned code, research media, generated analyses and merged
extensions. It also excludes binaries, packaged applications, databases,
credentials, environment files, local caches, deployment registrations and live
service configuration. Tests construct binary parser samples in temporary
folders instead of committing executable or proprietary fixtures.

User-provided targets and catalogs stay on the operator's machine. Default
outputs are gitignored; only the explicitly reviewed synthetic fixtures belong
in the repository. Do not copy private reports into screenshots or public Pages.
New UI dependencies and assets require their own license/provenance review.

The integration also derives manifest migration annotations and Pipeline
architecture metadata from the owner's pinned UI source. These two code-owned
references are recorded in PROVENANCE.json. Dashboard views are adapted to the
existing shell; no private Brain export or external source catalog is bundled.

## Review before each commit

Review the actual staged diff against `CONTRIBUTING.md`, `SECURITY.md` and all
four documents in `docs/legal/`. Confirm the paths above remain excluded, inspect
new strings and fixtures for credentials/personal data, verify attributions and
provenance, and ensure stored data and intentional network actions are described
accurately. Run relevant tests and `lat check`; record commands and limitations
in the PR. Do not mark unimplemented capabilities complete or weaken the existing
localhost/request protections to accommodate a port.

This policy describes contribution handling; it does not add conditions to the
Apache license. Operator use remains subject to the existing acceptable-use,
privacy and software-license notices.
