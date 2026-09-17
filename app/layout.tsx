import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AG Institutional FX Edge",
  description: "Research, risk, execution truth and reconciliation cockpit.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
