<#
The AAGAM Manager: one window to open, stop, update, check, repair, back up or remove AAGAM, and to choose whether it
starts with Windows and updates itself. It needs nothing but Windows (no Python), so it works even when AAGAM itself
won't start, which is when it is needed most. The "AAGAM Manager" shortcut on the desktop and in the Start menu opens
it; manage.cmd -Text gives the same choices as a numbered menu in a console.
#>
param(
    [switch]$Text,      # the numbered console menu instead of the window
    [switch]$SelfTest   # build the window and its state without showing it (the tests use this)
)
if ($Text) { & (Join-Path $PSScriptRoot 'manage.ps1'); exit $LASTEXITCODE }

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName Microsoft.VisualBasic
[System.Windows.Forms.Application]::EnableVisualStyles()

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
$record = Join-Path $root 'install.json'
$status = Join-Path $root '.update\status.json'
$port = if ($env:AAGAM_PORT) { [int]$env:AAGAM_PORT } else { 8765 }
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$userHome = [Environment]::GetEnvironmentVariable('AAGAM_HOME', 'User')
if ($env:AAGAM_HOME) { $data = $env:AAGAM_HOME } elseif ($userHome) { $data = $userHome } else { $data = Join-Path $env:USERPROFILE 'AAGAM' }
# Python's output in the log box: UTF-8 both ways, so the health check's marks come through.
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

# One Manager at a time.
$created = $false
$mutex = New-Object System.Threading.Mutex($true, 'Local\AAGAM-Manager', [ref]$created)
if (-not $created) {
    [System.Windows.Forms.MessageBox]::Show('The AAGAM Manager is already open.', 'AAGAM Manager') | Out-Null
    exit 0
}

# ------------------------------------------------------------------ what is true now

