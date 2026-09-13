[CmdletBinding()]
param(
    [int]$Port = 8766,
    [int]$WaitSeconds = 20,
    [string]$RuntimePath = (Join-Path $env:LOCALAPPDATA 'AI-Viral-Content-Factory\workbench')
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$root = $PSScriptRoot
$runtime = $RuntimePath
$configPath = Join-Path $runtime 'workbench-launcher.json'
$serviceStatePath = Join-Path $runtime 'workbench-service.json'
$runId = "$(Get-Date -Format 'yyyyMMdd-HHmmss')-$PID"
# Each Codex run can use a different Windows sandbox identity. Never reuse an
# old redirected log handle, because that can make a healthy server impossible
# to start after Codex restarts.
$stdout = Join-Path $runtime "server-$Port-$runId.out.log"
$stderr = Join-Path $runtime "server-$Port-$runId.err.log"

function Write-AtomicJson([string]$Path, [object]$Value) {
    $temporary = "$Path.$PID.tmp"
    $Value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Rotate-WorkbenchLog([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    if ((Get-Item -LiteralPath $Path).Length -lt 2MB) { return }
    Move-Item -LiteralPath $Path -Destination "$Path.$(Get-Date -Format 'yyyyMMdd-HHmmss')" -ErrorAction Stop
}

function Get-WorkbenchHealth {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
        if ($response.service -eq 'ai-viral-workbench' -and [int]$response.port -eq $Port) { return $response }
    } catch { }
    return $null
}

function Get-PythonRuntime {
    if (Test-Path -LiteralPath $configPath) {
        try {
            $saved = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
            if ($saved.pythonPath -and (Test-Path -LiteralPath $saved.pythonPath)) { return [string]$saved.pythonPath }
        } catch { }
    }
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $command -or -not (Test-Path -LiteralPath $command.Source)) {
        throw 'Python runtime is unavailable. Run install-workbench-watchdog.ps1 to configure a valid Python path.'
    }
    return [string]$command.Source
}

New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$env:AI_VIRAL_WORKBENCH_RUNTIME = $runtime
if (Get-WorkbenchHealth) { exit 0 }

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    throw "Port $Port is occupied by PID $($listener.OwningProcess), but it is not the AI Viral Content Factory workbench. The launcher will not change ports."
}

$python = Get-PythonRuntime
Rotate-WorkbenchLog $stdout
Rotate-WorkbenchLog $stderr
$process = Start-Process -FilePath $python `
    -ArgumentList @('-u', 'server.py', '--port', $Port, '--no-browser') `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

Write-AtomicJson $serviceStatePath ([pscustomobject]@{
    pid = $process.Id
    port = $Port
        pythonPath = $python
        startedAt = (Get-Date).ToString('o')
        status = 'starting'
        stdout = $stdout
        stderr = $stderr
})

$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 400
    $health = Get-WorkbenchHealth
    if ($health) {
        Write-AtomicJson $serviceStatePath ([pscustomobject]@{
            pid = $process.Id
            port = $Port
            pythonPath = $python
            startedAt = (Get-Date).ToString('o')
            status = 'healthy'
            instanceId = $health.instanceId
            stdout = $stdout
            stderr = $stderr
        })
        exit 0
    }
    if ($process.HasExited) { throw "Workbench process exited with code $($process.ExitCode). See: $stderr" }
}
throw "Workbench did not pass its health check within $WaitSeconds seconds. See: $stderr"
