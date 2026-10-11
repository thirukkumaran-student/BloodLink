import { useState } from "react";
import { Badge, Button, Card, FormField, Input, useToast } from "@bloodlink/ui";
import { authApi } from "../../api/endpoints";
import { ROLE_LABELS } from "../../lib/capabilities";
import { PageHeader } from "@bloodlink/ui";
function AccountPage({ user, onSaved }) {
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  if (!user) return null;
  async function changePassword() {
    setBusy(true);
    setError(null);
    try {
      await authApi.changePassword(current, next);
      setCurrent("");
      setNext("");
      toast.success("Password changed", "Other sessions were signed out.");
      onSaved();
    } catch (caught) {
      const apiError = caught;
      setError(apiError.message);
    } finally {
      setBusy(false);
    }
  }
  return <><PageHeader title="My account" subtitle="Identity, organization context and effective permissions." /><div className="bl-grid" style={{ gridTemplateColumns: "minmax(0, 1.2fr) minmax(0, 1fr)" }}><Card title="Identity"><div className="bl-stack-sm"><div className="bl-row-between"><span className="bl-muted">Name</span><strong>{user.fullName}</strong></div><div className="bl-row-between"><span className="bl-muted">Email</span><span>{user.email}</span></div><div className="bl-row-between"><span className="bl-muted">Role</span><Badge tone="info">{ROLE_LABELS[user.role]}</Badge></div><div className="bl-row-between"><span className="bl-muted">Donor profile</span><Badge tone={user.hasDonorProfile ? "success" : "neutral"}>{user.hasDonorProfile ? "Enabled" : "Not created"}</Badge></div>{user.organization ? <><div className="bl-row-between"><span className="bl-muted">Organization</span><span>{user.organization.name}</span></div><div className="bl-row-between"><span className="bl-muted">Verification</span><Badge tone={user.organization.verificationStatus === "VERIFIED" ? "success" : "warning"}>{user.organization.verificationStatus}</Badge></div></> : null}</div></Card><Card title="Change password" subtitle="Changing your password signs out other sessions."><div className="bl-stack"><FormField label="Current password" htmlFor="current" required error={error}><Input id="current" type="password" value={current} onChange={(event) => setCurrent(event.target.value)} /></FormField><FormField label="New password" htmlFor="next" required hint="At least 10 characters with a number"><Input id="next" type="password" value={next} onChange={(event) => setNext(event.target.value)} /></FormField><Button variant="primary" loading={busy} onClick={() => void changePassword()}>
              Update password
            </Button></div></Card></div><div style={{ marginTop: "var(--bl-space-5)" }}><Card
    title="Effective permissions"
    subtitle="Computed by the API from the RBAC matrix. Hiding UI is never the security boundary."
  ><div className="bl-row">{user.capabilities.map((capability) => <span key={capability} className="bl-badge bl-badge--neutral" style={{ textTransform: "none" }}>{capability}</span>)}</div></Card></div></>;
}
export {
  AccountPage
};
