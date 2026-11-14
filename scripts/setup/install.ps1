#Requires -Version 5.1
<#
.SYNOPSIS
  os-lab one-command setup - Windows (PowerShell)

.DESCRIPTION
  Detects the host, reports device status, installs prerequisites via winget
  (or Chocolatey), fetches or updates the os-lab checkout, provisions a Python
  virtualenv, and launches the web console (PWA UI). Safe to run repeatedly.

.EXAMPLE
  # Remote one-liner (PowerShell):
  irm https://raw.githubusercontent.com/keyvanarasteh/os-lab/master/scripts/setup/install.ps1 | iex

.EXAMPLE
  # From a checkout:
  .\scripts\setup\install.ps1

.PARAMETER Dir        Install/checkout directory (default: $HOME\os-lab)
.PARAMETER Branch     Git branch to track (default: master)
.PARAMETER Port       Web console port (default: 5050)
.PARAMETER ReportOnly Detect + report only; change nothing
.PARAMETER NoInstall  Do not install prerequisites
.PARAMETER NoRun      Set up but do not launch the web console
.PARAMETER Minimal    Virtualenv for the UI only (skip heavy tool deps)
.PARAMETER Update     Pull latest even if the checkout already exists
#>
[CmdletBinding()]
param(
  [string]$Dir    = "$HOME\os-lab",
  [string]$Branch = "master",
  [int]   $Port   = 5050,
  [switch]$ReportOnly,
  [switch]$NoInstall,
  [switch]$NoRun,
  [switch]$Minimal,
  [switch]$Update
)

$ErrorActionPreference = 'Stop'
$Repo = if ($env:OSLAB_REPO) { $env:OSLAB_REPO } else { 'https://github.com/keyvanarasteh/os-lab.git' }
if ($env:OSLAB_DIR)    { $Dir    = $env:OSLAB_DIR }
if ($env:OSLAB_BRANCH) { $Branch = $env:OSLAB_BRANCH }
if ($env:OSLAB_PORT)   { $Port   = [int]$env:OSLAB_PORT }

function Info($m) { Write-Host "==> " -ForegroundColor Green -NoNewline; Write-Host $m }
function Step($m) { Write-Host " -- " -ForegroundColor Cyan  -NoNewline; Write-Host $m }
function Warn($m) { Write-Host "warning: " -ForegroundColor Yellow -NoNewline; Write-Host $m }
function Die($m)  { Write-Host "error: " -ForegroundColor Red -NoNewline; Write-Host $m; exit 1 }
function Ok($m)   { Write-Host "   ok   " -ForegroundColor Green -NoNewline; Write-Host $m }
function Miss($m) { Write-Host "   miss " -ForegroundColor Red -NoNewline; Write-Host $m }
function Hr()     { Write-Host ("-" * 60) }

