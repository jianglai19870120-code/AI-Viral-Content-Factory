[CmdletBinding()]
param(
    [int]$Port = 8766
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$agent = Join-Path $root 'scripts\codex_desktop_bridge_agent.py'
if (-not (Test-Path -LiteralPath $agent)) {
    throw "Codex 桌面桥接助手不存在: $agent"
}
$python = (Get-Command python.exe -ErrorAction Stop).Source
Start-Process -FilePath $python -ArgumentList @('-B', '-u', $agent, '--port', $Port) -WorkingDirectory $root -WindowStyle Hidden
