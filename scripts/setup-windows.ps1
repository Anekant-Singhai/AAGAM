<#
Sets up AAGAM on her Windows laptop.

  setup-windows.cmd                     create the Python environment, install AAGAM, set up the data folder
  setup-windows.cmd -ConfigureClaude    also add AAGAM to Claude Desktop (its config is backed up first)
  setup-windows.cmd -DesktopShortcut    also put "AAGAM" and "CS Desk browser" shortcuts on the desktop
  setup-windows.cmd -LocalAI            also download the local AI model (needs Ollama from ollama.com)

Needs Python 3.11 or newer (python.org installer with "Add python.exe to PATH" ticked) and Chrome or Edge.
Client data goes to %USERPROFILE%\AAGAM unless AAGAM_HOME is set. The interface is already built; no
Node.js is needed on her laptop. It finishes by running `aagam doctor`, which checks everything and says
how to fix whatever is missing.
#>
param(
    [switch]$ConfigureClaude,
    [switch]$DesktopShortcut,
    [switch]$LocalAI,
    [string]$Model = 'qwen3:4b'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
$pythonw = Join-Path $venv 'Scripts\pythonw.exe'
$aagam = Join-Path $venv 'Scripts\aagam.exe'
$csdesk = Join-Path $venv 'Scripts\csdesk.exe'

function Find-Python {
    foreach ($candidate in @(@('py', '-3'), @('python'))) {
        if (Get-Command $candidate[0] -ErrorAction SilentlyContinue) {
            $check = @($candidate | Select-Object -Skip 1) + @('-c', 'import sys; print(sys.version_info >= (3, 11))')
            $answer = & $candidate[0] @check 2>$null
            if ($answer -eq 'True') { return , $candidate }
        }
    }
    throw 'Python 3.11 or newer was not found. Install it from python.org (tick "Add python.exe to PATH"), then run this again.'
}

if (-not (Test-Path $python)) {
    $found = Find-Python
    Write-Host "Creating the Python environment in $venv"
    $create = @($found | Select-Object -Skip 1) + @('-m', 'venv', $venv)
    & $found[0] @create
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}

Write-Host 'Installing AAGAM and its libraries (a few minutes the first time)'
# A slow home connection makes PyPI time out at pip's default 15 seconds; wait longer and retry more before giving up.
$patient = @('--timeout', '60', '--retries', '10')
& $python -m pip install --upgrade pip --quiet @patient
& $python -m pip install -e $root --quiet @patient
if ($LASTEXITCODE -ne 0) { throw 'Installing AAGAM failed; see the messages above. If they mention timeouts, check the internet connection and run this again.' }

& $aagam init
if ($LASTEXITCODE -ne 0) { throw 'aagam init failed.' }

if ($ConfigureClaude) {
    & $aagam claude-config --write
    if ($LASTEXITCODE -ne 0) { throw 'Could not update the Claude Desktop config.' }
}

if ($LocalAI) {
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollama) {
        Write-Host 'Ollama is not installed. Install it from https://ollama.com, then run: ollama pull' $Model
    } else {
        Write-Host "Downloading the local AI model $Model (a few GB, once)"
        & ollama pull $Model
        [Environment]::SetEnvironmentVariable('AAGAM_LOCAL_AI_MODEL', $Model, 'User')
    }
}

if ($DesktopShortcut) {
    $shell = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath('Desktop')
    $link = $shell.CreateShortcut((Join-Path $desktop 'AAGAM.lnk'))
    $link.TargetPath = $pythonw
    $link.Arguments = '-m aagam'
    $link.WorkingDirectory = $root
    $link.Description = 'Open AAGAM'
    $link.Save()
    $link = $shell.CreateShortcut((Join-Path $desktop 'CS Desk browser.lnk'))
    $link.TargetPath = $csdesk
    $link.Arguments = 'browser'
    $link.WorkingDirectory = $root
    $link.WindowStyle = 7
    $link.Description = 'Open the CS Desk browser window and log in to MCA'
    $link.Save()
    Write-Host "Added 'AAGAM' and 'CS Desk browser' to the desktop."
}

Write-Host ''
Write-Host 'Checking this computer (aagam doctor):'
& $aagam doctor
$healthy = $LASTEXITCODE -eq 0
Write-Host ''
if ($healthy) {
    Write-Host 'AAGAM is set up.'
} else {
    Write-Host 'AAGAM is installed, but fix the items marked above (the -> lines say how), then run: aagam doctor'
}
Write-Host 'Next:'
if ($DesktopShortcut -or (Test-Path (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AAGAM.lnk'))) {
    Write-Host '  - Open AAGAM from the "AAGAM" shortcut on the desktop.'
} else {
    Write-Host "  - Open AAGAM with: $aagam   (or run setup-windows.cmd -DesktopShortcut for a desktop shortcut)"
}
if (-not $ConfigureClaude) { Write-Host '  - To use AAGAM from Claude Desktop: setup-windows.cmd -ConfigureClaude, then restart Claude Desktop.' }
if (-not $LocalAI) { Write-Host '  - For local AI summaries: install Ollama (ollama.com), then setup-windows.cmd -LocalAI.' }
Write-Host "  - To check again later: $aagam doctor"
