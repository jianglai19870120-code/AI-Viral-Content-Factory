[CmdletBinding()]
param(
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$taskName = 'AI Viral Content Factory Workbench Service'
$desktopBridgeTaskName = 'AI Viral Content Factory Desktop Bridge'
$legacyTaskName = 'AI Viral Content Factory Workbench Watchdog'
$root = $PSScriptRoot
$runtime = Join-Path $env:ProgramData 'AI-Viral-Content-Factory\workbench'
$configPath = Join-Path $runtime 'workbench-launcher.json'
$watchdogStatePath = Join-Path $runtime 'watchdog-state.json'
$watcher = Join-Path $root 'watch-workbench.ps1'
$taskRunner = Join-Path $root 'run-workbench-watchdog.ps1'
$pythonWatchdog = Join-Path $root 'scripts\watch_workbench.py'
$detachedLauncher = Join-Path $root 'launch-workbench-watchdog.ps1'
$powerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$startupEntry = Join-Path ([Environment]::GetFolderPath('Startup')) 'AI爆款内容工厂工作台.cmd'
$installStatePath = Join-Path $runtime 'watchdog-install-state.json'

function Get-WorkbenchHealth {
    try {
        $response = Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/health' -TimeoutSec 3
        if ($response.service -eq 'ai-viral-workbench' -and [int]$response.port -eq 8766) { return $response }
    } catch { }
    return $null
}

function Write-InstallState([string]$Status, [string]$Message, [bool]$ScheduledTaskInstalled) {
    [pscustomobject]@{
        checkedAt = (Get-Date).ToString('o')
        status = $Status
        message = $Message
        scheduledTaskInstalled = $ScheduledTaskInstalled
        taskName = $taskName
        startupEntry = $startupEntry
        runtimePath = $runtime
    } | ConvertTo-Json | Set-Content -LiteralPath $installStatePath -Encoding utf8
}

function Stop-ExistingWorkbenchWatchdog {
    if (-not (Test-Path -LiteralPath $watchdogStatePath)) { return }
    try { $state = Get-Content -LiteralPath $watchdogStatePath -Raw | ConvertFrom-Json } catch { return }
    if (-not $state.pid) { return }

    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$state.pid)" -ErrorAction SilentlyContinue
    # Only take over the exact watchdog script recorded by its own heartbeat.
    if (-not $process -or $process.Name -ne 'powershell.exe' -or $process.CommandLine -notlike "*$watcher*") { return }

    Stop-Process -Id ([int]$state.pid) -Force -ErrorAction Stop
    $deadline = (Get-Date).AddSeconds(5)
    while ((Get-Date) -lt $deadline -and (Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue)) {
        Start-Sleep -Milliseconds 200
    }
}

function Stop-ExistingWorkbenchService {
    $serviceStatePath = Join-Path $runtime 'workbench-service.json'
    if (-not (Test-Path -LiteralPath $serviceStatePath)) { return }
    try { $state = Get-Content -LiteralPath $serviceStatePath -Raw | ConvertFrom-Json } catch { return }
    if (-not $state.pid -or [int]$state.port -ne 8766) { return }

    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$state.pid)" -ErrorAction SilentlyContinue
    # State alone is not enough authority to stop a process. Only replace the
    # service when it is the expected Python server for this fixed workbench port.
    if (-not $process -or $process.Name -ne 'python.exe' -or $process.CommandLine -notlike '*server.py*' -or $process.CommandLine -notlike '*--port 8766*') { return }

    Stop-Process -Id ([int]$state.pid) -Force -ErrorAction Stop
    $deadline = (Get-Date).AddSeconds(5)
    while ((Get-Date) -lt $deadline -and (Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue)) {
        Start-Sleep -Milliseconds 200
    }
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $legacyTaskName -Confirm:$false -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $desktopBridgeTaskName -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $startupEntry -Force -ErrorAction SilentlyContinue
    Write-InstallState 'removed' 'Removed workbench login startup entries.' $false
    Write-Output "Removed workbench login startup entries."
    exit 0
}

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $python -or -not (Test-Path -LiteralPath $python.Source)) {
    throw 'Python runtime is unavailable. Install Python or add python.exe to PATH before installing the workbench watchdog.'
}
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$existingLauncher = $null
if (Test-Path -LiteralPath $configPath) {
    try { $existingLauncher = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json } catch { }
}
# The watcher can hold this configuration open while it is healthy. Reuse a
# valid existing launcher instead of failing an otherwise idempotent install.
if (-not $existingLauncher -or -not (Test-Path -LiteralPath $existingLauncher.pythonPath)) {
    [pscustomobject]@{
        schema = 'workbench-launcher-v1'
        projectRoot = $root
        pythonPath = [string]$python.Source
        runtimePath = $runtime
        port = 8766
        installedAt = (Get-Date).ToString('o')
    } | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding Unicode
}

