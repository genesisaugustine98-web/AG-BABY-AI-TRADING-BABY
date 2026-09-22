'use client';

import { useState } from "react";
import type { ReactNode } from "react";
import type { DashboardSnapshot } from "../lib/dashboard";

function pretty(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return value.toLocaleString();
  return String(value);
}

function Status({ ok, children }: { ok: boolean; children: ReactNode }) {
  return <span className={`status ${ok ? "status-ok" : "status-bad"}`}><span className="status-dot" />{children}</span>;
}

export default function DashboardShell({ initial }: { initial: DashboardSnapshot }) {
  const [snapshot, setSnapshot] = useState(initial);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const response = await fetch("/api/dashboard", { cache: "no-store" });
      if (response.ok) setSnapshot(await response.json());
    } finally {
      setLoading(false);
    }
  }

  const latestRecon = snapshot.reconciliations[0];
  const latestRisk = snapshot.riskDecisions[0];
  const openPositions = snapshot.positions.filter((row) => Number(row.net_quantity ?? 0) !== 0).length;

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">AG // INSTITUTIONAL FX EDGE</p>
          <h1>Trading Operations Cockpit</h1>
          <p className="muted">Research, risk, execution truth and broker reconciliation in one control surface.</p>
        </div>
        <div className="header-actions">
          <Status ok={snapshot.source === "supabase" && !snapshot.control.frozen}>{snapshot.control.frozen ? "EXECUTION FROZEN" : "EXECUTION OPEN"}</Status>
          <span className="env-chip">{snapshot.environment.toUpperCase()}</span>
          <button onClick={refresh} disabled={loading} className="refresh">{loading ? "Refreshing…" : "Refresh"}</button>
        </div>
      </header>

      {snapshot.note && <div className="alert"><strong>Fail-closed:</strong> {snapshot.note}</div>}

      <section className="hero-grid">
        <article className="hero-card hero-card-primary"><div className="card-kicker">EXECUTION CONTROL</div><div className="hero-value">{snapshot.control.frozen ? "FROZEN" : "READY"}</div><div className="hero-detail">{snapshot.control.reason || "No active freeze reason."}</div><div className="hero-meta">Last control update: {pretty(snapshot.control.updated_at)}</div></article>
        <article className="metric-card"><span>Open positions</span><strong>{openPositions}</strong><small>{snapshot.positions.length} tracked symbols</small></article>
        <article className="metric-card"><span>Active orders</span><strong>{snapshot.activeOrders.length}</strong><small>Durable internal order ledger</small></article>
        <article className="metric-card"><span>Risk decisions</span><strong>{snapshot.riskDecisions.length}</strong><small>Latest: {pretty(latestRisk?.decision)}</small></article>
      </section>

      <section className="section-grid">
        <article className="panel"><div className="panel-head"><div><div className="card-kicker">BROKER TRUTH</div><h2>Account snapshot</h2></div><Status ok={Boolean(snapshot.account)}>{snapshot.account ? "Captured" : "Unavailable"}</Status></div><div className="key-grid"><div><span>Balance</span><strong>{pretty(snapshot.account?.balance)}</strong></div><div><span>Equity</span><strong>{pretty(snapshot.account?.equity)}</strong></div><div><span>Margin</span><strong>{pretty(snapshot.account?.margin)}</strong></div><div><span>Free margin</span><strong>{pretty(snapshot.account?.margin_free)}</strong></div><div><span>Currency</span><strong>{pretty(snapshot.account?.currency)}</strong></div><div><span>Trade allowed</span><strong>{snapshot.account?.trade_allowed === true ? "YES" : snapshot.account ? "NO" : "—"}</strong></div></div></article>

        <article className="panel"><div className="panel-head"><div><div className="card-kicker">RECONCILIATION</div><h2>Broker vs ledger</h2></div><Status ok={latestRecon?.status === "MATCHED"}>{pretty(latestRecon?.status || "NO RUN")}</Status></div><div className="key-grid"><div><span>Orders checked</span><strong>{pretty(latestRecon?.orders_checked)}</strong></div><div><span>Fills checked</span><strong>{pretty(latestRecon?.fills_checked)}</strong></div><div><span>Positions checked</span><strong>{pretty(latestRecon?.positions_checked)}</strong></div><div><span>Drift count</span><strong>{pretty(latestRecon?.drift_count)}</strong></div></div><p className="muted">{pretty(latestRecon?.details ? JSON.stringify(latestRecon.details) : "No reconciliation record yet.")}</p></article>
      </section>

      <section className="panel wide"><div className="panel-head"><div><div className="card-kicker">POSITIONS</div><h2>Environment-scoped position state</h2></div><span className="muted">{snapshot.positions.length} rows</span></div><div className="table-wrap"><table><thead><tr><th>Instrument</th><th>Net qty</th><th>Avg</th><th>Realized P&amp;L</th><th>Financing</th><th>State</th></tr></thead><tbody>{snapshot.positions.map((row, index) => <tr key={`${row.position_id}-${index}`}><td>{pretty(row.instrument)}</td><td>{pretty(row.net_quantity)}</td><td>{pretty(row.average_price)}</td><td>{pretty(row.realized_pnl)}</td><td>{pretty(row.financing_pnl)}</td><td>{pretty(row.state)}</td></tr>)}{!snapshot.positions.length && <tr><td colSpan={6} className="empty">No persisted positions.</td></tr>}</tbody></table></div></section>

      <section className="section-grid">
        <article className="panel"><div className="panel-head"><div><div className="card-kicker">ORDER FLOW</div><h2>Active internal orders</h2></div><span className="muted">No browser-side execution controls</span></div><div className="stack">{snapshot.activeOrders.map((row, index) => <div className="list-row" key={`${row.order_id}-${index}`}><div><strong>{pretty(row.instrument)} · {pretty(row.side)}</strong><span>{pretty(row.client_order_id)}</span></div><div className="right"><strong>{pretty(row.requested_quantity)}</strong><span>{pretty(row.state)}</span></div></div>)}{!snapshot.activeOrders.length && <div className="empty">No active durable orders.</div>}</div></article>
        <article className="panel"><div className="panel-head"><div><div className="card-kicker">OPPORTUNITY ENGINE</div><h2>Candidate pipeline</h2></div><span className="muted">Evidence before execution</span></div><div className="stack">{snapshot.opportunities.map((row, index) => <div className="list-row" key={`${row.candidate_id}-${index}`}><div><strong>{pretty(row.instrument)} · {pretty(row.side)}</strong><span>{pretty(row.model_id)} {pretty(row.model_version)}</span></div><div className="right"><strong>{pretty(row.executable_edge)}</strong><span>{pretty(row.state)}</span></div></div>)}{!snapshot.opportunities.length && <div className="empty">No stored opportunity candidates.</div>}</div></article>
      </section>

      <section className="section-grid">
        <article className="panel"><div className="panel-head"><div><div className="card-kicker">MODEL GOVERNANCE</div><h2>Registry</h2></div></div><div className="stack">{snapshot.models.map((row, index) => <div className="list-row" key={`${row.model_id}-${index}`}><div><strong>{pretty(row.model_id)} · {pretty(row.version)}</strong><span>{pretty(row.dataset_fingerprint)}</span></div><div className="right"><strong>{pretty(row.status)}</strong><span>{pretty(row.feature_version)}</span></div></div>)}{!snapshot.models.length && <div className="empty">No registered models.</div>}</div></article>
        <article className="panel"><div className="panel-head"><div><div className="card-kicker">DATA MESH</div><h2>Source health</h2></div></div><div className="stack">{snapshot.dataSources.map((row, index) => <div className="list-row" key={`${row.source_id}-${index}`}><div><strong>{pretty(row.provider)}</strong><span>{pretty(row.source_type)} · {pretty(row.license_class)}</span></div><div className="right"><strong>{pretty(row.health)}</strong><span>{pretty(row.revision)}</span></div></div>)}{!snapshot.dataSources.length && <div className="empty">No registered data sources.</div>}</div></article>
      </section>

      <footer className="footer"><span>Server-generated: {snapshot.generatedAt}</span><span>Live trading is disabled by policy; demo/paper paths remain explicitly bounded.</span></footer>
    </main>
  );
}
