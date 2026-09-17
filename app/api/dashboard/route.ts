import { NextResponse } from "next/server";
import { getDashboardSnapshot } from "@/lib/dashboard";

export const dynamic = "force-dynamic";

export async function GET() {
  const snapshot = await getDashboardSnapshot();
  return NextResponse.json(snapshot, {
    headers: {
      "Cache-Control": "no-store, max-age=0",
      "X-AG-Execution-Environment": snapshot.environment,
      "X-AG-Fail-Closed": snapshot.control.frozen ? "true" : "false",
    },
  });
}
