# AG-BABY Free-First Live Runbook

## What “live” means here

This branch makes the **research/control plane live**. It does not enable live-capital execution. The repository's current canonical runtime must continue to reject `environment="live"`.

The production-like topology is:

- Linux host: continuous public-data observation/research.
- Supabase Free: compact control state, evidence, model registry, demo ledger and source health.
- Vercel Hobby: cockpit/read-only web UI.
- Windows MT5 host: broker-facing execution boundary, still demo-only until the repository's execution evidence gate is satisfied.
- GitHub Actions: free CI/research jobs for this public repository.
- Optional external observability: Grafana Cloud Free and UptimeRobot Free.

## Linux host

The current AWS Linux machine can be used if its account/region/instance is verified as remaining inside the user's available Free Tier or credits. Do not create a second always-on VM until the first is proven insufficient.

From the repository checkout:

```bash
cd /opt
sudo git clone --branch codex/free-stack-multihorizon-20260927 \
  https://github.com/genesisaugustine98-web/AG-BABY-AI-TRADING-BABY.git ag-baby
cd /opt/ag-baby
```

Install the observer/research fabric:

```bash
sudo bash deploy/linux/install_free_stack.sh
```

The service now:

1. polls public Binance/Kraken sources;
2. normalizes source observations into the existing research contract;
3. periodically fetches closed Binance candles;
4. runs the existing TSMOM model at native M15/H1/H4/D1 horizons;
5. emits a multi-horizon consensus proposal;
6. stores compact provenance-bearing JSONL locally;
7. optionally publishes source health/last-seen metadata into Supabase.

Check:

```bash
sudo systemctl --no-pager status ag-baby-free-stack
curl -sS http://127.0.0.1:8787/healthz
curl -sS http://127.0.0.1:8787/metrics
tail -n 5 /var/lib/ag-baby/observations/observations-$(date -u +%Y-%m-%d).jsonl
```

### Environment

Create the root-owned environment file:

```bash
sudo install -m 600 /dev/null /etc/ag-baby/ag-baby.env
sudo tee /etc/ag-baby/ag-baby.env >/dev/null <<'EOF'
BINANCE_SYMBOL=BTCUSDT
KRAKEN_FUTURES_SYMBOL=PI_XBTUSD
OBSERVATION_INTERVAL_SECONDS=60
RESEARCH_INTERVAL_SECONDS=900
RESEARCH_HORIZONS=M15,H1,H4,D1
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SECRET_KEY=REPLACE_WITH_SERVER_ONLY_KEY
EOF
sudo systemctl restart ag-baby-free-stack
```

Do not put this file in Git.

## FRED

FRED/ALFRED currently require an API key. Store it only in the same root-owned environment file:

```bash
sudo sh -c 'printf "FRED_API_KEY=REPLACE_ME\\n" >> /etc/ag-baby/ag-baby.env'
sudo systemctl restart ag-baby-free-stack
```

The code redacts query strings before persisting source URLs.

## Windows MT5 execution host

Do not move the MT5 terminal into the Linux observer.

The current runtime uses a Windows execution boundary with MetaTrader 5. Keep:

- broker credentials;
- terminal state;
- execution gateway;
- broker truth;
- reconciliation

on the Windows execution host.

The free-first research branch feeds **observations and evidence into research**, not directly into a broker submission.

## Vercel

Use the existing `ag-baby-ai-trading-baby` Vercel project for the cockpit/control UI.

Do not use Vercel Hobby Cron as the market clock. Hobby Cron is intended for daily schedules on Hobby and does not provide minute-level scheduling precision.

## GitHub Actions

Use public repository standard runners for:

- tests;
- compile checks;
- research batteries;
- source smoke tests;
- security checks.

Do not use GitHub Actions as a permanent daemon or broker execution host.

## Observability

### UptimeRobot

Create external monitors for:

- Vercel cockpit HTTPS endpoint;
- a deliberately exposed, authenticated health facade if one is later deployed.

Do not expose the local Linux health server directly to the Internet.

### Grafana Cloud

Export non-sensitive metrics:

- data-source successes/failures;
- observation age;
- process liveness;
- model state;
- queue lag;
- execution latency;
- reconciliation mismatches;
- circuit-breaker state.

Never export API keys, broker credentials, private keys or raw account secrets.

## Cost controls

### AWS

Before adding any resource, verify:

1. the account's current Free Tier/credit plan;
2. remaining credits/expiration;
3. the instance's current eligibility;
4. EBS/storage usage;
5. public IPv4 usage;
6. data-transfer usage.

Do not assume an instance is free solely because the instance family was free at some earlier date.

### Supabase

Keep the database compact. Store:

- model metadata;
- evidence;
- policies;
- source health;
- orders/fills/reconciliation;
- compact control observations.

Do not store every tick/order-book update in Postgres.

### Vercel

Keep the cockpit read-mostly. Do not turn it into the trading loop.

## Promotion gates

No strategy moves from research to capital execution until all are true:

- point-in-time dataset;
- locked holdout;
- realistic spread/commission/financing model;
- delay stress;
- capacity analysis;
- regime breakdown;
- parameter perturbation;
- multiple-testing accounting;
- paper evidence;
- prolonged MT5 demo soak;
- restart/UNKNOWN/reconciliation drills;
- provider rule-set verified for the target funded account;
- human authorization.

## Absolute rule

If data, broker truth, reconciliation, policy, or execution state is uncertain:

```
FREEZE
```

Do not convert uncertainty into a guessed order.