function Read-Json([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    try { return (Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json) } catch { return $null }
}

function Get-Version {
    $init = Join-Path $root 'src\aagam\__init__.py'
    if (-not (Test-Path $init)) { return '?' }
    $found = Select-String -Path $init -Pattern '__version__\s*=\s*"([^"]+)"'
    if ($found) { return $found.Matches[0].Groups[1].Value }
    return '?'
}

function Test-Running {
    $client = New-Object Net.Sockets.TcpClient
    try {
        $wait = $client.BeginConnect('127.0.0.1', $port, $null, $null)
        if (-not $wait.AsyncWaitHandle.WaitOne(250)) { return $false }
        $client.EndConnect($wait)
        return $true
    } catch { return $false } finally { $client.Close() }
}

function Get-Autostart {
    try {
        $value = (Get-ItemProperty -Path $runKey -Name 'AAGAM' -ErrorAction Stop).AAGAM
        return [string]$value -like "*$pythonw*"
    } catch { return $false }
}

function Set-Autostart([bool]$On) {
    if ($On) {
        if (-not (Test-Path $pythonw)) { throw "AAGAM's Python is missing. Choose Repair first." }
        New-ItemProperty -Path $runKey -Name 'AAGAM' -Value "`"$pythonw`" -m aagam serve" -PropertyType String -Force | Out-Null
    } elseif (Get-Autostart) {
        Remove-ItemProperty -Path $runKey -Name 'AAGAM' -ErrorAction SilentlyContinue
    }
}

function Get-AutoUpdate {
    $r = Read-Json $record
    if (-not $r) { return $false }
    if ($null -eq $r.auto_update) { return $true }
    return [bool]$r.auto_update
}

function Set-AutoUpdate([bool]$On) {
    $r = Read-Json $record
    if (-not $r) { throw 'This copy of AAGAM has no install record, so it does not update itself. Choose Repair to set it up.' }
    $r | Add-Member -NotePropertyName 'auto_update' -NotePropertyValue $On -Force
    # UTF-8 without a byte-order mark, as AAGAM writes it.
    [IO.File]::WriteAllText($record, ($r | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
}

function Get-UpdateLine {
    $r = Read-Json $record
    if (-not $r -or -not $r.repo) {
        if (Test-Path (Join-Path $root '.git')) { return 'A developer copy (git): it updates with Check for updates / Update now.' }
        return 'Updates are not set up for this copy. Repair sets them up.'
    }
    $s = Read-Json $status
    if ($s -and $s.status -eq 'applying') { return 'Updating now...' }
    if ($s -and $s.available) {
        $v = if ($s.latest -and $s.latest.version) { " ($($s.latest.version))" } else { '' }
        return "A new version is ready$v. Press Update now."
    }
    if ($s -and $s.error) { return "Last check: $($s.error)" }
    if ($s -and $s.checked_at) { return "Up to date (checked $(([datetime]$s.checked_at).ToString('d MMM, HH:mm')))." }
    return 'Not checked yet.'
}

# ------------------------------------------------------------------ the window

$font = New-Object Drawing.Font('Segoe UI', 10)
$form = New-Object Windows.Forms.Form
$form.Text = 'AAGAM Manager'
$form.Size = New-Object Drawing.Size(760, 700)
$form.MinimumSize = New-Object Drawing.Size(700, 600)
$form.StartPosition = 'CenterScreen'
$form.Font = $font
$form.BackColor = [Drawing.Color]::White

$title = New-Object Windows.Forms.Label
$title.Text = 'AAGAM'
$title.Font = New-Object Drawing.Font('Segoe UI', 18, [Drawing.FontStyle]::Bold)
$title.ForeColor = [Drawing.Color]::FromArgb(23, 64, 112)
$title.Location = New-Object Drawing.Point(20, 14)
$title.AutoSize = $true
$form.Controls.Add($title)

$subtitle = New-Object Windows.Forms.Label
$subtitle.Text = 'Open, update, check or repair AAGAM. Your documents are never changed here unless you say so.'
$subtitle.ForeColor = [Drawing.Color]::DimGray
$subtitle.Location = New-Object Drawing.Point(22, 52)
$subtitle.Size = New-Object Drawing.Size(700, 22)
$form.Controls.Add($subtitle)

$state = New-Object Windows.Forms.Label
$state.Font = New-Object Drawing.Font('Segoe UI', 11, [Drawing.FontStyle]::Bold)
$state.Location = New-Object Drawing.Point(22, 86)
$state.Size = New-Object Drawing.Size(700, 24)
$form.Controls.Add($state)

$about = New-Object Windows.Forms.Label
$about.Location = New-Object Drawing.Point(22, 112)
$about.Size = New-Object Drawing.Size(700, 22)
$about.ForeColor = [Drawing.Color]::DimGray
$form.Controls.Add($about)

$updateLine = New-Object Windows.Forms.Label
$updateLine.Location = New-Object Drawing.Point(22, 136)
$updateLine.Size = New-Object Drawing.Size(700, 22)
$form.Controls.Add($updateLine)

$startBox = New-Object Windows.Forms.CheckBox
$startBox.Text = 'Start AAGAM when I sign in to Windows (it waits quietly in the background)'
$startBox.Location = New-Object Drawing.Point(22, 166)
$startBox.Size = New-Object Drawing.Size(700, 24)
$form.Controls.Add($startBox)

$autoBox = New-Object Windows.Forms.CheckBox
$autoBox.Text = 'Install updates by themselves (when AAGAM is not in use)'
$autoBox.Location = New-Object Drawing.Point(22, 192)
$autoBox.Size = New-Object Drawing.Size(700, 24)
$form.Controls.Add($autoBox)

$buttons = New-Object Windows.Forms.TableLayoutPanel
$buttons.Location = New-Object Drawing.Point(18, 226)
$buttons.Size = New-Object Drawing.Size(710, 150)
$buttons.ColumnCount = 4
$buttons.RowCount = 3
foreach ($i in 0..3) { $buttons.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Percent, 25))) | Out-Null }
foreach ($i in 0..2) { $buttons.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Percent, 33.3))) | Out-Null }
$buttons.Anchor = 'Top, Left, Right'
$form.Controls.Add($buttons)

$logLabel = New-Object Windows.Forms.Label
$logLabel.Text = "What's happening"
$logLabel.Location = New-Object Drawing.Point(22, 384)
$logLabel.AutoSize = $true
$logLabel.ForeColor = [Drawing.Color]::DimGray
$form.Controls.Add($logLabel)

$log = New-Object Windows.Forms.TextBox
$log.Multiline = $true
$log.ReadOnly = $true
$log.ScrollBars = 'Vertical'
$log.WordWrap = $true
$log.BackColor = [Drawing.Color]::FromArgb(248, 248, 246)
$log.Font = New-Object Drawing.Font('Consolas', 9)
$log.Location = New-Object Drawing.Point(20, 406)
$log.Size = New-Object Drawing.Size(706, 200)
$log.Anchor = 'Top, Bottom, Left, Right'
$form.Controls.Add($log)

$bar = New-Object Windows.Forms.StatusStrip
$barText = New-Object Windows.Forms.ToolStripStatusLabel
$barText.Text = 'Ready'
$barText.Spring = $true
$barText.TextAlign = 'MiddleLeft'
$busy = New-Object Windows.Forms.ToolStripProgressBar
$busy.Style = 'Marquee'
$busy.Visible = $false
$bar.Items.AddRange(@($barText, $busy))
$form.Controls.Add($bar)

function Write-Log([string]$Line) {
    $log.AppendText(($Line -replace "`r?`n", "`r`n") + "`r`n")
}

# ------------------------------------------------------------------ doing things, one at a time, in the background

$script:job = $null
$allButtons = New-Object System.Collections.ArrayList

function Read-New([hashtable]$Job, [string]$Key) {
    $path = $Job[$Key]
    if (-not (Test-Path $path)) { return }
    $stream = [IO.File]::Open($path, 'Open', 'Read', 'ReadWrite')
    try {
        $stream.Seek($Job["$Key-pos"], 'Begin') | Out-Null
        $reader = New-Object IO.StreamReader($stream, [Text.Encoding]::UTF8)
        $text = $reader.ReadToEnd()
        $Job["$Key-pos"] = $stream.Position
    } finally { $stream.Close() }
    if ($text) {
        # Progress bars redraw a line with carriage returns: keep only what each line ends as.
        $lines = ($text -replace "`r`n", "`n") -split "`n" | ForEach-Object { ($_ -split "`r")[-1] } | Where-Object { $_.Trim() }
        foreach ($line in $lines) { Write-Log $line }
    }
}

function Start-Action([string]$Name, [string]$File, [string[]]$Arguments, [scriptblock]$After = $null) {
    if ($script:job) { return }
    if (-not (Test-Path $File) -and $File -notmatch '^(powershell|explorer)') {
        Write-Log "AAGAM's Python is missing, so '$Name' can't run. Choose Repair first."
        return
    }
    $out = [IO.Path]::GetTempFileName()
    $err = [IO.Path]::GetTempFileName()
    Write-Log ''
    Write-Log "== $Name"
    try {
        $process = Start-Process -FilePath $File -ArgumentList $Arguments -WorkingDirectory $root -WindowStyle Hidden `
            -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
        $null = $process.Handle  # held now, or PowerShell can't tell the exit code once it has finished
    } catch {
        Write-Log "It didn't start: $($_.Exception.Message)"
        return
    }
    $script:job = @{ Name = $Name; Process = $process; Out = $out; Err = $err; 'Out-pos' = 0L; 'Err-pos' = 0L; After = $After }
    foreach ($b in $allButtons) { $b.Enabled = $false }
    $barText.Text = "Working: $Name..."
    $busy.Visible = $true
}

function Stop-Waiting {
    $job = $script:job
    $job.Process.WaitForExit()
    Read-New $job 'Out'
    Read-New $job 'Err'
    $code = $job.Process.ExitCode
    if ($code -eq 0) { Write-Log 'Done.' } else { Write-Log "It stopped with a problem (code $code). The lines above say what happened." }
    Remove-Item $job.Out, $job.Err -Force -ErrorAction SilentlyContinue
    $script:job = $null
    foreach ($b in $allButtons) { $b.Enabled = $true }
    $barText.Text = 'Ready'
    $busy.Visible = $false
    Update-State
    if ($job.After) { & $job.After $code }
}

function Invoke-Aagam([string]$Name, [string[]]$Arguments, [scriptblock]$After = $null) {
    Start-Action $Name $python (@('-m', 'aagam') + $Arguments) $After
}

function Invoke-Script([string]$Name, [string]$Script, [string[]]$Arguments, [scriptblock]$After = $null) {
    $path = Join-Path $PSScriptRoot $Script
    Start-Action $Name 'powershell.exe' (@('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$path`"") + $Arguments) $After
}

