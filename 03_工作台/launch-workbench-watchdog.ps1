[CmdletBinding()]
param(
    [int]$Port = 8766
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$watcher = Join-Path $root 'watch-workbench.ps1'
$launcher = Join-Path $root 'scripts\launch_detached_watchdog.py'
$runtime = Join-Path $env:LOCALAPPDATA 'AI-Viral-Content-Factory\workbench'
$configPath = Join-Path $runtime 'workbench-launcher.json'
if (-not (Test-Path -LiteralPath $watcher)) {
    throw "Workbench watchdog is missing: $watcher"
}
if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Workbench detached launcher is missing: $launcher"
}

if (Test-Path -LiteralPath $configPath) {
    $python = (Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json).pythonPath
}
if (-not $python -or -not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python.exe -ErrorAction Stop).Source
}
$desktopBridgeAgent = Join-Path $root 'scripts\codex_desktop_bridge_agent.py'
if (Test-Path -LiteralPath $desktopBridgeAgent) {
    Start-Process -FilePath $python -ArgumentList @('-B', '-u', $desktopBridgeAgent, '--port', $Port) -WorkingDirectory $root -WindowStyle Hidden
}
& $python $launcher --watcher $watcher --working-directory $root --runtime $runtime --port $Port
if ($LASTEXITCODE -ne 0) { throw "Detached watchdog launcher failed with exit code $LASTEXITCODE." }
