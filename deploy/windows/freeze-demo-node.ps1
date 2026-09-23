param(
    [string]$Path = "runtime\EMERGENCY_FREEZE"
)

$ErrorActionPreference = "Stop"
$parent = Split-Path -Parent $Path
if ($parent -and -not (Test-Path $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}

"EMERGENCY_FREEZE $(Get-Date -Format o)" | Set-Content -Path $Path -Encoding UTF8
Write-Host "Emergency freeze asserted at $Path. Do not delete this file until broker reconciliation and operator review are complete."
