<#
Sets up AAGAM in this folder: Python (installed for this user if there is none), AAGAM's own Python
environment, the data folder, and the extras asked for. scripts\install.ps1 runs this; so do the AAGAM
Manager and the System page's Repair buttons.

  setup-windows.cmd                     the Python environment, AAGAM and the data folder
  setup-windows.cmd -ConfigureClaude    also add AAGAM to Claude Desktop (its config is backed up first)
  setup-windows.cmd -DesktopShortcut    also put AAGAM, AAGAM Manager and CS Desk browser on the desktop and in the Start menu
  setup-windows.cmd -LocalAI            also install the local AI (Ollama) and download its model (-Model qwen3:4b)
  setup-windows.cmd -RepairOnly ...     only the extras named, nothing else (the Repair buttons use this)

Nothing needs to be installed first: a missing Python is installed for this user from python.org
(-NoPythonInstall stops that). Client data goes to %USERPROFILE%\AAGAM unless AAGAM_HOME is set. The
interface is already built, so no Node.js is needed. It finishes with `aagam doctor`, which checks everything
and says how to fix whatever is missing.
#>
param(
    [switch]$ConfigureClaude,
    [switch]$DesktopShortcut,
    [switch]$LocalAI,
    [switch]$RepairOnly,
    [switch]$NoPythonInstall,
    [string]$Model = 'qwen3:4b'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
$pythonw = Join-Path $venv 'Scripts\pythonw.exe'
$aagam = Join-Path $venv 'Scripts\aagam.exe'
$csdesk = Join-Path $venv 'Scripts\csdesk.exe'
# The Python installed when there is none (a newer 3.13 is used when python.org has one).
$PythonFallback = '3.13.17'

function Write-Step([string]$Text) { Write-Host ''; Write-Host "== $Text" }

# Windows PowerShell 5.1 turns a program's warnings on stderr into errors when 'Stop' is set; run programs with
# 'Continue' and judge them by their exit code instead.
function Invoke-Program([scriptblock]$Block) {
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Block } finally { $ErrorActionPreference = $saved }
}

function Update-SessionPath {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
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

function Test-Python([string]$Exe, [string[]]$Before) {
    # True when this command is Python 3.11 or newer. (The Microsoft Store's python.exe placeholder fails here.)
    try {
        $answer = Invoke-Program { & $Exe @Before -c 'import sys; print(sys.version_info >= (3, 11))' 2>$null }
        return ($LASTEXITCODE -eq 0 -and "$answer".Trim() -eq 'True')
    } catch { return $false }
}

function Find-Python {
    $candidates = @(@('py', '-3.13'), @('py', '-3.12'), @('py', '-3.11'), @('py', '-3'), @('python'))
    foreach ($candidate in $candidates) {
        if (Get-Command $candidate[0] -ErrorAction SilentlyContinue) {
            $before = @($candidate | Select-Object -Skip 1)
            if (Test-Python $candidate[0] $before) { return , $candidate }
        }
    }
    # Installed but not on PATH yet (just installed, or "Add to PATH" was left unticked).
    $places = @()
    foreach ($hive in 'HKCU:', 'HKLM:') {
        foreach ($version in '3.13', '3.12', '3.11', '3.14') {
            $key = "$hive\Software\Python\PythonCore\$version\InstallPath"
            if (Test-Path $key) {
                $item = Get-ItemProperty $key
                if ($item.ExecutablePath) { $places += $item.ExecutablePath } elseif ($item.'(default)') { $places += (Join-Path $item.'(default)' 'python.exe') }
            }
        }
    }
    foreach ($version in '313', '312', '311', '314') { $places += (Join-Path $env:LOCALAPPDATA "Programs\Python\Python$version\python.exe") }
    foreach ($place in $places) {
        if ($place -and (Test-Path $place) -and (Test-Python $place @())) { return , @($place) }
    }
    return $null
}

function Get-PythonInstallerUrl {
    # The newest 3.13.N on python.org that has a Windows installer (64-bit; it also runs on ARM laptops).
    try {
        $listing = Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/' -UseBasicParsing -TimeoutSec 30
        $versions = [regex]::Matches($listing.Content, 'href="3\.13\.(\d+)/"') | ForEach-Object { [int]$_.Groups[1].Value } | Sort-Object -Descending
        foreach ($n in ($versions | Select-Object -First 6)) {
            $url = "https://www.python.org/ftp/python/3.13.$n/python-3.13.$n-amd64.exe"
            try {
                Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing -TimeoutSec 20 | Out-Null
                return $url
            } catch { continue }
        }
    } catch { }
    return "https://www.python.org/ftp/python/$PythonFallback/python-$PythonFallback-amd64.exe"
}

function Install-Python {
    $url = Get-PythonInstallerUrl
    $setup = Join-Path $env:TEMP ([IO.Path]::GetFileName($url))
    Write-Step "Downloading Python ($([IO.Path]::GetFileName($url)))"
    Get-File $url $setup
    Write-Step 'Installing Python for this user (a minute or two)'
    $arguments = '/quiet', 'InstallAllUsers=0', 'InstallLauncherAllUsers=0', 'PrependPath=1', 'Include_launcher=1', 'Include_test=0', 'Include_tcltk=1'
    $process = Start-Process -FilePath $setup -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0 -and $process.ExitCode -ne 3010) { throw "Python's installer stopped (code $($process.ExitCode))." }
    Remove-Item $setup -Force -ErrorAction SilentlyContinue
    Update-SessionPath
}

