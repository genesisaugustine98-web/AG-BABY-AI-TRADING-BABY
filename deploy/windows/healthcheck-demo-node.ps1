param(
    [int]$Port = 9300
)

$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:$Port"

try {
    $health = Invoke-RestMethod "$base/healthz" -TimeoutSec 5
    $ready = Invoke-RestMethod "$base/readyz" -TimeoutSec 5
    Write-Host ("health={0} ready={1} state={2} cycles={3} unknown={4}" -f $health.healthy, $ready.ready, $health.state, $health.cycles, $health.execution_unknown)
    if (-not $health.healthy) { exit 2 }
    if (-not $ready.ready) { exit 3 }
    exit 0
}
catch {
    Write-Error "demo node health endpoint unavailable: $($_.Exception.Message)"
    exit 4
}
