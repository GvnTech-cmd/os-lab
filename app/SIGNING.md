# Signing the Windows installers

Unsigned installers make Windows SmartScreen warn on first run ("Windows protected your PC").

| | Local `release-win.ps1` | GitHub Actions `release-win` |
|---|---|---|
| Where it builds | your Windows machine | a GitHub-hosted runner (free for public repositories) |
| Signed | no, unless you own a certificate | if SignPath Foundation accepts the project and approves the release |
| SmartScreen | Warns for an unsigned file | Reputation may still need to build after signing |

## Option 1: unsigned, local

```powershell
app\scripts\release-win.ps1 -Publish
```

Publishes `os-lab_<v>_windows_x64-setup.exe` and `.msi` with `.sha256` files to the release `app-v<v>`.
Users click **More info → Run anyway**. Verify a download with the `.sha256` file.

## Option 2: signed, GitHub Actions + SignPath Foundation

[SignPath Foundation](https://signpath.org/) offers publicly trusted code signing to eligible
open-source projects. os-lab is public and Apache-2.0 licensed, but Foundation acceptance is
not guaranteed. Its [terms](https://signpath.org/terms.html) restrict tools that identify or
exploit vulnerabilities; os-lab includes security labs and analysis features, so disclose the
actual functionality during application and ask SignPath to assess eligibility. The private key
stays in SignPath's hardware module, so signing only works from a
pipeline SignPath can trace to this repository. That is why this runs in GitHub Actions and
cannot be done from a laptop.

The workflow [`.github/workflows/release-win.yml`](../.github/workflows/release-win.yml) runs on a
pushed `app-v*` tag, or manually (**Actions → release-win → Run workflow**, tick *publish*). It
builds the installers, submits them to SignPath, checks that each signature is `Valid`, writes the
`.sha256` files and uploads everything to the release.

### One-time setup

1. Review the [Foundation terms](https://signpath.org/terms.html) and apply at
   <https://signpath.org/apply.html>. Describe the Android analysis, reverse-engineering and
   vulnerability-scanning workflows accurately; SignPath decides whether this project qualifies.
   The application and each release signing request require human approval.
2. In SignPath, create the project `os-lab` with a signing policy `release-signing`, and connect it
   to this GitHub repository as a trusted build system. Ensure maintainers and approvers have
   multi-factor authentication on GitHub and SignPath, as the Foundation terms require.
3. In SignPath, create the default **artifact configuration** from
   [`signpath/artifact-configuration.xml`](signpath/artifact-configuration.xml). It restricts
   installer filenames to the requested version and checks the NSIS setup program's product name,
   product version and file version, plus the MSI subject and author. These values were checked
   against the 0.2.5 unsigned CI artifacts. Recheck the metadata if the packaging tool changes.
4. In the GitHub repository settings add:
   - secret `SIGNPATH_API_TOKEN` (a SignPath API token for a CI user)
   - variable `SIGNPATH_ORGANIZATION_ID`
   - optional variables `SIGNPATH_PROJECT_SLUG` (default `os-lab`) and `SIGNPATH_POLICY_SLUG`
     (default `release-signing`)
5. Publish and link the [Code signing policy](../CODE_SIGNING.md) from the project home page and
   each desktop download/release page. The policy identifies reviewers and approvers and links
   the privacy notice. The repository README and future release notes link it; the qrofessor.com
   product download page also needs a link before applying.

Until both `SIGNPATH_ORGANIZATION_ID` and `SIGNPATH_API_TOKEN` are set the workflow builds
**unsigned artifacts for review** but does not publish them from a tag. A manual workflow run
can publish unsigned installers only when
both *publish* and *allow_unsigned* are selected. No certificate or key is ever stored in the
repository.

### Re-signing an existing release

Run the workflow manually on the exact `app-v<v>` tag with *publish* ticked. Uploads use
`--clobber`, so the signed files replace the unsigned ones in that release.
