# Code signing policy

os-lab desktop releases are built from this public repository. **The current Windows installers
(0.3.6) are unsigned** — they carry verified updater signatures and per-release build provenance
attestations instead. Verify a download with its `.sha256` file and
`gh attestation verify <file> -R keyvanarasteh/os-lab`; check the Authenticode signature before
relying on any claim that an installer is signed.

Free code signing from [SignPath.io](https://signpath.io), certificate by
[SignPath Foundation](https://signpath.org), was applied for; the Foundation declined the first
application pending broader public visibility and invited a reapplication. The project will
reapply once that evidence exists; until then, Windows installers publish unsigned after an
explicit maintainer approval, with build attestations.

## Roles and approval

- **Committer and reviewer:** [Keyvan Arasteh](https://github.com/keyvanarasteh). A maintainer reviews changes from other contributors before any release is signed.
- **Signing approvers:** [the repository owner](https://github.com/keyvanarasteh), who reviews each release signing request in SignPath. A successful build alone does not approve signing.

The [Windows release workflow](.github/workflows/release-win.yml) builds installers on a GitHub-hosted
runner, submits the uploaded GitHub Actions artifact to SignPath, verifies Authenticode on the returned
files, and computes checksums from those signed bytes. It only publishes automatically after SignPath
credentials are configured and the signing request is approved. Pull request builds remain unsigned.

The [Privacy Notice](docs/legal/PRIVACY.md) describes local data and network connections. The
[install and uninstall guide](app/INSTALL.md) describes how to remove each desktop package.

SignPath Foundation's [terms](https://signpath.org/terms.html) apply to any future signed release.
Acceptance is SignPath Foundation's decision; this policy is not a claim of approval.
