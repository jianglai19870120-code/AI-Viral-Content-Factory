[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RuntimePath
)

$ErrorActionPreference = 'Stop'
$runnerLog = Join-Path $RuntimePath 'scheduled-watchdog.log'
New-Item -ItemType Directory -Path $RuntimePath -Force | Out-Null

try {
    Add-Content -LiteralPath $runnerLog -Encoding utf8 -Value "$(Get-Date -Format 'o') scheduled watchdog host started pid=$PID"
    # The watchdog writes its own state and trace. Do not redirect it to this
    # host log: Windows PowerShell keeps redirected files exclusively locked.
    & (Join-Path $PSScriptRoot 'watch-workbench.ps1') -RuntimePath $RuntimePath
    $exitCode = $LASTEXITCODE
    Add-Content -LiteralPath $runnerLog -Encoding utf8 -Value "$(Get-Date -Format 'o') scheduled watchdog host exited code=$exitCode"
    exit $exitCode
} catch {
    Add-Content -LiteralPath $runnerLog -Encoding utf8 -Value "$(Get-Date -Format 'o') scheduled watchdog host failed: $($_.Exception.Message)"
    exit 1
}
