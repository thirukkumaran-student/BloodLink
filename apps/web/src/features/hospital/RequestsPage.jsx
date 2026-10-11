/**
 * Hospital request board — OWNER: D3 (spec §9).
 *
 * The organization's BloodRequests, plus the one action that starts the donor
 * side of the flow: minting a request from an approved need (which triggers
 * tier-1 outreach through D4's matching engine).
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  Banner,
  Button,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  Modal,
  PageHeader,
  Select,
  StatusBadge,
  StatCard,
  Textarea,
  useToast,
} from "@bloodlink/ui";
import { ApiError } from "../../api/client";
import { hospitalApi } from "../../api/endpoints";
import {
  BLOOD_REQUEST_STATUSES,
  COMPONENT_LABELS,
  REQUEST_TERMINAL_STATUSES,
  URGENCIES,
  URGENCY_LABELS,
} from "../../api/types";
import { dueLabel } from "../../lib/format";

const ALL = "ALL";

function HospitalRequestsPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState(ALL);
  const [mintFor, setMintFor] = useState(null);
  const [draft, setDraft] = useState({ units: "", urgency: "", note: "" });

  const board = useQuery({
    queryKey: ["hospital", "requests"],
    queryFn: () => hospitalApi.requests(),
  });
  const approvedNeeds = useQuery({
    queryKey: ["hospital", "approvedNeeds"],
    queryFn: () => hospitalApi.approvedNeeds(),
  });

  const createRequest = useMutation({
    mutationFn: (payload) => hospitalApi.createRequest(payload),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["hospital", "requests"] });
      queryClient.invalidateQueries({ queryKey: ["hospital", "approvedNeeds"] });
      queryClient.invalidateQueries({ queryKey: ["hospital", "queue"] });
      setMintFor(null);
      toast.success(
        "Request opened",
        "Compatible donors nearby have been notified through BloodLink.",
      );
      if (created?.id) navigate(`/hospital/requests/${created.id}`);
    },
    onError: (error) => toast.error("Could not open the request", readable(error)),
  });

  function readable(error) {
    if (error instanceof ApiError && error.details?.length) {
      return error.details.map((detail) => detail.message).filter(Boolean).join(" ") || error.message;
    }
    return error?.message ?? "Unexpected error";
  }

  const allRequests = board.data?.items ?? [];
  const requests = useMemo(
    () => (statusFilter === ALL ? allRequests : allRequests.filter((item) => item.status === statusFilter)),
    [allRequests, statusFilter],
  );
  const open = allRequests.filter((item) => !REQUEST_TERMINAL_STATUSES.includes(item.status));

  function openMint(need) {
    setMintFor(need);
    setDraft({ units: String(need.units), urgency: need.urgency, note: "" });
  }

  const columns = [
    {
      key: "request",
      header: "Request",
      render: (request) => (
        <div className="bl-stack-sm">
          <strong>
            {request.bloodGroup} · {COMPONENT_LABELS[request.component] ?? request.component} ·{" "}
            {request.unitsRequired}u
          </strong>
          <span className="bl-muted bl-small bl-mono">{request.reference}</span>
        </div>
      ),
    },
    {
      key: "urgency",
      header: "Urgency",
      render: (request) => (
        <StatusBadge status={request.urgency} label={URGENCY_LABELS[request.urgency]} />
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (request) => <StatusBadge status={request.status} />,
    },
    {
      key: "responders",
      header: "Responders",
      render: (request) => (
        <div className="bl-stack-sm">
          <span>
            {request.responders?.accepted ?? 0} accepted · {request.responders?.standby ?? 0} standby
          </span>
          <span className="bl-muted bl-small">
            outreach tier {request.outreachTier || 0}
          </span>
        </div>
      ),
    },
    {
      key: "requiredBy",
      header: "Required by",
      render: (request) => <span>{dueLabel(request.requiredBy)}</span>,
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (request) => (
        <Button size="sm" variant="outline" onClick={() => navigate(`/hospital/requests/${request.id}`)}>
          Open
        </Button>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Request board"
        subtitle="Open and historical BloodLink requests for your hospital."
        actions={
          <Button variant="outline" loading={board.isFetching} onClick={() => board.refetch()}>
            Refresh
          </Button>
        }
      />

      <div className="bl-grid-stats" style={{ marginBottom: "var(--bl-space-5)" }}>
        <StatCard label="Requests" value={allRequests.length} hint="All time" />
        <StatCard label="Active" value={open.length} hint="Not fulfilled, cancelled or expired" />
        <StatCard
          label="Awaiting coordination"
          value={allRequests.filter((item) => item.responders?.accepted > 0 && item.status !== "FULFILLED").length}
          hint="Accepted donors not yet selected"
        />
        <StatCard
          label="Approved needs"
          value={approvedNeeds.data?.items?.length ?? 0}
          hint="Ready to become requests"
        />
      </div>

      {(approvedNeeds.data?.items?.length ?? 0) > 0 ? (
        <Banner tone="info" title="Approved requirements are waiting to become requests">
          <div className="bl-stack-sm">
            <span>
              Reviewing a requirement is not the same as opening it. Minting the request is what
              notifies compatible donors nearby.
            </span>
            <div className="bl-row" style={{ flexWrap: "wrap", gap: "var(--bl-space-2)" }}>
              {approvedNeeds.data.items.slice(0, 4).map((need) => (
                <Button key={need.id} size="sm" onClick={() => openMint(need)}>
                  Create {need.bloodGroup} · {need.units}u request
                </Button>
              ))}
            </div>
          </div>
        </Banner>
      ) : null}

      {board.isLoading ? <LoadingState label="Loading the request board…" /> : null}
      {board.error ? <ErrorState message={board.error.message} onRetry={() => board.refetch()} /> : null}

      {allRequests.length ? (
        <>
          <div className="bl-row" style={{ margin: "var(--bl-space-4) 0" }}>
            <Select
              value={statusFilter}
              style={{ maxWidth: "18rem" }}
              options={[{ value: ALL, label: "All statuses" }, ...BLOOD_REQUEST_STATUSES.map((status) => ({ value: status, label: status.replace(/_/g, " ") }))]}
              onChange={(event) => setStatusFilter(event.target.value)}
            />
          </div>
          <Card flush>
            <DataTable
              columns={columns}
              rows={requests}
              rowKey={(request) => request.id}
              emptyTitle="No requests with that status"
              onRowClick={(request) => navigate(`/hospital/requests/${request.id}`)}
            />
          </Card>
        </>
      ) : null}

      {!board.isLoading && !board.error && !allRequests.length ? (
        <EmptyState
          title="No requests yet"
          hint="Approve a requirement in the review queue, then create the request from here."
          action={<Button onClick={() => navigate("/hospital/queue")}>Open review queue</Button>}
        />
      ) : null}

      <Modal
        open={Boolean(mintFor)}
        title="Create the BloodLink request"
        onClose={() => setMintFor(null)}
        footer={
          <>
            <Button variant="outline" onClick={() => setMintFor(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={createRequest.isPending}
              onClick={() =>
                createRequest.mutate({
                  patientNeedId: mintFor.id,
                  unitsRequired: Number(draft.units) || mintFor.units,
                  urgency: draft.urgency || mintFor.urgency,
                  coordinationNote: draft.note || null,
                })
              }
            >
              Open request and match donors
            </Button>
          </>
        }
      >
        {mintFor ? (
          <div className="bl-stack">
            <p className="bl-muted">
              {mintFor.bloodGroup} · {COMPONENT_LABELS[mintFor.component] ?? mintFor.component} ·
              required {dueLabel(mintFor.requiredBy)} · submitted by{" "}
              {mintFor.submittedBy?.fullName ?? "the requester"}
            </p>
            <div className="bl-grid-2">
              <FormField label="Units required" required>
                <Input
                  type="number"
                  min="1"
                  max="10"
                  value={draft.units}
                  onChange={(event) => setDraft((state) => ({ ...state, units: event.target.value }))}
                />
              </FormField>
              <FormField label="Urgency" required>
                <Select
                  value={draft.urgency}
                  options={URGENCIES.map((urgency) => ({
                    value: urgency,
                    label: URGENCY_LABELS[urgency] ?? urgency,
                  }))}
                  onChange={(event) => setDraft((state) => ({ ...state, urgency: event.target.value }))}
                />
              </FormField>
            </div>
            <FormField label="Coordination note" hint="Shared with responders — no patient identity">
              <Textarea
                rows={3}
                value={draft.note}
                onChange={(event) => setDraft((state) => ({ ...state, note: event.target.value }))}
              />
            </FormField>
            <Banner tone="muted">
              Opening the request notifies compatible donors nearest to your hospital first. BloodLink
              never shares their coordinates, and they still decide whether to accept.
            </Banner>
          </div>
        ) : null}
      </Modal>
    </>
  );
}

export { HospitalRequestsPage };
