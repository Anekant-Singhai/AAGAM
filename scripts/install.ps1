<#
Installs AAGAM on this computer, with everything it needs. Double-click install.cmd in the AAGAM folder, or
paste this into PowerShell (for a public repository):

    irm https://raw.githubusercontent.com/Anekant-Singhai/AAGAM/main/scripts/install.ps1 | iex

It puts AAGAM in %LOCALAPPDATA%\Programs\AAGAM (no administrator rights needed), installs Python for this user
if there is none, sets AAGAM up, installs the local AI (Ollama and its model, a few GB, once), adds AAGAM to
Claude Desktop, puts shortcuts on the desktop and in the Start menu, adds AAGAM to Settings > Apps (so it can be
removed like any program) and ends with a health check. Running it again repairs or refreshes an installation.
Client data, in %USERPROFILE%\AAGAM, is never touched.

  -InstallDir <folder>   install somewhere else
  -NoLocalAI             leave out the local AI
  -NoClaude              don't add AAGAM to Claude Desktop
  -NoShortcuts           no desktop or Start menu shortcuts
  -NoRegister            don't add AAGAM to Settings > Apps
  -Model <name>          the local AI model (qwen3:4b; qwen3:8b with a graphics card)
  -Repo <owner/name>     the GitHub repository AAGAM comes from and updates from
  -Branch <name>         its branch (main)
  -NoOpen                don't open AAGAM in the browser at the end

A record of the installation is kept in %TEMP%\aagam-install.log.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = '',
    [switch]$NoLocalAI,
    [switch]$NoClaude,
    [switch]$NoShortcuts,
    [switch]$NoRegister,
    [string]$Model = 'qwen3:4b',
    [string]$Repo = '',
    [string]$Branch = 'main',
    [switch]$NoOpen
)

# ---- The GitHub repository AAGAM comes from. Change this one line if yours is somewhere else. ----
$DefaultRepo = 'Anekant-Singhai/AAGAM'

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
if (-not $Repo) { $Repo = $DefaultRepo }
if (-not $InstallDir) { $InstallDir = Join-Path $env:LOCALAPPDATA 'Programs\AAGAM' }
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
# What an installation is made of; nothing else travels (no .git, .venv, client data or node_modules).
$Parts = 'src', 'scripts', 'docs', 'pyproject.toml', 'README.md', 'START-HERE.txt', 'install.cmd', 'manage.cmd', 'LICENSE'

function Write-Step([string]$Text) { Write-Host ''; Write-Host "== $Text" }

function Invoke-Program([scriptblock]$Block) {
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Block } finally { $ErrorActionPreference = $saved }
}

function Get-File([string]$Url, [string]$OutFile) {
    $curl = Join-Path $env:SystemRoot 'System32\curl.exe'
    if (Test-Path $curl) {
        Invoke-Program { & $curl --fail --location --retry 3 --retry-delay 2 --progress-bar --output $OutFile $Url }
        if ($LASTEXITCODE -ne 0) { throw "The download failed: $Url" }
    } else {
        Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
    }
}

function Get-FromGitHub([string]$Repo, [string]$Branch) {
    # Download the branch's newest version; the commit is asked for first so the download is exactly that one.
    $work = Join-Path $env:TEMP ('aagam-download-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
    New-Item -ItemType Directory -Force $work | Out-Null
    $commit = $null
    try {
        $head = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/commits/$Branch" -TimeoutSec 30 `
            -Headers @{ 'User-Agent' = 'AAGAM-installer'; 'Accept' = 'application/vnd.github+json' }
        $commit = $head.sha
    } catch { $commit = $null }
    if ($commit) { $url = "https://github.com/$Repo/archive/$commit.zip" } else { $url = "https://github.com/$Repo/archive/refs/heads/$Branch.zip" }
    $zip = Join-Path $work 'aagam.zip'
    Write-Step "Downloading AAGAM from github.com/$Repo"
    try {
        Get-File $url $zip
    } catch {
        throw ("AAGAM could not be downloaded from github.com/$Repo. If the repository is private: open it in your " +
            'browser while signed in to GitHub, choose Code > Download ZIP, extract the ZIP (right-click > Extract All) ' +
            'and double-click install.cmd inside it.')
    }
    Expand-Archive -Path $zip -DestinationPath $work -Force
    $folder = Get-ChildItem $work -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'pyproject.toml') } | Select-Object -First 1
    if (-not $folder) { throw 'The download does not look like AAGAM (it has no pyproject.toml).' }
    return @{ Path = $folder.FullName; Commit = $commit; Source = 'download'; Work = $work }
}

