param(
    [ValidateSet('status', 'stop', 'restart', 'diagnose', 'install', 'uninstall')]
    [string]$Mode = 'status'
)

$ErrorActionPreference = 'Stop'
$port = 8766
$staleAfterSeconds = 30
$taskName = 'AI Viral Content Factory Workbench Service'
$root = $PSScriptRoot
$runtime = Join-Path $env:ProgramData 'AI-Viral-Content-Factory\workbench'
$watchdogStatePath = Join-Path $runtime 'watchdog-state.json'
$serviceStatePath = Join-Path $runtime 'workbench-service.json'
$installStatePath = Join-Path $runtime 'watchdog-install-state.json'
$startupEntry = Join-Path ([Environment]::GetFolderPath('Startup')) 'AI爆款内容工厂工作台.cmd'

function Get-WorkbenchHealth {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 3
        if ($response.service -eq 'ai-viral-workbench' -and [int]$response.port -eq $port) { return $response }
    } catch { }
    return $null
}

function Get-WorkbenchListener {
    try {
        $connection = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -First 1
        if ($connection) { return [pscustomobject]@{ OwningProcess = [int]$connection.OwningProcess } }
    } catch { }
    # Get-NetTCPConnection can omit ownership for a non-elevated shell. Netstat
    # still exposes the local listener and keeps restart/diagnose deterministic.
    $line = netstat.exe -ano -p tcp | Where-Object {
        $_ -match "^\s*TCP\s+127\.0\.0\.1:$port\s+\S+\s+LISTENING\s+\d+\s*$"
    } | Select-Object -First 1
    if ($line -and $line -match 'LISTENING\s+(\d+)\s*$') {
        return [pscustomobject]@{ OwningProcess = [int]$matches[1] }
    }
    return $null
}

function Get-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { return $null }
}

function Get-WatchdogReport {
    $saved = Get-JsonFile $watchdogStatePath
    if (-not $saved) {
        return [pscustomobject]@{ status = 'not-started'; fresh = $false; ageSeconds = $null; message = 'No watchdog heartbeat has been recorded.' }
    }
    $age = [math]::Round(((Get-Date) - [datetimeoffset]::Parse($saved.checkedAt).LocalDateTime).TotalSeconds, 1)
    $alive = Get-Process -Id $saved.pid -ErrorAction SilentlyContinue
    $fresh = $age -le $staleAfterSeconds -and $null -ne $alive
    return [pscustomobject]@{
        status = if ($fresh) { $saved.status } else { 'stale' }
        fresh = $fresh
        ageSeconds = $age
        pid = $saved.pid
        checkedAt = $saved.checkedAt
        message = if ($fresh) { $saved.message } else { 'Watchdog heartbeat is older than 30 seconds or its process is no longer running.' }
    }
}

function Get-SystemPythonWatchdog {
    # SYSTEM-owned processes intentionally hide command lines from a normal
    # administrator token. A Python child of the Task Scheduler service is
    # the reliable process-level signal for the production watchdog.
    foreach ($process in Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)" -ErrorAction SilentlyContinue
        if (-not $parent -or $parent.Name -ne 'svchost.exe') { continue }

        $owner = Invoke-CimMethod -InputObject $process -MethodName GetOwner -ErrorAction SilentlyContinue
        $isSystem = $owner -and $owner.ReturnValue -eq 0 -and $owner.User -eq 'SYSTEM'
        $isProtected = $owner -and $owner.ReturnValue -ne 0
        if ($isSystem -or $isProtected) {
            return [pscustomobject]@{
                pid = [int]$process.ProcessId
                parentPid = [int]$process.ParentProcessId
                startedAt = $process.CreationDate
            }
        }
    }
    return $null
}

if ($Mode -eq 'install') {
    & (Join-Path $root 'install-workbench-watchdog.ps1')
    exit $LASTEXITCODE
}
if ($Mode -eq 'uninstall') {
    & (Join-Path $root 'install-workbench-watchdog.ps1') -Uninstall
    exit $LASTEXITCODE
}

$health = Get-WorkbenchHealth
$listener = Get-WorkbenchListener