function Find-Ollama {
    $command = Get-Command ollama -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $default = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path $default) { return $default }
    return $null
}

function Test-Ollama {
    try { Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 3 | Out-Null; return $true } catch { return $false }
}

function Wait-Ollama([int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Ollama) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Install-LocalAI {
    $ollama = Find-Ollama
    if (-not $ollama) {
        $setup = Join-Path $env:TEMP 'OllamaSetup.exe'
        Write-Step 'Downloading the local AI (Ollama, about 1 GB, once)'
        Get-File 'https://ollama.com/download/OllamaSetup.exe' $setup
        Write-Step 'Installing the local AI'
        $process = Start-Process -FilePath $setup -ArgumentList '/VERYSILENT', '/NORESTART', '/SUPPRESSMSGBOXES' -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "The local AI's installer stopped (code $($process.ExitCode))." }
        Remove-Item $setup -Force -ErrorAction SilentlyContinue
        Update-SessionPath
        $ollama = Find-Ollama
        if (-not $ollama) { throw 'The local AI was installed but ollama.exe was not found. Restart the computer and choose Install local AI in the AAGAM Manager.' }
    }
    if (-not (Wait-Ollama 20)) {
        Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden
        if (-not (Wait-Ollama 60)) { throw 'The local AI did not start. Restart the computer, then choose Install local AI in the AAGAM Manager.' }
    }
    Write-Step "Downloading the local AI model $Model (a few GB, once)"
    Invoke-Program { & $ollama pull $Model }
    if ($LASTEXITCODE -ne 0) { throw "Downloading the model $Model failed; check the internet connection and try again." }
    [Environment]::SetEnvironmentVariable('AAGAM_LOCAL_AI_MODEL', $Model, 'User')
    $env:AAGAM_LOCAL_AI_MODEL = $Model
}

function New-Shortcut([string]$Path, [string]$Target, [string]$Arguments, [string]$Description, [int]$WindowStyle = 1) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($Path)
    $link.TargetPath = $Target
    $link.Arguments = $Arguments
    $link.WorkingDirectory = $root
    $link.Description = $Description
    $link.WindowStyle = $WindowStyle
    $link.Save()
}

function Add-Shortcuts {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'AAGAM'
    New-Item -ItemType Directory -Force $menu | Out-Null
    $manager = Join-Path $root 'manage.cmd'
    foreach ($folder in $desktop, $menu) {
        New-Shortcut (Join-Path $folder 'AAGAM.lnk') $pythonw '-m aagam' 'Open AAGAM'
        New-Shortcut (Join-Path $folder 'CS Desk browser.lnk') $csdesk 'browser' 'Open the CS Desk browser window and log in to MCA' 7
        if (Test-Path $manager) { New-Shortcut (Join-Path $folder 'AAGAM Manager.lnk') $manager '' 'Update, check, repair or remove AAGAM' }
    }
    Write-Host 'Added AAGAM, AAGAM Manager and CS Desk browser to the desktop and the Start menu.'
}

