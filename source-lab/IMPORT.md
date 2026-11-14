# Opt-in legacy analysis import

Import only first-party artifacts or material you are authorized to process.
No original is moved, deleted or rewritten. This command never copies an entire
project, workspace or resource tree and makes no network requests.

The input is an explicit legacy **analysis directory** containing selected
`owner__repo/` folders. Root relocation maps those folders into private
`SOURCE_LAB_STORAGE/analysis/`; embedded source paths remain original forensic
metadata and are not rewritten. Workspaces/targets must be supplied separately.

```bash
# Inspect file counts, source/destination paths, hashes, sessions and exclusions.
./labctl source import-legacy --source /path/to/owned/analysis --slug owner__repo

# After reviewing the dry-run JSON, use its exact fingerprint.
./labctl source import-legacy --source /path/to/owned/analysis --slug owner__repo \
  --copy --authorized --expected-plan FINGERPRINT

# Inspect rollback, then confirm its fingerprint. Originals remain untouched.
./labctl source import-legacy --rollback IMPORT_ID
./labctl source import-legacy --rollback IMPORT_ID \
  --copy --authorized --expected-plan ROLLBACK_FINGERPRINT
```

On Windows use `python source-lab/run.py import-legacy ...`. The command requires
Python 3.11+ and no Node/database/browser tooling. `--authorized` is an operator
attestation for the selected local artifacts; it is not a redistribution licence.

Allowed inputs are known JSON findings/coverage/manifest/dependency/file-tree/map/
metadata reports, indexed AST JSON, Markdown/SARIF/STIX reports, and complete
signed sessions with text/JSON artifacts. Unsupported evidence/map versions fail.
Limits: 5 MB per file, 64 MB per import, 1,000 imported files and bounded directory
entries. Unknown files are listed as excluded; symlinks/special files are refused.
Archives, datasets/catalogs, application binaries, databases, Skills, `.env`, keys,
credentials/configuration trees and deployment files are never copied.

Sessions require a valid original signing key in the operator environment or
already managed destination storage. No key is imported. Hashes and HMAC must
verify, and all members must be signed. A session containing private browser
state or binary attachments is held out as a whole; deleting members would break
its integrity. Existing destination session IDs cannot be overwritten. Legacy
Windows manifest newlines are supported without accepting changed file hashes.

`--settings /path/to/runtime-settings.json` can additionally import only
`{"testUrl":"https://example.test"}`. Credential-bearing URLs and all other
settings fields are rejected. No request is made to that URL.

Copying shares the Source job lock, rechecks source/destination hashes, writes
atomically with private file modes where supported, and journals each replacement
before applying it. Existing reports/settings are backed up under
`control/import-backups/<id>/`; journals are `control/imports/<id>.json`. Both
remain private until the operator removes them. Rollback retains the journal and
backups; it restores only files still matching the imported hashes and refuses
newer edits before changing anything. Copy failures attempt automatic rollback.
After process interruption, preview rollback by journal ID before retrying.
Storage failures may require restoring free space/permissions first. Rollback
removes imported files, but can leave empty directories. Never delete the backup
or journal while you still need rollback.