function Open-Aagam {
    if (-not (Test-Path $pythonw)) { Write-Log "AAGAM's Python is missing. Choose Repair first."; return }
    Write-Log ''
    Write-Log '== Open AAGAM'
    Write-Log 'Opening AAGAM in your browser (the first start after installing or updating can take up to a minute).'
    Start-Process -FilePath $pythonw -ArgumentList '-m', 'aagam' -WorkingDirectory $root | Out-Null
}

function Stop-Aagam {
    Write-Log ''
    Write-Log '== Stop AAGAM'
    if (-not (Test-Running)) { Write-Log 'AAGAM is not running.'; return }
    try {
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$port/api/system/shutdown" -Headers @{ 'X-AAGAM' = '1' } -TimeoutSec 5 | Out-Null
        Write-Log 'AAGAM is closing. (Documents being read are picked up again next time.)'
    } catch {
        Write-Log "AAGAM didn't answer: $($_.Exception.Message)"
    }
}

function Add-Button([string]$Label, [string]$Tip, [scriptblock]$Click) {
    $b = New-Object Windows.Forms.Button
    $b.Text = $Label
    $b.Dock = 'Fill'
    $b.Margin = New-Object Windows.Forms.Padding(4)
    $b.FlatStyle = 'System'
    $b.Add_Click($Click)
    $tips.SetToolTip($b, $Tip)
    $buttons.Controls.Add($b) | Out-Null
    $allButtons.Add($b) | Out-Null
}

