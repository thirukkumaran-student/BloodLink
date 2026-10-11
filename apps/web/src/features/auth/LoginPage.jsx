import { useState } from "react";
import { Button, FormField, Input, useToast } from "@bloodlink/ui";
import { session } from "../../api/client";
import { authApi } from "../../api/endpoints";
import { CLINICAL_DISCLAIMER } from "../../lib/capabilities";
import { DEMO_ACCOUNTS, DEMO_MODE, DEMO_PASSWORD } from "../../app/config";
function LoginPage({ onDone }) {
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  async function submit(nextEmail = email, nextPassword = password) {
    setBusy(true);
    setError(null);
    try {
      const result = await authApi.login(nextEmail, nextPassword);
      session.save(result);
      toast.success("Signed in", `Welcome back, ${result.user.fullName}.`);
      onDone();
      window.location.reload();
    } catch (caught) {
      const apiError = caught;
      setError(apiError.message);
      toast.error("Could not sign in", apiError.message);
    } finally {
      setBusy(false);
    }
  }
  return <div className="bl-auth"><aside className="bl-auth__aside"><div><div className="bl-row" style={{ gap: "var(--bl-space-3)" }}><span className="bl-app__logo" aria-hidden="true">
              B
            </span><span className="bl-app__brand-name">BloodLink</span></div><h1 style={{ marginTop: "var(--bl-space-6)" }}>
            Hospital-verified blood coordination.
          </h1><p style={{ marginTop: "var(--bl-space-3)" }}>
            Requests verified by hospitals, matched by distance, coordinated in the open — without
            turning anyone's medical details into data.
          </p><div className="bl-auth__points" style={{ marginTop: "var(--bl-space-6)" }}><div className="bl-auth__point"><span aria-hidden="true">🏥</span><span><strong>Hospitals verify before outreach</strong>
                No request leaves a hospital's review without approval.
              </span></div><div className="bl-auth__point"><span aria-hidden="true">📍</span><span><strong>Distance-first matching</strong>
                Tiered alerts by real proximity — district lines are not walls.
              </span></div><div className="bl-auth__point"><span aria-hidden="true">🔒</span><span><strong>Privacy by design</strong>
                Donors see "~4 km away", never an address. Notifications carry no patient identity.
              </span></div></div></div><p className="bl-auth__disclaimer">{CLINICAL_DISCLAIMER}</p></aside><div className="bl-auth__panel"><form
    className="bl-auth__form"
    onSubmit={(event) => {
      event.preventDefault();
      void submit();
    }}
  ><div><h2>Sign in</h2><p className="bl-muted" style={{ marginTop: "var(--bl-space-2)" }}>
              Use your BloodLink account. Every role signs in here.
            </p></div><FormField label="Email" htmlFor="email" required><Input
    id="email"
    type="email"
    autoComplete="email"
    value={email}
    onChange={(event) => setEmail(event.target.value)}
    placeholder="you@example.org"
    required
  /></FormField><FormField label="Password" htmlFor="password" required error={error}><Input
    id="password"
    type="password"
    autoComplete="current-password"
    value={password}
    onChange={(event) => setPassword(event.target.value)}
    required
  /></FormField><Button type="submit" variant="primary" block loading={busy}>
            Sign in
          </Button><p className="bl-subtle">
            New to BloodLink?{" "}<a href="/register" onClick={(event) => {
    event.preventDefault();
    window.location.assign("/register");
  }}>
              Create an account
            </a></p>{DEMO_MODE ? <div className="bl-auth__demo"><div className="bl-row-between"><strong>Demo accounts</strong><span className="bl-subtle">password: {DEMO_PASSWORD}</span></div><div className="bl-stack-sm" style={{ marginTop: "var(--bl-space-2)" }}>{DEMO_ACCOUNTS.map((account) => <button
    key={account.email}
    type="button"
    className="bl-auth__demo-account"
    onClick={() => {
      setEmail(account.email);
      setPassword(DEMO_PASSWORD);
      void submit(account.email, DEMO_PASSWORD);
    }}
  ><span><strong>{account.label}</strong><span className="bl-subtle"> · {account.role}</span><br /><span className="bl-subtle">{account.description}</span></span><span className="bl-badge bl-badge--info">Use</span></button>)}</div></div> : null}</form></div></div>;
}
export {
  LoginPage
};
