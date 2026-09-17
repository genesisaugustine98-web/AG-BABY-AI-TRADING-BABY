import { NextResponse } from "next/server";
import { getDashboardSnapshot } from "@/lib/dashboard";
import { isCockpitAuthorized } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET() {
  if (!(await isCockpitAuthorized())) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401, headers: { "Cache-Control": "no-store" } });
  }
  const snapshot = await getDashboardSnapshot();
  return NextResponse.json(snapshot, {
    headers: {
      "Cache-Control": "no-store, max-age=0",
      "X-AG-Execution-Environment": snapshot.environment,
      "X-AG-Fail-Closed": snapshot.control.frozen ? "true" : "false",
    },
  });
}
