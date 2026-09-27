import { redirect } from "next/navigation";
import DashboardShell from "../components/dashboard-shell";
import { getDashboardSnapshot } from "../lib/dashboard";
import { isCockpitAuthorized } from "../lib/auth";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  if (!(await isCockpitAuthorized())) redirect("/login");
  const snapshot = await getDashboardSnapshot();
  return <DashboardShell initial={snapshot} />;
}
