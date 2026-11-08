# Risk and execution review

This is a code-review note, not a broker certification or financial recommendation.

## Design strengths

- Live trading is intentionally disabled in the documented v2 architecture.
- The LLM is kept away from broker credentials and direct execution authority.
- The MT5 demo gateway is designed to fail closed if demo status cannot be established.
- Unknown broker outcomes are documented as requiring reconciliation, not blind retry.
- Research promotion is intended to require out-of-sample evidence, costs, stress tests and shadow/demo checks.

## Remaining evidence requirements

- Prove end-to-end idempotency and UNKNOWN-state recovery against simulated timeouts, duplicate callbacks and partial fills.
- Demonstrate that kill switches work across restarts and broker reconnects.
- Verify contract sizes, symbol mappings, volume steps, tick values, commissions, swaps and market hours against each demo broker.
- Record and reconcile every order request, broker acknowledgement, fill, cancellation and position snapshot.
- Perform deterministic replay and fault-injection exercises before an unattended demo run.
- Treat architectural coverage metrics as implementation coverage, never as trading accuracy.

## Operating restriction

Do not connect a live account or enable real-money execution as part of this readiness work. A clean CI run is necessary but does not prove safe execution.
