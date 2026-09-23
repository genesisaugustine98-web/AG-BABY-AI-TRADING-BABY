# Institutional Runtime FAQ

## Is this a real trading system or a backtest?

It is a real software runtime with an MT5 demo execution boundary, durable order state, reconciliation, risk controls, model governance and supervision. It is not merely a historical backtest. It is also not a proven profitable trading operation.

## Can it trade a real-money account today?

The canonical autonomous runtime deliberately cannot. Its environment validation accepts only demo, and the lower execution boundary independently enforces the demo constraint.

## What happens if MT5 disconnects?

The runtime fails closed. It does not invent broker state. It must reconnect and reconcile broker orders, positions and account state before autonomous submission can resume.

## What happens if an order submission times out?

The system treats an ambiguous submission as UNKNOWN. It persists that state and requires broker truth before recovery. Blind duplicate retries are prohibited.

## What happens if two machines start the robot?

The host-local singleton prevents duplicate processes on one host. The optional Supabase/Postgres fenced lease provides multi-host ownership with a fencing token. A node that loses the lease is frozen.

## Can an operator override the risk engine?

The intended design is fail-closed: risk and policy checks sit on the execution path, and durable frozen state cannot be bypassed by changing in-memory state. Any future operator-control surface should require authenticated, audited, reconciliation-aware actions.

## How is portfolio correlation handled?

There are two stages. The strategy allocator applies risk-budget and correlation-aware concentration controls before order construction. After the exact order size is known, the canonical portfolio gate rebuilds broker-valued exposures and checks gross, net, margin, realized portfolio volatility, beta and required correlation inputs.

## How are non-USD pairs handled?

The exact portfolio gate does not silently guess a USD conversion for unsupported cross-currency instruments. If a position cannot be valued unambiguously in USD from the supported pair structure, the gate fails closed.

## How do we know which configuration generated an order?

Every runtime instance has a unique instance ID, and runtime events carry a deterministic configuration fingerprint. Model records also preserve model ID/version, dataset fingerprint, feature identity and code commit SHA.

## Can the event ledger be tampered with silently?

The canonical runtime uses a hash-linked event chain. Each persisted event records the previous event hash and its own SHA-256 hash, and the adapter contains deterministic verification logic.

## What happens when Supabase is unavailable?

Critical durable execution/audit operations fail closed rather than allowing the runtime to continue as though persistence had succeeded.

## What happens if the system clock jumps?

The runtime clock rejects large forward jumps and significant backward movement. A clock anomaly causes the runtime cycle to fail closed rather than corrupting quote age or event ordering assumptions.

## Does the model-monitoring layer prove the strategy is profitable?

No. Model drift and calibration metrics are surveillance signals. Economic performance still requires independent, executable-cost research across multiple periods and regimes.

## What does CI prove?

CI proves things such as compilation, tests, web build/lint, Windows deployment-script syntax, demo-only environment enforcement and dependency security scans. CI does not prove future trading returns or eliminate broker/market risk.

## What remains before a serious production-like demo soak?

The main remaining work is operational evidence: prolonged soak, deliberate fault injection, real broker execution telemetry, recovery drills and further integration of model surveillance. The architecture now has explicit places for those controls.

## Why not simply turn on live mode later?

Because a live-capital boundary should be independently reviewed. The current demo constraint intentionally prevents a credential/configuration mistake from becoming a capital authorization mechanism.
