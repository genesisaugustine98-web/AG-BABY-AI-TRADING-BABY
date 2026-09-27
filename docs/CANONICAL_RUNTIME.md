# Canonical runtime deployment

## Runtime contract

The canonical process is started with:

~~~powershell
python -m apps.trading_runtime
~~~

It is intentionally demo/paper bounded. Broker submission is permitted only when:

- EXECUTION_ENV=demo
- AG_EXECUTION_ENABLED=true
- the MT5 gateway positively verifies the configured demo server/account
- startup reconciliation is clean
- the model passes the explicit governance evidence gate
- the current quote is fresh and the market state is not blocked
- strategy allocation approves the candidate
- policy and deterministic risk approve the order
- the durable execution order is written before broker submission

Any failure in those gates causes the process to refuse execution or enter a frozen state.

## Required demo environment

Set these on the Windows execution host. Never commit credentials.

~~~text
EXECUTION_ENV=demo
AG_EXECUTION_ENABLED=true
AG_NODE_ID=ag-demo-node-01
AG_SYMBOLS=EURUSD,GBPUSD
AG_TIMEFRAME=H1
AG_BARS_PER_SYMBOL=500

MT5_SERVER=<demo-server>
MT5_DEMO_SERVER=<same-demo-server>
MT5_LOGIN=<demo-login>
MT5_PASSWORD=<demo-password>
MT5_TERMINAL_PATH=<optional-full-path-to-terminal64.exe>

SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SECRET_KEY=<server-only-secret>

GIT_COMMIT_SHA=<deployed-commit>

AG_MODEL_EVIDENCE_JSON={...}
~~~

The runtime fills data_fingerprint and code_commit_sha from the fitted model when those JSON fields are empty.

## Host topology

The execution node should be a Windows host capable of running the MetaTrader 5 terminal and its Python integration. Linux control/research hosts can remain separate.

~~~text
research / CI / Supabase / observability
                 |
                 | secure deployment/configuration
                 v
Windows execution node
  -> MetaTrader 5 demo terminal
  -> python -m apps.trading_runtime
~~~

## Shutdown behavior

SIGINT and SIGTERM freeze durable execution state before closing the broker session. A restart must reconcile against broker truth before trading can resume.

Do not place passwords in command history, source code, workflow files, or browser-exposed variables.

See apps/trading_runtime/canonical.py for the single composition root.

## Institutional hardening controls

Optional multi-host fencing:

    AG_DISTRIBUTED_LEASE=true
    AG_LEASE_NAME=ag-demo-execution
    AG_LEASE_TTL_SECONDS=30

Optional local telemetry:

    AG_METRICS_ENABLED=true
    AG_METRICS_HOST=127.0.0.1
    AG_METRICS_PORT=9300

Portfolio allocation controls:

    AG_MAX_CORR_ADJUSTED_RISK=0.03
    AG_MAX_ABS_NET_RISK=0.03
    AG_REQUIRE_COMPLETE_CORRELATIONS=true
    AG_PORTFOLIO_CORRELATIONS={"EURUSD,GBPUSD":"0.78"}

Execution circuit breakers:

    AG_MAX_EXECUTION_UNKNOWN=1
    AG_MAX_EXECUTION_REJECTIONS=5

The complete failure matrix, promotion doctrine, and multi-host safety contract are in docs/INSTITUTIONAL_RUNTIME.md.
