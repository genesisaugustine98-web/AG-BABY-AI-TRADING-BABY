# AG-BABY Free-First Architecture

## First principle

Use free resources to maximize **independent information coverage**, not to maximize the number of vendors.

More providers can increase:
- data duplication;
- conflicting timestamps;
- different contract definitions;
- rate-limit failures;
- schema drift;
- maintenance cost;
- false confidence from correlated sources.

The free stack therefore has a small authoritative core plus optional cross-check sources.

## Runtime topology

~~~text
                    GitHub
              source + CI + research
                       |
          +------------+------------+
          |                         |
          v                         v
   Linux research/control      Vercel cockpit
   (AWS free/eligible host)   (read-only UI)
          |
          +----------------------+
          |                      |
          v                      v
   local compressed archive   Supabase Free
   (research artifacts)       durable ledger/control
          |                      |
          +----------+-----------+
                     |
                     v
             Windows execution host
               MT5 demo terminal
                     |
                     v
              broker demo truth

External:
  Grafana Cloud Free -> metrics/logs
  UptimeRobot Free   -> 5-minute external health check
  Cloudflare Workers -> optional public edge/status only
~~~

The Windows execution node is intentionally separate because the current repository's MT5 integration and trusted runtime are designed around a Windows MT5 terminal.

## Free compute allocation

### GitHub Actions

Use public-repository standard runners for:
- unit/regression tests;
- research batteries;
- backtest matrix jobs;
- source smoke tests;
- dependency/security checks.

GitHub documents standard runners as free and unlimited for public repositories. Avoid larger runners and avoid relying on Actions as a 24/7 daemon.

### Existing AWS Linux host

Use the existing eligible Free Tier/credit-backed Linux host for:
- continuous research polling;
- local data cache;
- DuckDB/Parquet research;
- optional Prometheus agent;
- operator utilities.

Do not create multiple always-on hosts just because other free tiers exist. Consolidation reduces cost and operational failure surface.

### Windows MT5 host

Use a Windows host only for:
- MT5 terminal;
- broker demo/funded-account connectivity;
- the protected execution gateway.

Do not put the research warehouse or large ML environment on that host.

## Free data hierarchy

### FX

**Authoritative execution truth:** MT5 broker quote/account state.

**Macro/positioning:** FRED/ALFRED, central-bank sources, BLS/BEA where relevant, ECB/BOE/BOJ data, and CFTC COT.

**Centralized market proxy:** CME FX futures data where access/licensing permits.

The system must label reference data separately from executable broker data.

### Crypto

**Primary market observations:** exchange WebSockets/REST from Binance, Coinbase and Kraken.

**Derivatives observations:** public funding, basis, open-interest, liquidation and market-analytics endpoints where available.

**On-chain research:** Etherscan, Dune and DeFiLlama as supplemental sources.

The system must never claim that these public sources provide the same institutional information set.

## Storage

Do not put high-frequency raw market data into the 500 MB Supabase Free Postgres database. Keep raw/large research data on the Linux research host in compressed Parquet/DuckDB files; keep Supabase for compact evidence, metadata, model registry, order ledger and control state.

Supabase Free currently includes 500 MB database size and 1 GB file storage and can pause projects after 1 week of inactivity, so it is a poor sole archive for market history. It remains useful for durable control-plane metadata and demo accounting, provided the runtime freezes on dependency failure.

## Observability

Grafana Cloud Free is suitable for:
- metrics;
- logs;
- traces;
- short retention operational history.

UptimeRobot Free is suitable for:
- external HTTP/ping/port/heartbeat checks;
- detecting that the Windows/Linux node or cockpit is no longer reachable.

Neither service is authoritative for trading permission. Supabase control state and broker truth remain authoritative.

## Edge

Cloudflare Workers Free is appropriate for:
- a tiny public status/health facade;
- signed alert relay;
- cached read-only status.

It is not appropriate for:
- MT5 connectivity;
- persistent Python processes;
- market-making loops;
- heavy model inference.

The current Workers Free plan has 100,000 requests/day and 10 ms CPU per invocation.

## Scheduling

Do not use Vercel Hobby Cron as the market clock. Hobby Cron is limited to daily schedules and timing is only hourly precise. It is useful for:
- daily research refresh;
- daily report generation;
- maintenance.

Use the Linux runtime for continuous loops and GitHub Actions for CI/research jobs.

## Model stack

Start with:
- deterministic factor features;
- linear/logistic baselines;
- tree ensembles only where they beat baselines out of sample;
- calibrated probabilities;
- explicit regime conditioning.

Keep training dependencies out of the MT5 execution environment. The execution host should remain small and deterministic.

## Security

Secrets must stay in:
- GitHub Secrets;
- server-side environment variables;
- platform secret stores.

Never send broker credentials to:
- Vercel browser code;
- Cloudflare Workers;
- research notebooks;
- LLM prompts;
- GitHub repository files.

## Promotion path

~~~text
research
  -> frozen hypothesis
  -> PIT dataset
  -> cost/delay stress
  -> walk-forward
  -> locked holdout
  -> capacity
  -> paper
  -> prolonged demo
  -> funded-account rule adapter
  -> human authorization
~~~

The current repository remains demo-only. The objective of this branch is to build the research/data/control plane and preserve the protected execution boundary, not silently turn on live capital execution.
