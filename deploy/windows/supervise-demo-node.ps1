$ErrorActionPreference = 'Stop'

$MaxRestarts = if ($env:AG_MAX_RESTARTS) { [int]$env:AG_MAX_RESTARTS } else { 5 }
$BackoffSeconds = if ($env:AG_RESTART_BACKOFF_SECONDS) { [int]$env:AG_RESTART_BACKOFF_SECONDS } else { 15 }
$HealthEnabled = if ($env:AG_SUPERVISOR_HEALTH_ENABLED) { $env:AG_SUPERVISOR_HEALTH_ENABLED.ToLower() -in @('1','true','yes','on') } else { $false }
$HealthIntervalSeconds = if ($env:AG_HEALTHCHECK_INTERVAL_SECONDS) { [int]$env:AG_HEALTHCHECK_INTERVAL_SECONDS } else { 15 }
$HealthFailureLimit = if ($env:AG_HEALTHCHECK_FAILURES) { [int]$env:AG_HEALTHCHECK_FAILURES } else { 3 }
$StartupGraceSeconds = if ($env:AG_HEALTHCHECK_STARTUP_GRACE_SECONDS) { [int]$env:AG_HEALTHCHECK_STARTUP_GRACE_SECONDS } else { 60 }
$MetricsPort = if ($env:AG_METRICS_PORT) { [int]$env:AG_METRICS_PORT } else { 9300 }
$RestartCount = 0

if ($MaxRestarts -lt 0) { throw 'AG_MAX_RESTARTS must be >= 0' }
if ($HealthEnabled -and $HealthIntervalSeconds -lt 1) { throw 'AG_HEALTHCHECK_INTERVAL_SECONDS must be >= 1' }
if ($HealthEnabled -and $HealthFailureLimit -lt 1) { throw 'AG_HEALTHCHECK_FAILURES must be >= 1' }
if ($HealthEnabled -and $StartupGraceSeconds -lt 0) { throw 'AG_HEALTHCHECK_STARTUP_GRACE_SECONDS must be >= 0' }

while ($true) {
  $Process = Start-Process powershell.exe `
    -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',"$PSScriptRoot\run-demo-node.ps1") `
    -PassThru

  $HealthFailures = 0
  $StartedAt = Get-Date

  while ($true) {
    Start-Sleep -Seconds $(if ($HealthEnabled) { $HealthIntervalSeconds } else { 2 })
    $Process.Refresh()

    if ($Process.HasExited) {
      $ExitCode = $Process.ExitCode
      break
    }

    if (-not $HealthEnabled) {
      continue
    }

    $AgeSeconds = ((Get-Date) - $StartedAt).TotalSeconds
    if ($AgeSeconds -lt $StartupGraceSeconds) {
      continue
    }

    try {
      $health = Invoke-RestMethod "http://127.0.0.1:$MetricsPort/healthz" -TimeoutSec 5
      $ready = Invoke-RestMethod "http://127.0.0.1:$MetricsPort/readyz" -TimeoutSec 5

      if ($health.healthy -and $ready.ready) {
        $HealthFailures = 0
      }
      else {
        $HealthFailures++
        Write-Warning "AG-BABY runtime health failure ${HealthFailures} of $HealthFailureLimit."
      }
    }
    catch {
      $HealthFailures++
      Write-Warning "AG-BABY runtime health probe failed ${HealthFailures} of ${HealthFailureLimit}: $($_.Exception.Message)"
    }

    if ($HealthFailures -ge $HealthFailureLimit) {
      Write-Error 'AG-BABY runtime failed the external health watchdog. Terminating child and restarting under the bounded restart policy.'
      Stop-Process -Id $Process.Id -Force
      $Process.WaitForExit()
      $ExitCode = 70
      break
    }
  }

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
