<#
Removes AAGAM from this computer: the program, its shortcuts, its entry in Settings > Apps and its entry in
Claude Desktop. The data folder (documents and client records) is kept unless you ask for it to go too.

  uninstall.ps1                                asks first
  uninstall.ps1 -Quiet                         no questions (the System page and `aagam uninstall` use this)
  uninstall.ps1 -RemoveData -Confirm REMOVE    also delete the data folder, with everything in it

The local AI (Ollama) is a program of its own and stays; remove it in Settings > Apps if it isn't needed.
#>
param(
    [switch]$Quiet,
    [switch]$RemoveData,
    [string]$Confirm = '',
    [int]$Port = 0
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$scripts = (Join-Path $root '.venv\Scripts').TrimEnd('\') + '\'
if (-not $Port) { $Port = if ($env:AAGAM_PORT) { [int]$env:AAGAM_PORT } else { 8765 } }
$userHome = [Environment]::GetEnvironmentVariable('AAGAM_HOME', 'User')
if ($env:AAGAM_HOME) { $data = $env:AAGAM_HOME } elseif ($userHome) { $data = $userHome } else { $data = Join-Path $env:USERPROFILE 'AAGAM' }

function Invoke-Program([scriptblock]$Block) {
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Block } finally { $ErrorActionPreference = $saved }
}

function Test-Port([int]$Number) {
    $client = New-Object Net.Sockets.TcpClient
    try { $client.Connect('127.0.0.1', $Number); return $true } catch { return $false } finally { $client.Close() }
}

if (-not (Test-Path (Join-Path $root 'src\aagam')) -or -not (Test-Path (Join-Path $root 'pyproject.toml'))) {
    Write-Host "$root does not look like an AAGAM program folder; nothing was removed."
    exit 1
}
if ($RemoveData -and $Quiet -and $Confirm -ne 'REMOVE') {
    Write-Host 'To delete the data folder too, add -Confirm REMOVE. Nothing was removed.'
    exit 1
}

if (-not $Quiet) {
    Write-Host ''
    Write-Host '  Remove AAGAM from this computer'
    Write-Host "  Program folder: $root (removed)"
    if ($RemoveData) { Write-Host "  Data folder:    $data (DELETED, with every document and record in it)" }
    else { Write-Host "  Data folder:    $data (kept: your documents and records stay)" }
    Write-Host ''
    $answer = Read-Host 'Type Y and press Enter to remove AAGAM (anything else keeps it)'
    if ($answer -notmatch '^(y|yes)$') { Write-Host 'Nothing was removed.'; exit 2 }
    if ($RemoveData -and $Confirm -ne 'REMOVE') {
        $Confirm = Read-Host 'To delete the data folder as well, type REMOVE (anything else keeps it)'
        if ($Confirm -ne 'REMOVE') { $RemoveData = $false; Write-Host 'The data folder will be kept.' }
    }
}

# 1. Close AAGAM: the window's server first, politely, then anything else running from its Python.
if (Test-Port $Port) {
    try { Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$Port/api/system/shutdown" -Headers @{ 'X-AAGAM' = '1' } -TimeoutSec 5 | Out-Null } catch { }
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline -and (Test-Port $Port)) { Start-Sleep -Milliseconds 500 }
}
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='aagam.exe' OR Name='csdesk.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($scripts, [StringComparison]::OrdinalIgnoreCase) -and $_.ProcessId -ne $PID } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# 2. Claude Desktop: take AAGAM out of each config it may read (each is backed up first).
$configs = @()
Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Packages') -Directory -Filter 'Claude_*' -ErrorAction SilentlyContinue |
    ForEach-Object { $configs += (Join-Path $_.FullName 'LocalCache\Roaming\Claude\claude_desktop_config.json') }
$configs += (Join-Path $env:APPDATA 'Claude\claude_desktop_config.json')
if (Test-Path $python) {
    Invoke-Program { & $python -m aagam.updates claude-remove @configs }
}

# 3. Shortcuts that open this copy, the Start menu folder, the Settings > Apps entry, the model setting.
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
foreach ($name in 'AAGAM.lnk', 'AAGAM Manager.lnk', 'CS Desk browser.lnk') {
    $link = Join-Path $desktop $name
    if (Test-Path $link) {
        $target = $shell.CreateShortcut($link).TargetPath
        if ($target -and $target.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { Remove-Item -Force $link }
    }
}
Remove-Item -Recurse -Force (Join-Path ([Environment]::GetFolderPath('Programs')) 'AAGAM') -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AAGAM' -ErrorAction SilentlyContinue
try { Unregister-ScheduledTask -TaskName 'AAGAM Update' -Confirm:$false -ErrorAction SilentlyContinue } catch { }
[Environment]::SetEnvironmentVariable('AAGAM_LOCAL_AI_MODEL', $null, 'User')

# 4. The data folder, only when asked for and only if it is AAGAM's.
if ($RemoveData -and $Confirm -eq 'REMOVE') {
    if ((Test-Path (Join-Path $data 'csdesk.db')) -or (Test-Path (Join-Path $data 'clients'))) {
        Remove-Item -Recurse -Force $data -ErrorAction SilentlyContinue
        Write-Host "Deleted the data folder $data."
    } else {
        Write-Host "$data does not look like AAGAM's data folder, so it was left alone."
    }
}

# 5. The program folder. A developer's git checkout is never deleted; otherwise it goes once this script has ended.
if (Test-Path (Join-Path $root '.git')) {
    Write-Host "$root is a git checkout, so the folder itself was left in place."
} else {
    Set-Location $env:TEMP
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', "timeout /t 3 /nobreak >nul & rmdir /s /q `"$root`"" -WindowStyle Hidden
}

Write-Host ''
Write-Host 'AAGAM is removed from this computer.'
if (-not ($RemoveData -and $Confirm -eq 'REMOVE')) { Write-Host "Your documents and records are still in $data. Installing AAGAM again finds them there." }
Write-Host 'The local AI (Ollama) is a separate program; remove it in Settings > Apps if you no longer need it.'
if (-not $Quiet) { Read-Host 'Press Enter to close' | Out-Null }
exit 0