function Copy-Parts([string]$From, [string]$To) {
    New-Item -ItemType Directory -Force $To | Out-Null
    foreach ($part in $Parts) {
        $source = Join-Path $From $part
        $target = Join-Path $To $part
        if (Test-Path $source -PathType Container) {
            # Mirror the folder; robocopy leaves the excluded names (pip's *.egg-info, caches) alone on both sides.
            Invoke-Program { robocopy $source $target /MIR /NFL /NDL /NJH /NJS /NP /XD __pycache__ '*.egg-info' node_modules /XF '*.pyc' | Out-Null }
            if ($LASTEXITCODE -ge 8) { throw "Copying $part failed (robocopy code $LASTEXITCODE)." }
        } elseif (Test-Path $source -PathType Leaf) {
            Copy-Item -Force $source $target
        }
    }
    $global:LASTEXITCODE = 0
    # Files from a downloaded ZIP are marked as coming from the internet; this copy is ours now.
    Get-ChildItem -Recurse -File $To -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
}

function Get-DataFolder {
    if ($env:AAGAM_HOME) { return [IO.Path]::GetFullPath($env:AAGAM_HOME) }
    return Join-Path $env:USERPROFILE 'AAGAM'
}

function Test-Inside([string]$Path, [string]$Folder) {
    $p = $Path.TrimEnd('\') + '\'
    $f = $Folder.TrimEnd('\') + '\'
    return $p.StartsWith($f, [StringComparison]::OrdinalIgnoreCase)
}

function Register-App([string]$Version) {
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AAGAM'
    $uninstall = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\scripts\uninstall.ps1`""
    New-Item -Path $key -Force | Out-Null
    $values = @{
        DisplayName = 'AAGAM'; DisplayVersion = $Version; Publisher = 'AAGAM'; InstallLocation = $InstallDir
        UninstallString = $uninstall; QuietUninstallString = "$uninstall -Quiet"; URLInfoAbout = "https://github.com/$Repo"
        DisplayIcon = (Join-Path $InstallDir '.venv\Scripts\pythonw.exe'); InstallDate = (Get-Date -Format 'yyyyMMdd')
    }
    foreach ($name in $values.Keys) { New-ItemProperty -Path $key -Name $name -Value $values[$name] -PropertyType String -Force | Out-Null }
    $size = [int]((Get-ChildItem -Recurse -File $InstallDir -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1KB)
    foreach ($pair in @(@('NoModify', 1), @('NoRepair', 1), @('EstimatedSize', $size))) {
        New-ItemProperty -Path $key -Name $pair[0] -Value $pair[1] -PropertyType DWord -Force | Out-Null
    }
}

$transcript = $false
try {
    Start-Transcript -Path (Join-Path $env:TEMP 'aagam-install.log') -Force | Out-Null
    $transcript = $true
} catch { }

try {
    Write-Host ''
    Write-Host '  AAGAM installer'
    Write-Host "  Program folder: $InstallDir"
    Write-Host "  Data folder:    $(Get-DataFolder)  (your documents and records; never touched by installing)"

    $data = Get-DataFolder
    if ((Test-Inside $InstallDir $data) -or (Test-Inside $data $InstallDir)) {
        throw "The program folder ($InstallDir) and the data folder ($data) must be separate. Choose another -InstallDir."
    }

    # Where AAGAM comes from: this folder (an extracted ZIP or a clone), or GitHub when run from the web.
    $here = $null
    if ($PSScriptRoot) {
        $candidate = Split-Path -Parent $PSScriptRoot
        if (Test-Path (Join-Path $candidate 'src\aagam\__init__.py')) { $here = $candidate }
    }
    if ($here) {
        $origin = @{ Path = $here; Commit = $null; Source = 'zip'; Work = $null }
        if ((Test-Path (Join-Path $here '.git')) -and (Get-Command git -ErrorAction SilentlyContinue)) {
            $commit = Invoke-Program { git -C $here rev-parse HEAD 2>$null }
            if ($LASTEXITCODE -eq 0 -and $commit) { $origin.Commit = "$commit".Trim(); $origin.Source = 'git' }
        }
    } else {
        $origin = Get-FromGitHub $Repo $Branch
    }

    $same = [IO.Path]::GetFullPath($origin.Path).TrimEnd('\') -ieq $InstallDir.TrimEnd('\')
    if ($same) {
        Write-Step 'Repairing the AAGAM already in this folder'
        if ($origin.Source -eq 'zip') { $origin.Source = 'local' }
    } else {
        Write-Step "Copying AAGAM to $InstallDir"
        Copy-Parts $origin.Path $InstallDir
    }

    # Python, AAGAM's environment, the data folder and the extras.
    $setupArgs = @{}
    if (-not $NoShortcuts) { $setupArgs.DesktopShortcut = $true }
    if (-not $NoClaude) { $setupArgs.ConfigureClaude = $true }
    if (-not $NoLocalAI) { $setupArgs.LocalAI = $true; $setupArgs.Model = $Model }
    & (Join-Path $InstallDir 'scripts\setup-windows.ps1') @setupArgs

    # The record the updater works from: where this copy came from and which version it is.
    $python = Join-Path $InstallDir '.venv\Scripts\python.exe'
    $record = @('-m', 'aagam.updates', 'record', '--app', $InstallDir, '--repo', $Repo, '--branch', $Branch, '--source', $origin.Source)
    if ($origin.Commit) { $record += @('--commit', $origin.Commit) }
    if (-not (Test-Path (Join-Path $InstallDir 'install.json'))) { $record += @('--auto-update', 'on') }
    Invoke-Program { & $python @record | Out-Null }
    if ($LASTEXITCODE -ne 0) { Write-Host 'The install record could not be written; updates will ask to be set up.' }
    # After the record exists, an installed copy (not a developer's git checkout) gets a daily check.
    if (-not (Test-Path (Join-Path $InstallDir '.git')) -and (Test-Path (Join-Path $InstallDir '.venv\Scripts\pythonw.exe'))) {
        Invoke-Program { & $python -m aagam.updates schedule --app $InstallDir }
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'The daily update check was not added. AAGAM still updates itself while it is open.'
        } else {
            Write-Host 'Each day at 8:00, if AAGAM is not open, a new version is installed by itself.'
        }
    }

    $version = (Select-String -Path (Join-Path $InstallDir 'src\aagam\__init__.py') -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
    if (-not $NoRegister) {
        Register-App $version
        Write-Host 'AAGAM is in Settings > Apps, where it can be removed like any program.'
    }
    if ($origin.Work) { Remove-Item -Recurse -Force $origin.Work -ErrorAction SilentlyContinue }

    Write-Host ''
    Write-Host "AAGAM $version is installed."
    if (-not $NoShortcuts) {
        Write-Host '  Open it from the AAGAM shortcut on the desktop or in the Start menu.'
        Write-Host '  "AAGAM Manager" (same places) updates, checks, repairs or removes it.'
    } else {
        Write-Host "  Open it with: $InstallDir\.venv\Scripts\aagam.exe"
    }
    Write-Host '  Updates arrive by themselves from GitHub while AAGAM is idle, and at 8:00 when it is closed.'
    if (-not $NoOpen) {
        $pythonw = Join-Path $InstallDir '.venv\Scripts\pythonw.exe'
        if (Test-Path $pythonw) {
            Write-Host 'Opening AAGAM in your browser.'
            Start-Process -FilePath $pythonw -ArgumentList '-m', 'aagam' -WorkingDirectory $InstallDir | Out-Null
        }
    }
    $code = 0
} catch {
    Write-Host ''
    Write-Host "The installation stopped: $($_.Exception.Message)"
    Write-Host "Nothing in your data folder was changed. The details are in $(Join-Path $env:TEMP 'aagam-install.log')."
    $code = 1
} finally {
    if ($transcript) { try { Stop-Transcript | Out-Null } catch { } }
}
if ($PSScriptRoot) { exit $code }
