<#
The AAGAM Manager: open, update, check, repair or remove AAGAM, by choosing a number. The "AAGAM Manager"
shortcut on the desktop and in the Start menu opens this (through manage.cmd). It works even when AAGAM's
window doesn't, which is when it is most needed.
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

function Invoke-Aagam([string[]]$Arguments) {
    if (-not (Test-Path $python)) {
        Write-Host "AAGAM's Python environment is missing. Choose 5 (Repair) first."
        return
    }
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $python -m aagam @Arguments } finally { $ErrorActionPreference = $saved }
}

function Get-Version {
    $init = Join-Path $root 'src\aagam\__init__.py'
    if (-not (Test-Path $init)) { return '?' }
    $found = Select-String -Path $init -Pattern '__version__\s*=\s*"([^"]+)"'
    if ($found) { return $found.Matches[0].Groups[1].Value }
    return '?'
}

while ($true) {
    Write-Host ''
    Write-Host "  AAGAM Manager   (AAGAM $(Get-Version), in $root)"
    Write-Host ''
    Write-Host '   1  Open AAGAM'
    Write-Host '   2  Check for updates'
    Write-Host '   3  Update now'
    Write-Host '   4  Health check'
    Write-Host '   5  Repair (set AAGAM up again; your data is kept)'
    Write-Host '   6  Install or repair the local AI'
    Write-Host '   7  Connect Claude Desktop'
    Write-Host '   8  Set the update key (for a private GitHub repository)'
    Write-Host '   9  Uninstall AAGAM'
    Write-Host '  10  Back up my data'
    Write-Host '  11  Save a report for help'
    Write-Host '   0  Exit'
    Write-Host ''
    $choice = (Read-Host 'Type a number and press Enter').Trim()
    try {
        switch ($choice) {
            '1' { Invoke-Aagam @('open') }
            '2' { Invoke-Aagam @('update') }
            '3' { Invoke-Aagam @('update', '--apply', '--open') }
            '4' { Invoke-Aagam @('doctor') }
            '5' { & (Join-Path $PSScriptRoot 'install.ps1') -InstallDir $root }
            '6' { & (Join-Path $PSScriptRoot 'setup-windows.ps1') -RepairOnly -LocalAI }
            '7' { & (Join-Path $PSScriptRoot 'setup-windows.ps1') -RepairOnly -ConfigureClaude }
            '8' { Invoke-Aagam @('update', '--set-token') }
            '9' {
                & (Join-Path $PSScriptRoot 'uninstall.ps1')
                if ($LASTEXITCODE -eq 0) { return }  # removed: close at once, so the folder can go
            }
            '10' { Invoke-Aagam @('backup') }
            '11' { Invoke-Aagam @('support') }
            '0' { return }
            '' { continue }
            default { Write-Host "There is no choice $choice." }
        }
    } catch {
        Write-Host ''
        Write-Host "That didn't work: $($_.Exception.Message)"
    }
    Write-Host ''
    Read-Host 'Press Enter to go back to the menu' | Out-Null
}