if ($Mode -eq 'restart') {
    if ($health -and $listener) {
        Stop-Process -Id $listener.OwningProcess -Force
        Start-Sleep -Milliseconds 800
    }
    & (Join-Path $root 'start-workbench.ps1') -Port $port
    exit $LASTEXITCODE
}

if ($Mode -eq 'stop') {
    if (-not $health -or -not $listener) {
        Write-Output '{"status":"stopped","message":"工作台当前未运行。"}'
        exit 0
    }
    $serviceState = Get-JsonFile $serviceStatePath
    # Only stop a listener that has authenticated as this workbench and whose
    # persisted state points at the live listener. This never kills another
    # program merely because it happens to use port 8766.
    if ($serviceState -and $serviceState.pid -and [int]$serviceState.pid -ne [int]$listener.OwningProcess) {
        throw "工作台状态文件与监听进程不一致，拒绝停止 PID $($listener.OwningProcess)。"
    }
    Stop-Process -Id $listener.OwningProcess -Force -ErrorAction Stop
    Write-Output (ConvertTo-Json ([pscustomobject]@{ status = 'stopped'; pid = $listener.OwningProcess; url = "http://127.0.0.1:$port" }))
    exit 0
}

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$taskInfo = if ($task) { Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue } else { $null }
$installState = Get-JsonFile $installStatePath
$watchdog = Get-WatchdogReport
$systemWatchdog = Get-SystemPythonWatchdog
if (($task -and $task.State -eq 'Running' -or $systemWatchdog) -and -not $watchdog.fresh) {
    # Python owns the production scheduled task. Ignore the stale heartbeat
    # left by the retired PowerShell fallback after a successful task takeover.
    $watchdog = [pscustomobject]@{
        status = 'healthy'
        fresh = $true
        ageSeconds = $null
        pid = if ($systemWatchdog) { $systemWatchdog.pid } else { $null }
        checkedAt = $null
        message = 'SYSTEM Python watchdog is running; legacy PowerShell heartbeat is ignored.'
    }
}
$reportService = Get-JsonFile $serviceStatePath
if ($health -and $listener -and (-not $reportService -or [int]$reportService.pid -ne [int]$listener.OwningProcess)) {
    # The SYSTEM watchdog may be unable to replace a user-owned state file,
    # so prefer the authenticated health payload and live listener PID.
    $reportService = [pscustomobject]@{
        pid = $listener.OwningProcess
        port = $port
        pythonPath = $null
        startedAt = $health.startedAt
        status = 'healthy'
        instanceId = $health.instanceId
        stdout = $null
        stderr = $null
    }
}
$report = [pscustomobject]@{
    url = "http://127.0.0.1:$port"
    health = if ($health) { $health.status } else { 'unavailable' }
    listenerPid = if ($listener) { $listener.OwningProcess } else { $null }
    service = $reportService
    watchdog = $watchdog
    scheduledTask = if ($task) { [pscustomobject]@{ name = $taskName; state = [string]$task.State; lastRunTime = $taskInfo.LastRunTime; lastTaskResult = $taskInfo.LastTaskResult } } elseif ($systemWatchdog) { [pscustomobject]@{ name = $taskName; state = 'running (SYSTEM process verified)'; lastRunTime = $systemWatchdog.startedAt; lastTaskResult = $null } } elseif ($installState -and $installState.status -eq 'installed' -and $installState.scheduledTaskInstalled) { [pscustomobject]@{ name = $taskName; state = 'registered (elevated installer verified)'; lastRunTime = $installState.checkedAt; lastTaskResult = $null } } else { $null }
    startupEntry = if (Test-Path -LiteralPath $startupEntry) { $startupEntry } else { $null }
    logs = [pscustomobject]@{
        stdout = if ($reportService.stdout) { $reportService.stdout } else { (Join-Path $runtime 'server-8766*.out.log') }
        stderr = if ($reportService.stderr) { $reportService.stderr } else { (Join-Path $runtime 'server-8766*.err.log') }
        watchdog = (Join-Path $runtime 'python-watchdog.log')
    }
}
if ($Mode -eq 'status' -and -not $health) {
    $report | ConvertTo-Json -Depth 8
    exit 2
}
$report | ConvertTo-Json -Depth 8