function Have($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

# Resolve a REAL python interpreter, skipping the Windows Store execution alias
# (a 0-byte stub under ...\WindowsApps that just opens the Store). Returns the
# usable path, or $null when only the alias / nothing is present.
function Get-PythonExe {
  foreach ($name in @('python','python3')) {
    foreach ($c in @(Get-Command $name -All -ErrorAction SilentlyContinue)) {
      $src = $c.Source
      if (-not $src) { continue }
      if ($src -like '*\WindowsApps\*') { continue }   # Store alias stub
      try { & $src --version *> $null; if ($LASTEXITCODE -eq 0) { return $src } } catch {}
    }
  }
  return $null
}

function Banner {
  Write-Host @'
   ___  ____    _          _
  / _ \/ ___|  | |    __ _| |__
 | | | \___ \  | |   / _` | '_ \
 | |_| |___) | | |__| (_| | |_) |
  \___/|____/  |_____\__,_|_.__/   one-command setup - Windows
'@ -ForegroundColor White
}

function Report-Tool($label, $bin, [scriptblock]$verCmd) {
  $cmd = Get-Command $bin -ErrorAction SilentlyContinue
  if ($cmd) {
    $v = ""
    try { $v = (& $verCmd 2>&1 | Select-Object -First 1) } catch { $v = "" }
    Write-Host "   ok   " -ForegroundColor Green -NoNewline
    "{0,-16}{1}  {2}" -f $label, $v, $cmd.Source | Write-Host
    return $true
  }
  Write-Host "   miss " -ForegroundColor Red -NoNewline
  "{0,-16}not found" -f $label | Write-Host
  return $false
}

function Print-Report {
  $os   = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
  $cpu  = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1
  $cores = if ($cpu) { $cpu.NumberOfLogicalProcessors } else { "?" }
  $ramGb = if ($os) { "{0:N1} GiB" -f ($os.TotalVisibleMemorySize / 1MB) } else { "?" }
  $sys  = $env:SystemDrive
  $free = try { $d = Get-PSDrive ($sys.TrimEnd(':')) -ErrorAction Stop; "{0:N1} GiB free of {1:N1} GiB" -f ($d.Free/1GB), (($d.Free+$d.Used)/1GB) } catch { "?" }
  $arch = $env:PROCESSOR_ARCHITECTURE

  # Virtualization providers
  $hyperv = "unknown"
  try {
    $f = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -ErrorAction SilentlyContinue
    if ($f) { $hyperv = $f.State }
  } catch {}
  $wsl = if (Have wsl) { "installed" } else { "not installed" }

  Hr; Info "Host & device report"; Hr
  "   {0,-16}{1}" -f "OS", (if ($os) { "$($os.Caption) ($arch)" } else { "Windows ($arch)" }) | Write-Host
  "   {0,-16}{1}" -f "Provider", "native-windows" | Write-Host
  "   {0,-16}{1}" -f "Hyper-V", $hyperv | Write-Host
  "   {0,-16}{1}" -f "WSL2", $wsl | Write-Host
  "   {0,-16}{1}" -f "CPU cores", $cores | Write-Host
  "   {0,-16}{1}" -f "Memory", $ramGb | Write-Host
  "   {0,-16}{1}" -f "Disk", $free | Write-Host
  Hr; Info "Host tools"; Hr
  Report-Tool "git"     "git"    { git --version } | Out-Null
  Report-Tool "python"  "python" { python --version } | Out-Null
  Report-Tool "pip"     "pip"    { pip --version } | Out-Null
  Report-Tool "docker"  "docker" { docker --version } | Out-Null
  if (Have docker) { try { $c = docker compose version 2>&1 | Select-Object -First 1; Ok ("compose         {0}" -f $c) } catch {} }
  Report-Tool "adb"     "adb"    { adb --version } | Out-Null
  Report-Tool "java"    "java"   { java -version } | Out-Null
  Report-Tool "node"    "node"   { node --version } | Out-Null
  Hr
}

function Ensure-Prereqs {
  $useWinget = Have winget
  $useChoco  = Have choco
  if (-not $useWinget -and -not $useChoco) {
    Warn "Neither winget nor Chocolatey found."
    if ((Have git) -and (Have python)) { Ok "git and python already present; continuing"; return }
    Die "git and/or python missing and no package manager available. Install winget (App Installer) or Chocolatey."
  }
  $want = @()
  if (-not (Have git))     { $want += "git" }
  if (-not (Get-PythonExe)) { $want += "python" }
  if ($want.Count -eq 0) { Ok "all core prerequisites already present"; return }
  Step ("installing: {0}" -f ($want -join ", "))
  foreach ($pkg in $want) {
    try {
      if ($useWinget) {
        $id = if ($pkg -eq "git") { "Git.Git" } elseif ($pkg -eq "python") { "Python.Python.3.12" } else { $pkg }
        winget install --accept-source-agreements --accept-package-agreements -e --id $id | Out-Null
      } else {
        choco install -y $pkg | Out-Null
      }
    } catch { Warn "failed to install $pkg; continuing" }
  }
  # refresh PATH for this session
  $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
}

$script:RepoRoot = ""
$script:Cloned = $false
function Locate-OrClone {
  $here = try { (git rev-parse --show-toplevel 2>$null) } catch { "" }
  if ($here) { $here = $here -replace '/', '\' }
  if ($here -and (Test-Path (Join-Path $here "labctl")) -and (Test-Path (Join-Path $here "android-lab"))) {
    $script:RepoRoot = $here; Step "using existing checkout: $here"
  } elseif (Test-Path (Join-Path $Dir ".git")) {
    $script:RepoRoot = $Dir; Step "found checkout: $Dir"
  } else {
    Step "cloning $Repo -> $Dir"
    if (-not (Have git)) { Die "git is required to clone" }
    git clone --branch $Branch $Repo $Dir
    if ($LASTEXITCODE -ne 0) { Die "git clone failed" }
    $script:RepoRoot = $Dir; $script:Cloned = $true; return
  }
  # Update only a fresh clone or when -Update is explicit; never switch branches.
  if ($script:Cloned -or $Update) {
    $cur = (git -C $script:RepoRoot rev-parse --abbrev-ref HEAD 2>$null)
    Step "updating checkout (branch: $cur)"
    git -C $script:RepoRoot fetch --quiet origin $cur 2>$null
    $dirty = (git -C $script:RepoRoot status --porcelain)
    if (-not $dirty) {
      git -C $script:RepoRoot pull --quiet --ff-only origin $cur 2>$null
      if ($LASTEXITCODE -eq 0) { Ok ("updated to " + (git -C $script:RepoRoot rev-parse --short HEAD)) }
      else { Warn "could not fast-forward; leaving checkout as-is" }
    } else { Warn "local changes present; skipping auto-update" }
  }
}

function Provision-Venv {
  $venv = Join-Path $script:RepoRoot ".venv"
  $req  = Join-Path $script:RepoRoot "android-lab\lab\requirements.txt"
  $pyExe = Get-PythonExe
  if (-not $pyExe) { Die "no real Python interpreter found (only the Store alias?); install Python and re-run" }
  if (-not (Test-Path $venv)) {
    Step "creating virtualenv: $venv"
    & $pyExe -m venv $venv
    if ($LASTEXITCODE -ne 0) { Die "failed to create virtualenv" }
  } else { Step "reusing virtualenv: $venv" }
  $py = Join-Path $venv "Scripts\python.exe"
  if ($Minimal) {
    Ok "minimal mode - web console runs on the standard library, no extra deps"
    & $py (Join-Path $script:RepoRoot "source-lab\run.py") doctor
    if ($LASTEXITCODE -ne 0) { Warn "Source Lab needs Python 3.11+ and writable private storage" }
  } elseif (Test-Path $req) {
    & $py -m pip install --quiet --upgrade pip wheel 2>$null
    Step "installing tool dependencies (this can take a few minutes)"
    & $py -m pip install --quiet -r $req
    if ($LASTEXITCODE -eq 0) { Ok "tool dependencies installed" }
    else { Warn "some dependencies failed to build; the web console still runs. Re-run with -Minimal to skip." }
  } else { Warn "requirements.txt not found at $req; skipping" }
}

# Dashboard (Astro): rebuild locally when Node 22+ is present, else use the committed
# build in dashboard\dist. Local builds go to the untracked dashboard\build so they never
# dirty the checkout; the console serves whichever build is newer.
function Build-Dashboard {
  $dir = Join-Path $script:RepoRoot "dashboard"
  if (-not (Test-Path (Join-Path $dir "package.json"))) { return }
  $prebuilt = if (Test-Path (Join-Path $dir "dist\index.html")) { "prebuilt dashboard (dashboard\dist)" } else { "classic console (no dashboard build found)" }
  if ($Minimal -or $env:OSLAB_DASHBOARD_BUILD -eq "0") { Ok "dashboard: using the $prebuilt"; return }
  $major = 0
  if (Have "node") { try { $major = [int](& node -p "process.versions.node.split('.')[0]") } catch { $major = 0 } }
  if (-not (Have "npm") -or $major -lt 22) { Ok "dashboard: Node.js 22+ not found, using the $prebuilt"; return }
  Step "building the dashboard with Node $(& node --version) (set OSLAB_DASHBOARD_BUILD=0 to skip)"
  Push-Location $dir
  try {
    & npm ci --no-audit --no-fund *> $null
    if ($LASTEXITCODE -ne 0) { & npm install --no-audit --no-fund *> $null }
    if ($LASTEXITCODE -eq 0) { & npm run --silent build:local *> $null }
    if ($LASTEXITCODE -eq 0) { Ok "dashboard built -> dashboard\build" }
    else { Warn "dashboard build failed; using the $prebuilt" }
  } finally { Pop-Location }
}

function Launch-Ui {
  $orch = Join-Path $script:RepoRoot "android-lab\lab\orchestrator.py"
  $py   = Join-Path $script:RepoRoot ".venv\Scripts\python.exe"
  $url  = "http://127.0.0.1:$Port"
  if (-not (Test-Path $orch)) { Die "web console entrypoint missing: $orch" }
  Info "Launching os-lab web console -> $url"
  Step "press Ctrl+C to stop"
  Start-Process $url | Out-Null
  & $py $orch ui --port $Port
}

Banner
Print-Report
if ($ReportOnly) { Info "report-only: no changes made"; exit 0 }
if (-not $NoInstall) { Info "Checking prerequisites"; Ensure-Prereqs }
Info "Fetching os-lab"; Locate-OrClone
Info "Provisioning Python environment"; Provision-Venv
Info "Preparing the dashboard"; Build-Dashboard
if (-not $NoRun) {
  Launch-Ui
} else {
  Hr
  Ok "setup complete - checkout at $script:RepoRoot"
  Write-Host "   start the console later with:"
  Write-Host ("     cd {0}; .\.venv\Scripts\Activate.ps1; python android-lab\lab\orchestrator.py ui --port {1}" -f $script:RepoRoot, $Port)
}
