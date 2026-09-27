$ErrorActionPreference = 'Stop'

if ($env:EXECUTION_ENV -ne 'demo') { throw 'Refusing to start: EXECUTION_ENV must be demo.' }
if ($env:AG_EXECUTION_ENABLED -ne 'true') { throw 'Refusing to start: AG_EXECUTION_ENABLED must be true for demo submission.' }
if (-not $env:MT5_SERVER -or -not $env:MT5_DEMO_SERVER -or -not $env:MT5_LOGIN -or -not $env:MT5_PASSWORD) {
  throw 'Missing MT5 demo environment variables.'
}
if (-not $env:SUPABASE_URL -or -not $env:SUPABASE_SECRET_KEY) {
  throw 'Missing server-side Supabase environment variables.'
}

python -m apps.trading_runtime
if ($LASTEXITCODE -ne 0) {
  throw "AG-BABY runtime exited with code $LASTEXITCODE. Durable reconciliation/freeze state must be inspected before restart."
}