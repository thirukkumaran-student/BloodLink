import { useState } from "react";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  Modal,
  PageHeader,
  Select,
  StatCard,
  StatusBadge,
  Textarea,
  useToast,
  Banner
} from "@bloodlink/ui";
import { ApiError } from "../../api/client";
import { useAcceptRequest, useDonorMatches, useDonorProfile } from "../../app/hooks";
import { COMPONENT_LABELS, URGENCY_LABELS, CLINICAL_DISCLAIMER } from "../../lib/capabilities";
import { dueLabel } from "../../lib/format";
function DonorOverviewPage({ user }) {
  const toast = useToast();
  const profile = useDonorProfile();
  const matches = useDonorMatches();
  const accept = useAcceptRequest();
  const [target, setTarget] = useState(null);
  const [eta, setEta] = useState("30");
  const [remarks, setRemarks] = useState("");
  const profileMissing = profile.error instanceof ApiError && profile.error.code === "FORBIDDEN";
  const data = matches.data;
  async function confirmAccept() {
    if (!target) return;
    try {
      await accept.mutateAsync({ requestId: target.id, eta: Number(eta) || void 0, remarks: remarks || void 0 });
      toast.success("Acceptance recorded", "The hospital has been notified. Acceptance is not a donation \u2014 screening happens at the facility.");
      setTarget(null);
      setRemarks("");
    } catch (caught) {
      const error = caught;
      toast.error("Could not accept", error.message);
    }
  }
  return <><PageHeader
    title={`Hello, ${user?.fullName.split(" ")[0] ?? "donor"}`}
    subtitle="Requests matched to you by blood group and distance."
    actions={<Button variant="outline" onClick={() => matches.refetch()} loading={matches.isFetching}>
            Refresh matches
          </Button>}
  />{profileMissing ? <Banner tone="info" title="Create your donor profile first.">
          BloodLink can only match you once you tell us your blood group and locality. Open{" "}<a href="/donor/profile">donor profile</a> to enable matching.
        </Banner> : null}{profile.data ? <div className="bl-grid-stats" style={{ marginBottom: "var(--bl-space-5)" }}><StatCard label="Your blood group" value={profile.data.bloodGroup} hint={`Area ${profile.data.area ?? "\u2014"}`} /><StatCard
    label="Available for outreach"
    value={profile.data.isAvailable ? "Yes" : "No"}
    hint={profile.data.acceptsNotifications ? "Push alerts on" : "Push alerts off"}
  /><StatCard
    label="You can donate to"
    value={profile.data.canDonateTo.join(" ")}
    hint="Compatibility targets outreach only"
  /><StatCard
    label="Cooldown"
    value={profile.data.cooldownDaysRemaining ? `${profile.data.cooldownDaysRemaining} d` : "Clear"}
    hint={`${profile.data.totalDonations} confirmed donation(s)`}
  /></div> : null}{matches.isLoading ? <LoadingState label="Finding nearby requests…" /> : null}{matches.error ? <ErrorState message={matches.error.message} onRetry={() => matches.refetch()} /> : null}{data && !data.items.length ? <EmptyState
    title="No matching requests right now"
    hint="You will be notified when a compatible request opens near you."
  /> : null}<div className="bl-grid-cards">{data?.items.map((card) => <Card
    key={card.id}
    accent={card.urgency === "EMERGENCY"}
    title={<span className="bl-row" style={{ gap: "var(--bl-space-2)" }}>{card.bloodGroup} · {COMPONENT_LABELS[card.component] ?? card.component}<StatusBadge status={card.urgency} label={URGENCY_LABELS[card.urgency]} /></span>}
    subtitle={`${card.hospital?.name ?? "Hospital"} \xB7 ${card.hospital?.locationLabel ?? ""}`}
  ><div className="bl-stack-sm"><div className="bl-row-between"><span className="bl-muted">Distance</span><span>{card.distanceBand}</span></div><div className="bl-row-between"><span className="bl-muted">Units needed</span><span>{card.unitsRequired} ({card.unitsCoordinated} coordinated)
                </span></div><div className="bl-row-between"><span className="bl-muted">Required by</span><span>{dueLabel(card.requiredBy)}</span></div><div className="bl-row-between"><span className="bl-muted">Reference</span><span className="bl-mono">{card.reference}</span></div><div className="bl-notice">{CLINICAL_DISCLAIMER}</div><Button
    variant="primary"
    block
    disabled={!card.acceptingResponses}
    onClick={() => setTarget(card)}
  >{card.acceptingResponses ? "Accept donation" : "Acceptance closed"}</Button></div></Card>)}</div><Modal
    open={Boolean(target)}
    title="Confirm your acceptance"
    onClose={() => setTarget(null)}
    footer={<><Button variant="outline" onClick={() => setTarget(null)}>
              Cancel
            </Button><Button variant="primary" loading={accept.isPending} onClick={() => void confirmAccept()}>
              Confirm acceptance
            </Button></>}
  >{target ? <div className="bl-stack"><p className="bl-muted">
              You are accepting a coordination request for <strong>{target.bloodGroup}</strong>{" "}{COMPONENT_LABELS[target.component] ?? target.component} at{" "}<strong>{target.hospital?.name}</strong> ({target.distanceBand}).
            </p><Banner tone="muted">
              Accepting tells the hospital you intend to donate. A medical screening at the facility
              decides whether the donation goes ahead — BloodLink never makes that call.
            </Banner><div className="bl-grid" style={{ gridTemplateColumns: "1fr" }}><label className="bl-field"><span className="bl-label">How soon can you travel?</span><Select
    options={[
      { value: "15", label: "Within 15 minutes" },
      { value: "30", label: "Within 30 minutes" },
      { value: "60", label: "Within 1 hour" },
      { value: "180", label: "Within 3 hours" }
    ]}
    value={eta}
    onChange={(event) => setEta(event.target.value)}
  /></label><label className="bl-field"><span className="bl-label">Note for the coordinator (optional)</span><Textarea
    value={remarks}
    onChange={(event) => setRemarks(event.target.value)}
    placeholder="Anything the hospital should know for coordination (not medical history)."
    maxLength={500}
  /></label></div><p className="bl-subtle">
              Cancelling this dialog does not change anything — nothing is submitted until you press
              Confirm acceptance.
            </p></div> : null}</Modal></>;
}
export {
  DonorOverviewPage
};
