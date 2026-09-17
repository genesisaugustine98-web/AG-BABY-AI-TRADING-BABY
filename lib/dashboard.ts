import "server-only";

export type DashboardSnapshot = {
  generatedAt: string;
  source: "supabase" | "unconfigured" | "error";
  environment: string;
  control: { frozen: boolean; reason: string | null; updated_at: string | null };
  account: Record<string, unknown> | null;
  positions: Array<Record<string, unknown>>;
  activeOrders: Array<Record<string, unknown>>;
  reconciliations: Array<Record<string, unknown>>;
  riskDecisions: Array<Record<string, unknown>>;
  opportunities: Array<Record<string, unknown>>;
  models: Array<Record<string, unknown>>;
  dataSources: Array<Record<string, unknown>>;
  research: Array<Record<string, unknown>>;
  note: string | null;
};

const env = () => process.env.EXECUTION_ENV || "demo";

async function supabaseGet(table: string, params: Record<string, string>) {
  const base = (process.env.SUPABASE_URL || "").replace(/\/$/, "");
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY || "";
  if (!base || !key) return null;
  const query = new URLSearchParams(params);
  const response = await fetch(`${base}/rest/v1/${table}?${query.toString()}`, {
    headers: { apikey: key, Authorization: `Bearer ${key}`, Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Supabase ${table} HTTP ${response.status}`);
  return (await response.json()) as Array<Record<string, unknown>>;
}

export async function getDashboardSnapshot(): Promise<DashboardSnapshot> {
  const environment = env();
  if (!process.env.SUPABASE_URL || !(process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY)) {
    return {
      generatedAt: new Date().toISOString(),
      source: "unconfigured",
      environment,
      control: { frozen: true, reason: "SUPABASE_SERVER_CREDENTIALS_NOT_CONFIGURED", updated_at: null },
      account: null,
      positions: [],
      activeOrders: [],
      reconciliations: [],
      riskDecisions: [],
      opportunities: [],
      models: [],
      dataSources: [],
      research: [],
      note: "Server-side Supabase credentials are not configured; the cockpit is intentionally fail-closed.",
    };
  }

  try {
    const [controlRows, accountRows, positions, activeOrders, reconciliations, riskDecisions, opportunities, models, dataSources, research] = await Promise.all([
      supabaseGet("execution_control_state", { environment: `eq.${environment}`, select: "environment,frozen,reason,updated_at", limit: "1" }),
      supabaseGet("execution_account_snapshots", { environment: `eq.${environment}`, select: "*", order: "captured_at.desc", limit: "1" }),
      supabaseGet("execution_positions", { environment: `eq.${environment}`, select: "*", order: "updated_at.desc", limit: "25" }),
      supabaseGet("execution_orders", { environment: `eq.${environment}`, state: "not.in.(FILLED,REJECTED,CANCELLED)", select: "*", order: "updated_at.desc", limit: "25" }),
      supabaseGet("execution_reconciliations", { environment: `eq.${environment}`, select: "*", order: "started_at.desc", limit: "10" }),
      supabaseGet("risk_decisions", { environment: `eq.${environment}`, select: "*", order: "created_at.desc", limit: "10" }),
      supabaseGet("opportunity_candidates", { environment: `eq.${environment}`, select: "*", order: "created_at.desc", limit: "10" }),
      supabaseGet("model_registry", { select: "*", order: "created_at.desc", limit: "10" }),
      supabaseGet("data_source_registry", { select: "*", order: "updated_at.desc", limit: "15" }),
      supabaseGet("research_runs", { select: "*", order: "started_at.desc", limit: "10" }),
    ]);

    return {
      generatedAt: new Date().toISOString(),
      source: "supabase",
      environment,
      control: {
        frozen: controlRows?.[0]?.frozen !== false,
        reason: (controlRows?.[0]?.reason as string | null) ?? null,
        updated_at: (controlRows?.[0]?.updated_at as string | null) ?? null,
      },
      account: accountRows?.[0] ?? null,
      positions: positions ?? [],
      activeOrders: activeOrders ?? [],
      reconciliations: reconciliations ?? [],
      riskDecisions: riskDecisions ?? [],
      opportunities: opportunities ?? [],
      models: models ?? [],
      dataSources: dataSources ?? [],
      research: research ?? [],
      note: null,
    };
  } catch (error) {
    return {
      generatedAt: new Date().toISOString(),
      source: "error",
      environment,
      control: { frozen: true, reason: "DASHBOARD_DATA_SOURCE_ERROR", updated_at: null },
      account: null,
      positions: [],
      activeOrders: [],
      reconciliations: [],
      riskDecisions: [],
      opportunities: [],
      models: [],
      dataSources: [],
      research: [],
      note: error instanceof Error ? error.message : "Unknown dashboard data-source error",
    };
  }
}
