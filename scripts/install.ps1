<#
Installs AAGAM on this computer, with everything it needs. Double-click install.cmd in the AAGAM folder, or
paste this into PowerShell (for a public repository):

    irm https://raw.githubusercontent.com/Anekant-Singhai/AAGAM/HEAD/scripts/install.ps1 | iex

It puts AAGAM in %LOCALAPPDATA%\Programs\AAGAM (no administrator rights needed), installs Python for this user
if there is none, sets AAGAM up, installs the local AI (Ollama and its model, a few GB, once), adds AAGAM to
Claude Desktop, puts shortcuts on the desktop and in the Start menu, starts AAGAM in the background when you sign in
to Windows, adds AAGAM to Settings > Apps (so it can be removed like any program) and ends with a health check.
Client data, in %USERPROFILE%\AAGAM, is never touched.

Running it again on a computer that already has AAGAM updates it: it fetches the newest version from GitHub (or uses
the AAGAM folder it is run from, if that is newer, or GitHub can't be reached), closes AAGAM, keeps a copy of the
version in place, puts the new one in, sets everything up again and opens AAGAM. It never goes back to an older
version, and if anything fails the previous version is put back.

  -InstallDir <folder>   install somewhere else
  -NoLocalAI             leave out the local AI
  -NoClaude              don't add AAGAM to Claude Desktop
  -NoShortcuts           no desktop or Start menu shortcuts
  -NoRegister            don't add AAGAM to Settings > Apps
  -NoAutostart           don't start AAGAM in the background when you sign in to Windows
  -NoSchedule            don't add the daily 8:00 update check
  -Model <name>          the local AI model (qwen3:4b; qwen3:8b with a graphics card)
  -Repo <owner/name>     the GitHub repository AAGAM comes from and updates from
  -Branch <name>         its branch (normally left out: the repository's default branch)
  -NoOpen                don't open AAGAM in the browser at the end
  -Offline               don't ask GitHub: install (or set up again) the AAGAM folder this is run from

A record of the installation is kept in %TEMP%\aagam-install.log.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = '',
    [switch]$Offline,
    [switch]$NoLocalAI,
    [switch]$NoClaude,
    [switch]$NoShortcuts,
    [switch]$NoRegister,
    [switch]$NoAutostart,
    [switch]$NoSchedule,
    [string]$Model = 'qwen3:4b',
    [string]$Repo = '',
    [string]$Branch = '',
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

function Get-DefaultBranch([string]$Repo) {
    # The repository's own main branch ("master" or "main"), so nothing here has to guess it.
    try {
        $about = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo" -TimeoutSec 30 `
            -Headers @{ 'User-Agent' = 'AAGAM-installer'; 'Accept' = 'application/vnd.github+json' }
        if ($about.default_branch) { return [string]$about.default_branch }
    } catch { }
    return ''
}

function Get-FromGitHub([string]$Repo, [string]$Branch) {
    # Download the branch's newest version; the commit is asked for first so the download is exactly that one.
    $work = Join-Path $env:TEMP ('aagam-download-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
    New-Item -ItemType Directory -Force $work | Out-Null
    $commit = $null
    if (-not $Branch) { $Branch = Get-DefaultBranch $Repo }
    if (-not $Branch) { $Branch = 'HEAD' }  # GitHub's name for the default branch, when its API can't be asked
    try {
        $head = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/commits/$Branch" -TimeoutSec 30 `
            -Headers @{ 'User-Agent' = 'AAGAM-installer'; 'Accept' = 'application/vnd.github+json' }
        $commit = $head.sha
    } catch { $commit = $null }
    if ($commit) { $url = "https://github.com/$Repo/archive/$commit.zip" }
    elseif ($Branch -eq 'HEAD') { $url = "https://github.com/$Repo/archive/HEAD.zip" }
    else { $url = "https://github.com/$Repo/archive/refs/heads/$Branch.zip" }
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
    return @{ Path = $folder.FullName; Commit = $commit; Source = 'download'; Work = $work; Branch = $(if ($Branch -ne 'HEAD') { $Branch } else { '' }) }
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

function Get-VersionOf([string]$Folder) {
    $init = Join-Path $Folder 'src\aagam\__init__.py'
    if (-not (Test-Path $init)) { return $null }
    $found = Select-String -Path $init -Pattern '__version__\s*=\s*"([^"]+)"'
    if ($found) { return $found.Matches[0].Groups[1].Value }
    return $null
}

function Compare-Version([string]$A, [string]$B) {
    # 1 when version A is newer than B, -1 when older, 0 when the same ("0.2.10" is newer than "0.2.9").
    $pa = @([regex]::Matches("$A", '\d+') | ForEach-Object { [int]$_.Value })
    $pb = @([regex]::Matches("$B", '\d+') | ForEach-Object { [int]$_.Value })
    for ($i = 0; $i -lt [Math]::Max($pa.Count, $pb.Count); $i++) {
        $x = if ($i -lt $pa.Count) { $pa[$i] } else { 0 }
        $y = if ($i -lt $pb.Count) { $pb[$i] } else { 0 }
        if ($x -gt $y) { return 1 }
        if ($x -lt $y) { return -1 }
    }
    return 0
}

function Read-Record {
    $path = Join-Path $InstallDir 'install.json'
    if (-not (Test-Path $path)) { return $null }
    try { return (Get-Content -Raw -Encoding UTF8 $path | ConvertFrom-Json) } catch { return $null }
}

function Get-Port { if ($env:AAGAM_PORT) { return [int]$env:AAGAM_PORT } else { return 8765 } }

function Test-Port([int]$Number) {
    $client = New-Object Net.Sockets.TcpClient
    try {
        $wait = $client.BeginConnect('127.0.0.1', $Number, $null, $null)
        if (-not $wait.AsyncWaitHandle.WaitOne(500)) { return $false }
        $client.EndConnect($wait)
        return $true
    } catch { return $false } finally { $client.Close() }
}

function Stop-Aagam {
    # Close AAGAM's window server before its files are replaced. True when it was running (it is opened again at the end).
    $port = Get-Port
    if (-not (Test-Port $port)) { return $false }
    Write-Step 'Closing AAGAM while it is updated'
    try { Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$port/api/system/shutdown" -Headers @{ 'X-AAGAM' = '1' } -TimeoutSec 5 | Out-Null } catch { }
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline -and (Test-Port $port)) { Start-Sleep -Milliseconds 500 }
    return $true
}

function Save-Code {
    # A copy of the code in place now, so a failed update can put it back. The last two copies are kept.
    $backups = Join-Path $InstallDir '.update'
    $backup = Join-Path $backups ('backup-install-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Copy-Parts $InstallDir $backup
    Get-ChildItem $backups -Directory -Filter 'backup-install-*' -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -Skip 2 | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    return $backup
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
$backup = $null       # the code that was in place, while an update puts new code in
$wasRunning = $false  # AAGAM was open when the update began
$installed = $null
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

    # What is installed now, if anything. An installed copy keeps updating from the repository it came from.
    $installed = Get-VersionOf $InstallDir
    $record = Read-Record
    if (-not $PSBoundParameters.ContainsKey('Repo') -and $record -and $record.repo) { $Repo = [string]$record.repo }
    if ($installed) { Write-Host "  Installed now:  AAGAM $installed" }

    # Where the new copy comes from: the newest of GitHub's default branch (unless -Offline) and the AAGAM folder this
    # was run from (an extracted ZIP or a clone). The same version on both: GitHub's, whose commit is known.
    $local = $null
    if ($PSScriptRoot) {
        $candidate = Split-Path -Parent $PSScriptRoot
        if (Test-Path (Join-Path $candidate 'src\aagam\__init__.py')) {
            $local = @{ Path = $candidate; Commit = $null; Source = 'zip'; Work = $null; Branch = $Branch }
            if ((Test-Path (Join-Path $candidate '.git')) -and (Get-Command git -ErrorAction SilentlyContinue)) {
                $commit = Invoke-Program { git -C $candidate rev-parse HEAD 2>$null }
                if ($LASTEXITCODE -eq 0 -and $commit) { $local.Commit = "$commit".Trim(); $local.Source = 'git' }
            }
        }
    }
    $remote = $null
    if (-not $Offline) {
        try {
            $remote = Get-FromGitHub $Repo $Branch
        } catch {
            if (-not $local -and -not $installed) { throw }
            Write-Host "GitHub couldn't be reached or refused: $($_.Exception.Message)"
            if ($local) { Write-Host 'Carrying on with the AAGAM in this folder.' } else { Write-Host 'Setting up the AAGAM already installed again.' }
        }
    }
    $origin = $remote
    if ($local -and (-not $origin -or (Compare-Version (Get-VersionOf $local.Path) (Get-VersionOf $origin.Path)) -gt 0)) { $origin = $local }
    $repair = @{ Path = $InstallDir; Commit = $null; Source = 'local'; Work = $null; Branch = '' }
    if (-not $origin) {
        $origin = $repair
    } elseif ($installed -and (Compare-Version (Get-VersionOf $origin.Path) $installed) -lt 0) {
        Write-Host "The AAGAM on this computer ($installed) is newer than $(Get-VersionOf $origin.Path), so it stays; setting it up again."
        $origin = $repair
    }
    $newVersion = Get-VersionOf $origin.Path

    $same = [IO.Path]::GetFullPath($origin.Path).TrimEnd('\') -ieq $InstallDir.TrimEnd('\')
    if ($same) {
        Write-Step "Setting up AAGAM $newVersion again in $InstallDir"
        if ($origin.Source -eq 'zip') { $origin.Source = 'local' }
    } else {
        if ($installed) {
            $how = if ((Compare-Version $newVersion $installed) -gt 0) { "Updating AAGAM $installed to $newVersion" } else { "Refreshing AAGAM $newVersion" }
            $from = if ($origin.Source -eq 'download') { ' from GitHub' } else { " from $($origin.Path)" }
            Write-Step ($how + $from)
            $wasRunning = Stop-Aagam
            $backup = Save-Code
        } else {
            Write-Step "Copying AAGAM $newVersion to $InstallDir"
        }
        Copy-Parts $origin.Path $InstallDir
    }

    # Python, AAGAM's environment, the data folder and the extras. The health check comes last, below.
    $firstInstall = -not (Test-Path (Join-Path $InstallDir 'install.json'))
    $setupArgs = @{ FromInstaller = $true }
    if (-not $NoShortcuts) { $setupArgs.DesktopShortcut = $true }
    if (-not $NoClaude) { $setupArgs.ConfigureClaude = $true }
    if (-not $NoLocalAI) { $setupArgs.LocalAI = $true; $setupArgs.Model = $Model }
    & (Join-Path $InstallDir 'scripts\setup-windows.ps1') @setupArgs

    # Compile AAGAM's code now, so its first start is quick rather than waiting on Python (and Windows' virus check).
    $python = Join-Path $InstallDir '.venv\Scripts\python.exe'
    Invoke-Program { & $python -m compileall -q -j 0 (Join-Path $InstallDir 'src') | Out-Null }

    # The record the updater works from: where this copy came from and which version it is.
    $recordArgs = @('-m', 'aagam.updates', 'record', '--app', $InstallDir, '--repo', $Repo, '--source', $origin.Source)
    if ($origin.Branch) { $recordArgs += @('--branch', $origin.Branch) }  # else the repository's default branch, found when checking
    if ($origin.Commit) { $recordArgs += @('--commit', $origin.Commit) }
    elseif (-not $same) { $recordArgs += @('--commit', 'none') }  # new files from a ZIP: the commit they are isn't known
    if ($firstInstall) { $recordArgs += @('--auto-update', 'on') }
    Invoke-Program { & $python @recordArgs | Out-Null }
    if ($LASTEXITCODE -ne 0) { Write-Host 'The install record could not be written; updates will ask to be set up.' }
    # After the record exists, an installed copy (not a developer's git checkout) gets a daily check.
    if (-not $NoSchedule -and -not (Test-Path (Join-Path $InstallDir '.git')) -and (Test-Path (Join-Path $InstallDir '.venv\Scripts\pythonw.exe'))) {
        Invoke-Program { & $python -m aagam.updates schedule --app $InstallDir }
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'The daily update check was not added. AAGAM still updates itself while it is open.'
        } else {
            Write-Host 'Each day at 8:00, if AAGAM is not open, a new version is installed by itself.'
        }
    }

    # AAGAM waits in the background from sign-in, so the desktop shortcut opens at once and watched folders keep
    # coming in. Set once per copy (--once): a repair or reinstall keeps her choice. The AAGAM Manager or Task Manager >
    # Startup apps turns it off.
    if (-not $NoAutostart) {
        $now = Invoke-Program { & $python -m aagam.updates autostart --app $InstallDir on --once }
        if ($LASTEXITCODE -eq 0 -and "$now".Trim() -eq 'on') { Write-Host 'AAGAM starts in the background when you sign in to Windows.' }
    }

    $version = (Select-String -Path (Join-Path $InstallDir 'src\aagam\__init__.py') -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
    if (-not $NoRegister) {
        Register-App $version
        Write-Host 'AAGAM is in Settings > Apps, where it can be removed like any program.'
    }
    if ($remote -and $remote.Work) { Remove-Item -Recurse -Force $remote.Work -ErrorAction SilentlyContinue }

    # Everything is in place: check it all once, now that the install record and the start at sign-in are there too.
    Write-Step 'Checking this computer'
    Invoke-Program { & (Join-Path $InstallDir '.venv\Scripts\aagam.exe') doctor }

    Write-Host ''
    if ($installed -and (Compare-Version $version $installed) -gt 0) { Write-Host "AAGAM is updated from $installed to $version." }
    elseif ($installed) { Write-Host "AAGAM $version is set up again (it was already the newest)." }
    else { Write-Host "AAGAM $version is installed." }
    if ($installed) { Write-Host '  If you use Claude Desktop, quit it and open it again so it uses this version too.' }
    if (-not $NoShortcuts) {
        Write-Host '  Open it from the AAGAM shortcut on the desktop or in the Start menu.'
        Write-Host '  "AAGAM Manager" (same places) updates, checks, repairs or removes it.'
    } else {
        Write-Host "  Open it with: $InstallDir\.venv\Scripts\aagam.exe"
    }
    Write-Host '  New versions arrive by themselves from GitHub while AAGAM is not in use.'
    Write-Host '  Lines marked ! above are optional; lines marked X need the fix written under them.'
    $pythonw = Join-Path $InstallDir '.venv\Scripts\pythonw.exe'
    if (-not $NoOpen -and (Test-Path $pythonw)) {
        Write-Host 'Opening AAGAM in your browser.'
        Start-Process -FilePath $pythonw -ArgumentList '-m', 'aagam' -WorkingDirectory $InstallDir | Out-Null
    } elseif ($wasRunning -and (Test-Path $pythonw)) {
        Start-Process -FilePath $pythonw -ArgumentList '-m', 'aagam', 'serve' -WorkingDirectory $InstallDir | Out-Null  # as it was: running, no new window
    }
    $code = 0
} catch {
    Write-Host ''
    Write-Host "The installation stopped: $($_.Exception.Message)"
    if ($backup -and (Test-Path $backup)) {
        # An update that didn't finish: the version that was in place goes back, and runs again if it was running.
        try {
            Copy-Parts $backup $InstallDir
            Write-Host "The AAGAM you had ($installed) was put back, so it works as before."
            $pythonw = Join-Path $InstallDir '.venv\Scripts\pythonw.exe'
            if ($wasRunning -and (Test-Path $pythonw)) { Start-Process -FilePath $pythonw -ArgumentList '-m', 'aagam', 'serve' -WorkingDirectory $InstallDir | Out-Null }
        } catch {
            Write-Host "Putting the previous version back failed too ($($_.Exception.Message)). Run install.cmd again when the internet is back."
        }
    }
    Write-Host "Nothing in your data folder was changed. The details are in $(Join-Path $env:TEMP 'aagam-install.log')."
    $code = 1
} finally {
    if ($transcript) { try { Stop-Transcript | Out-Null } catch { } }
}
if ($PSScriptRoot) { exit $code }