$startupCommand = @(
    '@echo off'
    "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$detachedLauncher`""
)
# Windows PowerShell reads the current user's Startup .cmd with the active ANSI
# code page. Keeping this file in that encoding preserves the Chinese project path.
$expectedStartupContent = $startupCommand -join [Environment]::NewLine
$existingStartupContent = if (Test-Path -LiteralPath $startupEntry) {
    Get-Content -LiteralPath $startupEntry -Raw -ErrorAction SilentlyContinue
} else {
    $null
}
if ($existingStartupContent -ne $expectedStartupContent -and $existingStartupContent -ne ($expectedStartupContent + [Environment]::NewLine)) {
    $startupCommand | Set-Content -LiteralPath $startupEntry -Encoding Default
}

$argument = "-u `"$pythonWatchdog`" --root `"$root`" --runtime `"$runtime`" --python `"$($python.Source)`" --port 8766"
$action = New-ScheduledTaskAction -Execute $python.Source -Argument $argument -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Days 3650) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Runs the local AI Viral Content Factory workbench independently of the Codex user process.'
$scheduledTaskInstalled = $false
try {
    $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existingTask -and $existingTask.State -eq 'Running') {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction Stop
        $stopDeadline = (Get-Date).AddSeconds(5)
        do {
            Start-Sleep -Milliseconds 200
            $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
        } while ($existingTask.State -eq 'Running' -and (Get-Date) -lt $stopDeadline)
        if ($existingTask.State -eq 'Running') {
            throw 'Existing scheduled watchdog instance did not stop.'
        }
    }
    Register-ScheduledTask -TaskName $taskName -InputObject $task -Force -ErrorAction Stop | Out-Null
    Stop-ExistingWorkbenchWatchdog
    Stop-ExistingWorkbenchService
    Start-ScheduledTask -TaskName $taskName -ErrorAction Stop
    $deadline = (Get-Date).AddSeconds(8)
    do {
        Start-Sleep -Milliseconds 300
        $registeredTask = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
    } while ($registeredTask.State -ne 'Running' -and (Get-Date) -lt $deadline)
    if ($registeredTask.State -ne 'Running') {
        throw "Scheduled task did not retain the watchdog process (state: $($registeredTask.State))."
    }
    $healthDeadline = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 400
        $health = Get-WorkbenchHealth
    } while (-not $health -and (Get-Date) -lt $healthDeadline)
    if (-not $health) {
        throw 'Scheduled task started, but the workbench health endpoint did not become available within 20 seconds.'
    }
    $taskXml = Export-ScheduledTask -TaskName $taskName
    $registeredTask = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
    # Prefer the Task Scheduler object model over XML formatting. Windows can
    # serialize LocalSystem as SYSTEM, NT AUTHORITY\\SYSTEM, or S-1-5-18.
    $principalId = [string]$registeredTask.Principal.UserId
    $isSystemPrincipal = $principalId -match '^(SYSTEM|S-1-5-18|NT AUTHORITY\\SYSTEM)$'
    $hasBootTrigger = $taskXml -match '<BootTrigger(?:\s[^>]*)?>'
    if (-not $isSystemPrincipal -or -not $hasBootTrigger) {
        throw "Scheduled task validation failed (principal='$principalId'; bootTrigger=$hasBootTrigger)."
    }
    Unregister-ScheduledTask -TaskName $legacyTaskName -Confirm:$false -ErrorAction SilentlyContinue
    $scheduledTaskInstalled = $true
} catch {
    $scheduledTaskError = $_.Exception.Message
    Write-Warning "Scheduled Task registration was unavailable: $scheduledTaskError"
}

if (-not $scheduledTaskInstalled) {
    # Keep a login fallback, but do not treat it as restart-proof: only a
    # registered Task Scheduler task is independent from Codex's job object.
    & $detachedLauncher
    Write-InstallState 'needs-admin' "Task Scheduler was unavailable: $scheduledTaskError" $false
    Write-Warning "Startup-folder fallback was refreshed, but it cannot guarantee survival across a Codex restart. Run 安装并验证工作台守护.cmd and approve UAC."
} else {
    # The watchdog service runs as SYSTEM for resilience, but desktop UI must
    # be opened from the currently signed-in Windows session. Start that small
    # bridge now; the Startup entry above starts it again after future logins.
    $desktopBridgeAgent = Join-Path $root 'scripts\codex_desktop_bridge_agent.py'
    if (Test-Path -LiteralPath $desktopBridgeAgent) {
        $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $desktopAction = New-ScheduledTaskAction -Execute $python.Source -Argument "-B -u `"$desktopBridgeAgent`" --port 8766" -WorkingDirectory $root
        $desktopTrigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
        $desktopPrincipal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
        $desktopSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Days 3650)
        $desktopTask = New-ScheduledTask -Action $desktopAction -Trigger $desktopTrigger -Principal $desktopPrincipal -Settings $desktopSettings -Description 'Runs the local folder and Codex bridge in the signed-in interactive desktop.'
        Register-ScheduledTask -TaskName $desktopBridgeTaskName -InputObject $desktopTask -Force -ErrorAction Stop | Out-Null
        Start-ScheduledTask -TaskName $desktopBridgeTaskName -ErrorAction Stop
    }
    Write-InstallState 'installed' 'Scheduled task registered and started successfully.' $true
    Write-Output "Installed and started scheduled task: $taskName"
}
