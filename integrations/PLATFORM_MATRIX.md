# Platform Integration Matrix

This repository is the canonical source of truth for the Institutional FX Edge Trading OS.

## Principles

1. GitHub is the system of record for source code, schemas, tests, CI, release manifests, and integration contracts.
2. External platforms consume versioned artifacts from GitHub; they do not become independent sources of truth.
3. No platform receives trading credentials by default.
4. Execution credentials remain isolated from research, analytics, model-training, and UI workloads.
5. External systems communicate through explicit artifacts, APIs, webhooks, or CI jobs with correlation IDs and immutable audit records.
6. Failure of an integration must fail closed for trading decisions: missing integration health means no new exposure unless an explicit policy permits a degraded research-only mode.

| Platform / Layer | Intended role | Repo access | Write-back | Credential class | Current status |
|---|---|---|---|---|---|
| GitHub | Source of truth, CI/CD, issues, release history | Read/write | Yes | GitHub App / token | Connected and writable |
| Hugging Face | Models, datasets, training/inference jobs | Read by default; job-based pull from public repo | Results/artifacts only | HF OAuth/token | Authenticated; current OAuth scope is read-repos + jobs |
| Kaggle | Heavy research/training notebooks and datasets | Pull public repo or release artifact | Research artifacts | Kaggle API token | Workflow contract defined; credentials not stored in repo |
| Google Colab | Interactive research and validation | Clone/pull repo | Research artifacts | User OAuth/token | Workflow contract defined |
| AWS | Durable compute/object storage/queues where needed | CI/job pull | Artifacts/metrics | GitHub OIDC or scoped AWS role | Workflow contract defined |
| Vercel | Research/control-plane web UI and dashboards | Git integration | Deployment status/metadata | Vercel integration token | Connector available; connection requires user authorization |
| Supabase | Postgres/metadata/vector/event storage | Migration-driven | Data + migration status | Scoped project secret | Connector available; connection requires user authorization |
| Render | Long-running service/worker alternative | Git deploy | Deploy/log/health metadata | Service API token | Connector available; connection requires user authorization |
| DigitalOcean | Remote development/compute workspace | Git clone/pull | Code changes only via GitHub | Scoped token/SSH | Connector available; connection requires user authorization |
| MT5 demo gateway | Broker demo execution | Pull release/source | Trade/audit events | Demo-only broker secret | Code present; live execution prohibited by policy |
| OpenBB / Qlib / NautilusTrader / FinRL | Research and simulation toolchain | Package/repo consumption | Reports/artifacts | None by default | Adapter boundary defined |

## Secret policy

Never commit API keys, passwords, private certificates, broker credentials, or cloud access tokens. Use platform-native secrets or GitHub Actions secrets/OIDC. The repository must remain safe to publish.

## Communication contract

External jobs should identify themselves with:

- `repo`
- `commit_sha`
- `integration_name`
- `run_id`
- `correlation_id`
- `environment` (`research`, `paper`, `demo`, `live`)
- `status`
- `started_at`
- `completed_at`
- `artifact_uri`
- `failure_class`

Only `research`, `paper`, and `demo` environments are enabled by default. A `live` value must be treated as disabled until separately reviewed and explicitly unlocked.
