import DashboardShell from "@/components/dashboard-shell";
import { getDashboardSnapshot } from "@/lib/dashboard";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const snapshot = await getDashboardSnapshot();
  return <DashboardShell initial={snapshot} />;
}