# ------------------------------------------------------------------ AAGAM itself

if (-not $RepairOnly) {
    if ((Test-Path $python) -and -not (Test-Python $python @())) {
        Write-Step "AAGAM's Python environment is damaged; making it again"
        Remove-Item -Recurse -Force $venv
    }
    if (-not (Test-Path $python)) {
        $found = Find-Python
        if (-not $found) {
            if ($NoPythonInstall) { throw 'Python 3.11 or newer was not found. Install it from python.org (tick "Add python.exe to PATH"), then run this again.' }
            Install-Python
            $found = Find-Python
            if (-not $found) { throw 'Python was installed but cannot be found yet. Restart the computer and run the installer again.' }
        }
        Write-Step "Creating AAGAM's Python environment in $venv"
        $create = @($found | Select-Object -Skip 1) + @('-m', 'venv', $venv)
        Invoke-Program { & $found[0] @create }
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $python)) { throw 'Could not create the Python environment.' }
    }

    Write-Step 'Installing AAGAM and its libraries (a few minutes the first time)'
    # A slow home connection makes PyPI time out at pip's default 15 seconds; wait longer and retry more before giving up.
    $patient = @('--timeout', '60', '--retries', '10', '--disable-pip-version-check')
    Invoke-Program { & $python -m pip install --upgrade pip --quiet @patient }
    Invoke-Program { & $python -m pip install -e $root --quiet @patient }
    if ($LASTEXITCODE -ne 0) { throw 'Installing AAGAM failed; see the messages above. If they mention timeouts, check the internet connection and run this again.' }

    Invoke-Program { & $aagam init }
    if ($LASTEXITCODE -ne 0) { throw 'aagam init failed.' }
}

# ------------------------------------------------------------------ the extras

if ($ConfigureClaude) {
    Write-Step 'Adding AAGAM to Claude Desktop'
    Invoke-Program { & $aagam claude-config --write }
    if ($LASTEXITCODE -ne 0) { throw 'Could not update the Claude Desktop config.' }
    $store = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Packages') -Directory -Filter 'Claude_*' -ErrorAction SilentlyContinue
    if (-not $store -and -not (Test-Path (Join-Path $env:APPDATA 'Claude'))) {
        Write-Host 'Claude Desktop is not installed yet. Install it from https://claude.ai/download and sign in,'
        Write-Host 'then choose "Connect Claude Desktop" in the AAGAM Manager.'
    }
}

if ($LocalAI) {
    try {
        Install-LocalAI
    } catch {
        # The local AI is optional: AAGAM works without it, so say what happened and carry on.
        Write-Host "The local AI was not set up: $($_.Exception.Message)"
        Write-Host 'Everything else works without it. Try again later with "Install local AI" in the AAGAM Manager.'
    }
}

if ($DesktopShortcut) {
    Write-Step 'Adding shortcuts'
    Add-Shortcuts
}

# ------------------------------------------------------------------ checking

Write-Step 'Checking this computer (aagam doctor)'
Invoke-Program { & $aagam doctor }
$healthy = $LASTEXITCODE -eq 0
Write-Host ''
if ($healthy) {
    Write-Host 'AAGAM is set up.'
} else {
    Write-Host 'AAGAM is installed, but fix the items marked above (the -> lines say how), then run: aagam doctor'
}
if (-not $RepairOnly) {
    Write-Host 'Next:'
    if ($DesktopShortcut -or (Test-Path (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AAGAM.lnk'))) {
        Write-Host '  - Open AAGAM from the "AAGAM" shortcut on the desktop or in the Start menu.'
    } else {
        Write-Host "  - Open AAGAM with: $aagam   (or run setup-windows.cmd -DesktopShortcut for shortcuts)"
    }
    if (-not $ConfigureClaude) { Write-Host '  - To use AAGAM from Claude Desktop: setup-windows.cmd -ConfigureClaude, then restart Claude Desktop.' }
    if (-not $LocalAI) { Write-Host '  - For local AI summaries: setup-windows.cmd -LocalAI (it installs Ollama too).' }
    Write-Host "  - To check again later: $aagam doctor"
}
