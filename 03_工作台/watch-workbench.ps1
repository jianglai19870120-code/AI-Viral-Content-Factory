[CmdletBinding()]
param(
    [int]$Port = 8766,
    [int]$IntervalSeconds = 10,
    [string]$RuntimePath = (Join-Path $env:LOCALAPPDATA 'AI-Viral-Content-Factory\workbench')
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$runtime = $RuntimePath
$log = Join-Path $runtime 'watchdog.log'
$watchdogStatePath = Join-Path $runtime 'watchdog-state.json'
$trace = Join-Path $runtime 'scheduled-watchdog.log'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
Add-Content -LiteralPath $trace -Encoding utf8 -Value "$(Get-Date -Format 'o') watchdog entered pid=$PID runtime=$runtime"
$mutex = New-Object System.Threading.Mutex($false, 'Local\AI-Viral-Content-Factory-Workbench-Watchdog')

function Write-AtomicJson([string]$Path, [object]$Value) {
    # The named mutex guarantees one writer. Direct UTF-8 BOM output avoids
    # Move-Item inconsistencies from the Task Scheduler process context.
    $json = $Value | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($Path, $json, [System.Text.UTF8Encoding]::new($true))
}

function Rotate-WatchdogLog {
    if (-not (Test-Path -LiteralPath $log)) { return }
    if ((Get-Item -LiteralPath $log).Length -lt 1MB) { return }
    Move-Item -LiteralPath $log -Destination "$log.$(Get-Date -Format 'yyyyMMdd-HHmmss')" -ErrorAction Stop
}

function Get-WorkbenchHealth {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
        if ($response.service -eq 'ai-viral-workbench' -and [int]$response.port -eq $Port) { return $response }
    } catch { }
    return $null
}

function Write-WatchdogState([string]$Status, [string]$Message = '', [object]$Health = $null) {
    Write-AtomicJson $watchdogStatePath ([pscustomobject]@{
        pid = $PID
        port = $Port
        checkedAt = (Get-Date).ToString('o')
        status = $Status
        message = $Message
        instanceId = if ($Health) { $Health.instanceId } else { '' }
        serviceStartedAt = if ($Health) { $Health.startedAt } else { '' }
    })
}

$acquiredMutex = $mutex.WaitOne(0)
if (-not $acquiredMutex) {
    Add-Content -LiteralPath $trace -Encoding utf8 -Value "$(Get-Date -Format 'o') watchdog exited because mutex is already owned"
    exit 0
}
Add-Content -LiteralPath $trace -Encoding utf8 -Value "$(Get-Date -Format 'o') watchdog acquired mutex"
try {
    while ($true) {
        Rotate-WatchdogLog
        $health = Get-WorkbenchHealth
        if ($health) {
            Write-WatchdogState 'healthy' '' $health
            Start-Sleep -Seconds $IntervalSeconds
            continue
        }

        try {
            Write-WatchdogState 'starting' 'Health endpoint is unavailable; starting workbench.'
            & (Join-Path $root 'start-workbench.ps1') -Port $Port -RuntimePath $runtime
            $health = Get-WorkbenchHealth
            if (-not $health) { throw 'Workbench launcher returned without a valid health response.' }
            Write-WatchdogState 'healthy' '' $health
        } catch {
            $message = $_.Exception.Message
            $status = if ($message -match 'occupied by PID') { 'blocked' } else { 'failed' }
            Add-Content -LiteralPath $trace -Encoding utf8 -Value "$(Get-Date -Format 'o') watchdog cycle failed: $message"
            Add-Content -LiteralPath $log -Encoding utf8 -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') watchdog [$status]: $message"
            Write-WatchdogState $status $message
        }
        Start-Sleep -Seconds $IntervalSeconds
    }
} finally {
    Write-WatchdogState 'stopped' 'Watchdog process ended.'
    $mutex.ReleaseMutex() | Out-Null
    $mutex.Dispose()
}
