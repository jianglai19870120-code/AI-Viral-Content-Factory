[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$taskName = 'AI Viral Content Factory Workbench Service'
$runtime = Join-Path $env:ProgramData 'AI-Viral-Content-Factory\workbench'
$statePath = Join-Path $runtime 'watchdog-install-state.json'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$installState = $null

if (Test-Path -LiteralPath $statePath) {
    Write-Output '安装结果：'
    $rawInstallState = Get-Content -LiteralPath $statePath -Raw
    Write-Output $rawInstallState
    try { $installState = $rawInstallState | ConvertFrom-Json } catch { }
} else {
    Write-Warning "未找到安装结果：$statePath"
    Write-Warning '管理员安装器没有完成。请重新运行本文件，并在 UAC 提示中选择“是”。'
}

if ($task) {
    Write-Output '计划任务：'
    $task | Select-Object TaskName, State, TaskPath | Format-Table -AutoSize
    $taskInfo = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
    $taskInfo | Select-Object LastRunTime, LastTaskResult | Format-List
    exit 0
}

if ($installState -and $installState.status -eq 'installed' -and $installState.scheduledTaskInstalled) {
    # A standard user token cannot always query a SYSTEM task. The installer
    # records success only after its elevated Task Scheduler and health checks.
    Write-Output '计划任务：已由管理员安装器验证；当前会话无任务查询权限。'
    exit 0
}

Write-Warning '计划任务尚未登记，因此工作台仍不能保证跨 Codex 重启持续运行。'
exit 2