$tips = New-Object Windows.Forms.ToolTip
Add-Button 'Open AAGAM' 'Start AAGAM if it is closed, and open it in your browser.' { Open-Aagam }
Add-Button 'Stop AAGAM' 'Close AAGAM (the server in the background).' { Stop-Aagam; Start-Sleep -Milliseconds 800; Update-State }
Add-Button 'Check for updates' 'Ask GitHub whether there is a newer version, and what changed.' { Invoke-Aagam 'Check for updates' @('update') }
Add-Button 'Update now' 'Put the newest version in place. AAGAM closes for a minute and opens again.' { Invoke-Aagam 'Update now' @('update', '--apply', '--open') }
Add-Button 'Health check' 'Check this computer: Python, data, the window, scanned-page reading, browser, local AI, Claude Desktop, disk.' { Invoke-Aagam 'Health check' @('doctor') }
Add-Button 'Repair' 'Fetch a fresh copy of AAGAM from GitHub (the newest version) and set everything up again: its Python, packages, data folder and shortcuts. Without internet it uses the copy here. Your documents and records are kept.' {
    # The installer closes AAGAM itself, keeps a copy to put back if anything fails, and starts it again afterwards.
    Invoke-Script 'Repair' 'install.ps1' @('-InstallDir', "`"$root`"", '-NoOpen', '-NoLocalAI', '-NoClaude')
}
Add-Button 'Local AI' 'Install or repair the local AI (Ollama and its model, a few GB the first time).' {
    Invoke-Script 'Install or repair the local AI' 'setup-windows.ps1' @('-RepairOnly', '-LocalAI')
}
Add-Button 'Claude Desktop' 'Connect AAGAM to Claude Desktop (then quit and reopen Claude Desktop).' {
    Invoke-Script 'Connect Claude Desktop' 'setup-windows.ps1' @('-RepairOnly', '-ConfigureClaude')
}
Add-Button 'Back up my data' 'Copy your documents and records to Documents\AAGAM backups.' { Invoke-Aagam 'Back up my data' @('backup') }
Add-Button 'Report for help' 'Save a report on the Desktop to send when you need help (no documents, no keys).' { Invoke-Aagam 'Save a report for help' @('support') }
Add-Button 'Open data folder' "Open $data in File Explorer." {
    if (Test-Path $data) { Start-Process explorer.exe $data } else { Write-Log "There is no data folder at $data yet." }
}
Add-Button 'Uninstall' 'Remove AAGAM from this computer. Your documents are kept unless you choose otherwise.' {
    $answer = [Windows.Forms.MessageBox]::Show(
        "Remove AAGAM from this computer?`r`n`r`nYour documents and records in $data are KEPT.`r`n(Choose No to keep AAGAM.)",
        'Uninstall AAGAM', 'YesNo', 'Question')
    if ($answer -ne 'Yes') { return }
    $alsoData = [Windows.Forms.MessageBox]::Show(
        "Also DELETE your data folder, with every document and record in it?`r`n`r`n$data`r`n`r`nChoose No to keep it (recommended).",
        'Uninstall AAGAM', 'YesNo', 'Warning', 'Button2')
    $arguments = @('-Quiet', '-Port', "$port")
    if ($alsoData -eq 'Yes') {
        $typed = [Microsoft.VisualBasic.Interaction]::InputBox('To delete the data folder as well, type REMOVE. Anything else keeps it.', 'Uninstall AAGAM', '')
        if ($typed -eq 'REMOVE') { $arguments += @('-RemoveData', '-Confirm', 'REMOVE') } else { Write-Log 'The data folder will be kept.' }
    }
    Invoke-Script 'Uninstall AAGAM' 'uninstall.ps1' $arguments {
        param($code)
        if ($code -eq 0) {
            [Windows.Forms.MessageBox]::Show('AAGAM is removed from this computer.', 'AAGAM Manager') | Out-Null
            $form.Close()
        }
    }
}

# ------------------------------------------------------------------ keeping the window in step

$script:quiet = $false
function Update-State {
    $running = Test-Running
    if ($running) {
        $state.Text = [string][char]0x25CF + '  AAGAM is running'
        $state.ForeColor = [Drawing.Color]::FromArgb(22, 128, 61)
    } else {
        $state.Text = [string][char]0x25CB + '  AAGAM is not running'
        $state.ForeColor = [Drawing.Color]::DimGray
    }
    $r = Read-Json $record
    $from = if ($r -and $r.repo) { " - updates from github.com/$($r.repo)" + $(if ($r.branch) { " ($($r.branch))" } else { '' }) } else { '' }
    $about.Text = "Version $(Get-Version)$from"
    $updateLine.Text = Get-UpdateLine
    $script:quiet = $true
    $startBox.Checked = Get-Autostart
    $startBox.Enabled = Test-Path $pythonw
    $autoBox.Checked = Get-AutoUpdate
    $autoBox.Enabled = [bool]($r -and $r.repo)
    $script:quiet = $false
}

$startBox.Add_CheckedChanged({
    if ($script:quiet) { return }
    try {
        Set-Autostart $startBox.Checked
        if ($startBox.Checked) { Write-Log 'AAGAM will start in the background when you sign in to Windows.' }
        else { Write-Log 'AAGAM will no longer start by itself; open it from the AAGAM shortcut.' }
    } catch { Write-Log "That didn't work: $($_.Exception.Message)" }
    Update-State
})

$autoBox.Add_CheckedChanged({
    if ($script:quiet) { return }
    try {
        Set-AutoUpdate $autoBox.Checked
        if ($autoBox.Checked) { Write-Log 'Updates will be installed by themselves while AAGAM is not in use.' }
        else { Write-Log 'Updates will wait for you: press Update now when it suits you.' }
    } catch { Write-Log "That didn't work: $($_.Exception.Message)" }
    Update-State
})

$timer = New-Object Windows.Forms.Timer
$timer.Interval = 500
$script:ticks = 0
$timer.Add_Tick({
    try {
        if ($script:job) {
            Read-New $script:job 'Out'
            Read-New $script:job 'Err'
            if ($script:job.Process.HasExited) { Stop-Waiting }
        }
        $script:ticks += 1
        if ($script:ticks % 6 -eq 0 -and -not $script:job) { Update-State }  # every three seconds
    } catch {
        Write-Log "(The Manager hit a snag: $($_.Exception.Message))"
    }
})

$form.Add_Shown({
    Update-State
    Write-Log "Program folder: $root"
    Write-Log "Your data:      $data"
    if (-not (Test-Path $python)) { Write-Log "AAGAM's Python environment is missing: choose Repair." }
    $timer.Start()
})
$form.Add_FormClosing({
    if ($script:job -and -not $script:job.Process.HasExited) {
        $answer = [Windows.Forms.MessageBox]::Show("'$($script:job.Name)' is still running. It carries on if you close this window. Close anyway?",
            'AAGAM Manager', 'YesNo', 'Question')
        if ($answer -ne 'Yes') { $_.Cancel = $true }
    }
})

if ($SelfTest) {
    Update-State
    Write-Output "buttons=$($allButtons.Count) state=$($state.Text) version=$($about.Text) updates=$($updateLine.Text) autostart=$($startBox.Checked) auto=$($autoBox.Checked)"
    if ($env:AAGAM_MANAGER_SNAPSHOT) {
        # A picture of the window, for checking its layout without showing it on screen.
        $form.Opacity = 0
        $form.Show()
        Write-Log 'Program folder and data folder are listed here when the Manager opens.'
        $picture = New-Object Drawing.Bitmap($form.Width, $form.Height)
        $form.DrawToBitmap($picture, (New-Object Drawing.Rectangle(0, 0, $form.Width, $form.Height)))
        $picture.Save($env:AAGAM_MANAGER_SNAPSHOT)
        $form.Hide()
    }
    if ($env:AAGAM_MANAGER_RUN -eq 'doctor') {
        # The Health check button's path: a background process, its output read into the log box as it comes.
        Invoke-Aagam 'Health check' @('doctor')
        $deadline = (Get-Date).AddMinutes(2)
        while ($script:job -and (Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 300
            Read-New $script:job 'Out'
            Read-New $script:job 'Err'
            if ($script:job.Process.HasExited) { Stop-Waiting }
        }
        Write-Output $log.Text
    }
    $form.Dispose()
    $mutex.ReleaseMutex()
    exit 0
}
[Windows.Forms.Application]::Run($form)
$timer.Stop()
$mutex.ReleaseMutex()
