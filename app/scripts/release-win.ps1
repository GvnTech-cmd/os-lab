<#
.SYNOPSIS
  Build and (optionally) publish the os-lab Windows app: an NSIS setup .exe and a WiX .msi.

.DESCRIPTION
  app\scripts\release-win.ps1             build + verify, upload nothing
  app\scripts\release-win.ps1 -Publish    ...and add them to the GitHub release app-v<version>
  app\scripts\release-win.ps1 -NoSign     skip Authenticode even if a certificate is configured
  app\scripts\release-win.ps1 -SmokeInstall  install the setup .exe for the current user, launch it
                                          and uninstall it; fail unless every step is per-user

  Authenticode signing is optional. Tauri updater signing is required for builds. A Windows
  Authenticode certificate is used when one is found, in this order:
    1. $env:OSLAB_WIN_CERT_THUMBPRINT (a certificate already in the user's store)
    2. secrets\windows\thumbprint.txt
    3. secrets\windows\os-lab.pfx + os-lab.pfx.password (imported into the user's store)
  Without one the installers are unsigned and SmartScreen warns on first run. Timestamp server:
  $env:OSLAB_WIN_TIMESTAMP_URL or secrets\windows\timestamp-url.txt (default http://timestamp.digicert.com).

  Credentials never live in the repository (see secrets\README.md). The script prints which source it
  used, never a value, and refuses to run if anything under secrets\ (besides the README) or any key
  file is tracked by git. -Publish uses the gh CLI when it is logged in, otherwise the credential that
  git already stores for pushes (like qLar's publish-release.ps1).
#>
[CmdletBinding()]
param(
  [switch]$Publish,
  [switch]$NoSign,
  [switch]$SmokeInstall
)
$ErrorActionPreference = 'Stop'

$AppDir = Split-Path -Parent $PSScriptRoot
$Repo = Split-Path -Parent $AppDir
$Slug = 'keyvanarasteh/os-lab'

function Say($m) { Write-Host "==> $m" }
function Die($m) { Write-Error "error: $m"; exit 1 }
function Need($cmd) { if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { Die "$cmd not found" } }
function Run($exe, [string[]]$a) { & $exe @a; if ($LASTEXITCODE -ne 0) { Die "$exe $($a -join ' ') failed ($LASTEXITCODE)" } }

# The setup .exe is built for the current user only (installMode "currentUser" in tauri.conf.json),
# so it must install under %LOCALAPPDATA% and HKCU without elevation, and remove both on uninstall.
# Refuses to run when an install already exists, so an existing copy is never touched.
function Test-CurrentUserInstall($Setup) {
  # Ask Windows for the folder instead of reading %LOCALAPPDATA%, which is missing in some shells.
  $localAppData = [Environment]::GetFolderPath('LocalApplicationData')
  if (-not $localAppData) { Die 'could not resolve the per-user local app data folder' }
  $installDir = Join-Path $localAppData 'os-lab'
  $exe = Join-Path $installDir 'os-lab-app.exe'
  $userKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\os-lab'
  $machineKey = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\os-lab'
  # Tauri's MSI reads this value to reuse a previous NSIS install directory (see installer-hooks.nsh).
  $reuseKey = 'HKCU:\Software\Keyvan Arasteh\os-lab'
  foreach ($present in @($installDir, $userKey)) {
    if (Test-Path $present) { Die "a per-user os-lab install already exists ($present); remove it before -SmokeInstall" }
  }
  Say "installing for the current user only: $Setup"
  # /NS skips the Start menu and desktop shortcuts, so the check leaves the profile as it found it.
  $install = Start-Process $Setup -ArgumentList '/S', '/NS' -Wait -PassThru
  if ($install.ExitCode -ne 0) { Die "per-user install failed ($($install.ExitCode))" }
  $problem = $null
  try {
    if (-not (Test-Path $exe)) { throw "the installer did not create $exe" }
    if (-not (Test-Path $userKey)) { throw 'no HKCU uninstall entry: the install is not recorded for the current user' }
    if (Test-Path $machineKey) { throw 'an HKLM uninstall entry appeared: the install is not per-user' }
    Say "installed per-user: $exe (HKCU entry, no HKLM entry)"
    $app = Start-Process $exe -PassThru
    Start-Sleep -Seconds 10
    if ($app.HasExited) { throw "the installed app exited early ($($app.ExitCode))" }
    Stop-Process -Id $app.Id -Force
    Say 'the installed app launched and stayed up'
  } catch { $problem = $_.Exception.Message } finally {
    $uninstaller = Join-Path $installDir 'uninstall.exe'
    if (Test-Path $uninstaller) {
      $null = Start-Process $uninstaller -ArgumentList '/S' -Wait -PassThru
      for ($i = 0; $i -lt 30 -and (Test-Path $installDir); $i++) { Start-Sleep -Milliseconds 500 }
      if (Test-Path $installDir) {
        if (-not $problem) { $problem = "the uninstaller left $installDir behind" }
      }
      if (Test-Path $userKey) {
        if (-not $problem) { $problem = 'the uninstaller left the HKCU uninstall entry behind' }
      }
      $reuse = (Get-ItemProperty $reuseKey -Name '(default)' -ErrorAction SilentlyContinue).'(default)'
      if ($reuse) {
        if (-not $problem) { $problem = "the uninstaller left its install path in $reuseKey" }
      }
      if (-not $problem) { Say 'uninstalled cleanly' }
    }
  }
  if ($problem) { Die "per-user install check failed: $problem" }
}

if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') { Die 'Windows only (WiX builds the .msi on Windows)' }
foreach ($c in 'node', 'npm', 'cargo', 'git', 'tar') { Need $c }

$Version = (& node -p "require('$($AppDir -replace '\\','/')/src-tauri/tauri.conf.json').version").Trim()
$Tag = "app-v$Version"
$Out = Join-Path $AppDir "out\$Version"

# 1. Secrets must never be tracked --------------------------------------------------------------
$tracked = @(git -C $Repo ls-files -- secrets | Where-Object { $_ -ne 'secrets/README.md' })
if ($tracked.Count) { Die "tracked files under secrets/ (remove them from git, rotate the keys):`n$($tracked -join "`n")" }
$keys = @(git -C $Repo ls-files -- '*.p8' '*.p12' '*.pfx' '*.pem' '*.key')
if ($keys.Count) { Die 'a key or certificate file is tracked by git' }

# 2. Optional Authenticode certificate ----------------------------------------------------------
$SecretsDir = if ($env:OSLAB_SECRETS_WIN_DIR) { $env:OSLAB_SECRETS_WIN_DIR } else { Join-Path $Repo 'secrets\windows' }
$Thumbprint = $null; $ThumbSource = $null
if (-not $NoSign) {
  if ($env:OSLAB_WIN_CERT_THUMBPRINT) {
    $Thumbprint = $env:OSLAB_WIN_CERT_THUMBPRINT; $ThumbSource = 'environment'
  } elseif (Test-Path (Join-Path $SecretsDir 'thumbprint.txt')) {
    $Thumbprint = (Get-Content -Raw (Join-Path $SecretsDir 'thumbprint.txt')).Trim(); $ThumbSource = 'secrets folder (thumbprint.txt)'
  } elseif (Test-Path (Join-Path $SecretsDir 'os-lab.pfx')) {
    $pw = Join-Path $SecretsDir 'os-lab.pfx.password'
    if (-not (Test-Path $pw)) { Die 'os-lab.pfx found without os-lab.pfx.password' }
    $secure = ConvertTo-SecureString (Get-Content -Raw $pw).Trim() -AsPlainText -Force
    $cert = Import-PfxCertificate -FilePath (Join-Path $SecretsDir 'os-lab.pfx') -CertStoreLocation Cert:\CurrentUser\My -Password $secure
    $Thumbprint = $cert.Thumbprint; $ThumbSource = 'secrets folder (os-lab.pfx, imported)'
  }
}
if ($Thumbprint) {
  $Thumbprint = ($Thumbprint -replace '\s', '').ToUpper()
  if (-not (Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My -ErrorAction SilentlyContinue | Where-Object Thumbprint -eq $Thumbprint)) {
    Die "no certificate with thumbprint $Thumbprint in the user or machine store"
  }
}
$TimestampUrl = $env:OSLAB_WIN_TIMESTAMP_URL
if (-not $TimestampUrl -and (Test-Path (Join-Path $SecretsDir 'timestamp-url.txt'))) { $TimestampUrl = (Get-Content -Raw (Join-Path $SecretsDir 'timestamp-url.txt')).Trim() }
if (-not $TimestampUrl) { $TimestampUrl = 'http://timestamp.digicert.com' }

Say "version $Version, tag $Tag"
if ($Thumbprint) { Say "Authenticode: certificate $Thumbprint from $ThumbSource, timestamp $TimestampUrl" }
else { Say 'Authenticode: not configured, the installers will be unsigned (SmartScreen will warn)' }

# 3. Build --------------------------------------------------------------------------------------
Set-Location $AppDir
Say 'installing build tools'
Run 'npm' @('ci', '--no-audit', '--no-fund')
Say 'installing dashboard build tools'
Run 'npm' @('ci', '--no-audit', '--no-fund', '--prefix', (Join-Path $Repo 'dashboard'))
Say 'staging the runtime and dashboard'
Run 'node' @('scripts/stage-runtime.mjs')
Run 'node' @('scripts/stage-python-helper.mjs')
if (-not $env:TAURI_SIGNING_PRIVATE_KEY) {
  $updaterKey = Join-Path $Repo 'secrets\updater\os-lab.key'
  if (Test-Path $updaterKey) { $env:TAURI_SIGNING_PRIVATE_KEY = Get-Content -Raw $updaterKey }
}
if (-not $env:TAURI_SIGNING_PRIVATE_KEY) { Die 'updater signing key is missing (TAURI_SIGNING_PRIVATE_KEY)' }

$tauriArgs = @('tauri', 'build', '--bundles', 'nsis,msi')
$overlay = $null
if ($Thumbprint) {
  # A throwaway --config overlay (never committed) tells Tauri which certificate to sign with.
  $overlay = Join-Path ([IO.Path]::GetTempPath()) "os-lab-sign-$PID.json"
  @{ bundle = @{ windows = @{ certificateThumbprint = $Thumbprint; digestAlgorithm = 'sha256'; timestampUrl = $TimestampUrl } } } |
    ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $overlay
  $tauriArgs += @('--config', $overlay)
}
Say 'building the NSIS and MSI installers'
try { Run 'npx' $tauriArgs } finally { if ($overlay) { Remove-Item -Force $overlay -ErrorAction SilentlyContinue } }

$bundle = Join-Path $AppDir 'src-tauri\target\release\bundle'
$nsis = Get-ChildItem (Join-Path $bundle 'nsis') -Filter "*_${Version}_*-setup.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
$msi = Get-ChildItem (Join-Path $bundle 'msi') -Filter "*_${Version}_*.msi" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $nsis -or -not $msi) { Die "build produced no $Version setup .exe and .msi under $bundle" }

# 4. Verify what will ship ----------------------------------------------------------------------
Say 'verifying'
foreach ($f in @($nsis, $msi)) {
  $sig = Get-AuthenticodeSignature $f.FullName
  if ($Thumbprint) {
    if ($sig.Status -ne 'Valid') { Die "$($f.Name): Authenticode status is $($sig.Status), expected Valid" }
    Say "$($f.Name): signed by $($sig.SignerCertificate.Subject)"
  } else {
    Say "$($f.Name): unsigned"
  }
}

# 5. Collect ------------------------------------------------------------------------------------
New-Item -ItemType Directory -Force $Out | Out-Null
$assets = @(
  @{ Src = $nsis.FullName; Name = "os-lab_${Version}_windows_x64-setup.exe" },
  @{ Src = $msi.FullName; Name = "os-lab_${Version}_windows_x64.msi" }
)
$utf8 = New-Object Text.UTF8Encoding($false)   # no BOM, so `sha256sum -c` reads it elsewhere
$files = @()
foreach ($a in $assets) {
  $dest = Join-Path $Out $a.Name
  Copy-Item -Force $a.Src $dest
  $hash = (Get-FileHash -Algorithm SHA256 $dest).Hash.ToLower()
  [IO.File]::WriteAllText("$dest.sha256", "$hash  $($a.Name)`n", $utf8)
  Say "ready: $dest"
  Write-Host "$hash  $($a.Name)"
  $files += $dest, "$dest.sha256"
  if (-not (Test-Path "$($a.Src).sig")) { Die "updater signature is missing for $($a.Src)" }
  Copy-Item -Force "$($a.Src).sig" "$dest.sig"
  $files += "$dest.sig"
}

# 5. Per-user install check (opt-in) ------------------------------------------------------------
# Runs before publishing so a broken or per-machine setup .exe cannot reach a release.
if ($SmokeInstall) { Test-CurrentUserInstall (Join-Path $Out "os-lab_${Version}_windows_x64-setup.exe") }

# 6. Publish ------------------------------------------------------------------------------------
if (-not $Publish) { Say 'dry run: nothing uploaded (use -Publish)'; exit 0 }

$notes = "os-lab desktop app $Version. One installer per platform, each with a .sha256 file. The app can download managed Python on request."
# gh writes to stderr for 'not logged in' and 'release not found'; that must not abort under Stop.
$ErrorActionPreference = 'Continue'
if (Get-Command gh -ErrorAction SilentlyContinue) { & gh auth status 2>$null | Out-Null; $haveGh = ($LASTEXITCODE -eq 0) } else { $haveGh = $false }

if ($haveGh) {
  & gh release view $Tag -R $Slug 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) {
    Say "adding to release $Tag"
    Run 'gh' (@('release', 'upload', $Tag) + $files + @('--clobber', '-R', $Slug))
  } else {
    Say "creating release $Tag"
    Run 'gh' (@('release', 'create', $Tag) + $files + @('-R', $Slug, '--title', "os-lab app $Version", '--notes', $notes))
  }
} else {
  # Fall back to the credential git stores for pushes; never printed.
  $credLines = "url=https://github.com/$Slug`n`n" | git credential fill 2>$null
  $token = ($credLines | Where-Object { $_ -match '^password=' }) -replace '^password=', ''
  if (-not $token) { Die 'neither a logged-in gh CLI nor a stored GitHub credential was found' }
  $ErrorActionPreference = 'Stop'
  $h = @{ Authorization = "Bearer $token"; Accept = 'application/vnd.github+json'; 'X-GitHub-Api-Version' = '2022-11-28' }
  try { $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$Slug/releases/tags/$Tag" -Headers $h }
  catch {
    Say "creating release $Tag"
    $payload = @{ tag_name = $Tag; name = "os-lab app $Version"; body = $notes; draft = $false; prerelease = $false } | ConvertTo-Json
    $rel = Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$Slug/releases" -Headers $h `
      -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($payload))
  }
  foreach ($f in $files) {
    $name = Split-Path -Leaf $f
    $old = $rel.assets | Where-Object name -eq $name
    if ($old) { Invoke-RestMethod -Method Delete -Uri "https://api.github.com/repos/$Slug/releases/assets/$($old.id)" -Headers $h | Out-Null }
    Invoke-RestMethod -Method Post -Uri "https://uploads.github.com/repos/$Slug/releases/$($rel.id)/assets?name=$([uri]::EscapeDataString($name))" `
      -Headers $h -ContentType 'application/octet-stream' -InFile $f | Out-Null
    Say "uploaded $name"
  }
}
Say "published: https://github.com/$Slug/releases/tag/$Tag"
