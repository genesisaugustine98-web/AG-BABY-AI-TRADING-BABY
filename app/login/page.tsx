import { authConfigured } from "../../lib/auth";

export const dynamic = "force-dynamic";

export default function LoginPage() {
  const configured = authConfigured();
  return (
    <main className="login-shell">
      <section className="login-card">
        <p className="eyebrow">AG // INSTITUTIONAL FX EDGE</p>
        <h1>Operator access</h1>
        <p className="muted">The trading cockpit is server-authenticated. Credentials never enter the browser runtime.</p>
        {!configured ? (
          <div className="alert"><strong>Access not configured.</strong> Set <code>COCKPIT_ACCESS_TOKEN</code> in the server environment before exposing the cockpit.</div>
        ) : (
          <form action="/api/auth/login" method="post" className="login-form">
            <label htmlFor="token">Access token</label>
            <input id="token" name="token" type="password" autoComplete="current-password" required />
            <button type="submit">Enter cockpit</button>
          </form>
        )}
        <p className="login-note">Live trading remains disabled by architecture and policy.</p>
      </section>
    </main>
  );
}
