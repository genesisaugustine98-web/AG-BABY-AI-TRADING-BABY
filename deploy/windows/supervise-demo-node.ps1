$ErrorActionPreference = 'Stop'

$MaxRestarts = if ($env:AG_MAX_RESTARTS) { [int]$env:AG_MAX_RESTARTS } else { 5 }
$BackoffSeconds = if ($env:AG_RESTART_BACKOFF_SECONDS) { [int]$env:AG_RESTART_BACKOFF_SECONDS } else { 15 }
$HealthEnabled = if ($env:AG_SUPERVISOR_HEALTH_ENABLED) { $env:AG_SUPERVISOR_HEALTH_ENABLED.ToLower() -in @('1','true','yes','on') } else { $false }
$HealthIntervalSeconds = if ($env:AG_HEALTHCHECK_INTERVAL_SECONDS) { [int]$env:AG_HEALTHCHECK_INTERVAL_SECONDS } else { 15 }
$HealthFailureLimit = if ($env:AG_HEALTHCHECK_FAILURES) { [int]$env:AG_HEALTHCHECK_FAILURES } else { 3 }
$MetricsPort = if ($env:AG_METRICS_PORT) { [int]$env:AG_METRICS_PORT } else { 9300 }
$RestartCount = 0

if ($HealthEnabled -and $HealthIntervalSeconds -lt 1) { throw 'AG_HEALTHCHECK_INTERVAL_SECONDS must be >= 1' }
if ($HealthEnabled -and $HealthFailureLimit -lt 1) { throw 'AG_HEALTHCHECK_FAILURES must be >= 1' }

while ($true) {
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRootun-demo-node.ps1" | Out-Host
  # run-demo-node.ps1 blocks until the Python runtime exits. The separate health watchdog
  # below is therefore only useful when the runtime exposes a dedicated supervisor heartbeat.
  $ExitCode = $LASTEXITCODE

  if ($ExitCode -eq 0) {
    Write-Host 'AG-BABY runtime stopped cleanly.'
    exit 0
  }

  $RestartCount++
  Write-Warning "AG-BABY runtime failed with exit code $ExitCode. Restart $RestartCount of $MaxRestarts."

  if ($RestartCount -gt $MaxRestarts) {
    Write-Error 'Restart budget exhausted. Leaving durable execution controls frozen for operator/reconciliation review.'
    exit $ExitCode
  }

  Start-Sleep -Seconds ([Math]::Min(300, $BackoffSeconds * $RestartCount))
}
