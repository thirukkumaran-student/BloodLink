import { useState } from "react";
import {
  Button,
  Card,
  DataTable,
  ErrorState,
  LoadingState,
  Modal,
  PageHeader,
  StatCard,
  StatusBadge,
  Textarea,
  Tabs,
  useToast
} from "@bloodlink/ui";
import { useDonations, useDonorResponses, useWithdrawResponse } from "../../app/hooks";
import { formatDate, formatDateTime, relativeTime } from "../../lib/format";
function DonorCommitmentsPage({ user }) {
  const toast = useToast();
  const responses = useDonorResponses();
  const donations = useDonations();
  const withdraw = useWithdrawResponse();
  const [tab, setTab] = useState("responses");
  const [withdrawTarget, setWithdrawTarget] = useState(null);
  const [reason, setReason] = useState("");
  const responseColumns = [
    {
      key: "reference",
      header: "Request",
      render: (row) => <span className="bl-mono">{row.requestReference ?? row.requestId.slice(0, 8)}</span>
    },
    { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
    {
      key: "standby",
      header: "Standby",
      render: (row) => row.standbyStatus === "NONE" ? <span className="bl-subtle">—</span> : <StatusBadge status={row.standbyStatus} />
    },
    { key: "confirmed", header: "Accepted", render: (row) => relativeTime(row.confirmedAt) },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (row) => ["ACCEPTED", "SELECTED", "STANDBY"].includes(row.status) ? <Button variant="outline" size="sm" onClick={() => setWithdrawTarget(row)}>
            Withdraw
          </Button> : <span className="bl-subtle">Closed</span>
    }
  ];
  const donationColumns = [
    { key: "date", header: "Confirmed", render: (row) => formatDate(row.confirmedAt) },
    { key: "group", header: "Group", render: (row) => row.bloodGroup },
    { key: "component", header: "Component", render: (row) => row.component },
    { key: "units", header: "Units", render: (row) => row.units },
    { key: "reference", header: "Hospital reference", render: (row) => row.hospitalReference ?? "\u2014" }
  ];
  async function confirmWithdraw() {
    if (!withdrawTarget) return;
    try {
      await withdraw.mutateAsync({ responseId: withdrawTarget.id, reason: reason || void 0 });
      toast.success("Withdrawn", "The hospital has been told and can arrange backup.");
      setWithdrawTarget(null);
      setReason("");
    } catch (caught) {
      toast.error("Could not withdraw", caught.message);
    }
  }
  return <><PageHeader
    title="My commitments"
    subtitle="Every request you accepted, and every donation a hospital confirmed."
  /><div className="bl-grid-stats" style={{ marginBottom: "var(--bl-space-5)" }}><StatCard label="Active commitments" value={responses.data?.items.filter((item) => ["ACCEPTED", "SELECTED", "STANDBY"].includes(item.status)).length ?? 0} /><StatCard label="Confirmed donations" value={donations.data?.items.length ?? 0} /><StatCard label="Units contributed" value={donations.data?.totalUnits ?? 0} /></div><Card
    flush={false}
    title="History"
    actions={<Tabs
      tabs={[
        { id: "responses", label: "Responses", count: responses.data?.items.length },
        { id: "donations", label: "Donations", count: donations.data?.items.length }
      ]}
      active={tab}
      onChange={setTab}
    />}
  >{tab === "responses" ? responses.isLoading ? <LoadingState /> : responses.error ? <ErrorState message={responses.error.message} onRetry={() => responses.refetch()} /> : <DataTable
    columns={responseColumns}
    rows={responses.data?.items ?? []}
    rowKey={(row) => row.id}
    emptyTitle="No responses yet"
    emptyHint="When you accept a request it appears here with its coordination status."
  /> : donations.isLoading ? <LoadingState /> : <DataTable
    columns={donationColumns}
    rows={donations.data?.items ?? []}
    rowKey={(row) => row.id}
    emptyTitle="No confirmed donations yet"
    emptyHint="A donation is recorded only after the hospital confirms fulfilment."
  />}</Card><Card title="Why acceptance is not a donation" subtitle="Spec §10, enforced by the API."><div className="bl-stack-sm"><p className="bl-muted">
            An accepted response means you intend to donate. The hospital confirms fulfilment after
            the donation is completed and screened, and only then does it become part of your history
            and start your recovery window.
          </p>{user ? <span className="bl-subtle">Signed in as {user.fullName}</span> : null}</div></Card><Modal
    open={Boolean(withdrawTarget)}
    title="Withdraw this commitment?"
    onClose={() => setWithdrawTarget(null)}
    footer={<><Button variant="outline" onClick={() => setWithdrawTarget(null)}>
              Keep it
            </Button><Button variant="danger" loading={withdraw.isPending} onClick={() => void confirmWithdraw()}>
              Withdraw
            </Button></>}
  ><div className="bl-stack"><p className="bl-muted">
            If you were already selected, the request will be marked as needing backup so the hospital
            can find someone else quickly.
          </p><label className="bl-field"><span className="bl-label">Reason (optional, shared with the hospital)</span><Textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={240} /></label>{withdrawTarget ? <span className="bl-subtle">Last updated {formatDateTime(withdrawTarget.createdAt)}</span> : null}</div></Modal></>;
}
export {
  DonorCommitmentsPage
};
