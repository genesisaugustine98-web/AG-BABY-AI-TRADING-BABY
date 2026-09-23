$ErrorActionPreference = 'Stop'

$MaxRestarts = if ($env:AG_MAX_RESTARTS) { [int]$env:AG_MAX_RESTARTS } else { 5 }
$BackoffSeconds = if ($env:AG_RESTART_BACKOFF_SECONDS) { [int]$env:AG_RESTART_BACKOFF_SECONDS } else { 15 }
$RestartCount = 0

while ($true) {
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\run-demo-node.ps1"
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