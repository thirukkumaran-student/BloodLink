/**
 * Hospital review queue — OWNER: D3 (spec §5, §8).
 *
 * The gate between an individual's request and an official BloodLink request:
 * nothing is matched, notified or coordinated before a hospital approves a need.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Banner,
  Button,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  Modal,
  PageHeader,
  StatusBadge,
  Textarea,
  useToast,
} from "@bloodlink/ui";
import { ApiError } from "../../api/client";
import { hospitalApi } from "../../api/endpoints";
import { COMPONENT_LABELS, URGENCY_LABELS } from "../../api/types";
import { CLINICAL_DISCLAIMER } from "../../lib/capabilities";
import { dueLabel, formatDateTime } from "../../lib/format";

function HospitalQueuePage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [decision, setDecision] = useState(null); // { need, verdict }
  const [reason, setReason] = useState("");

  const queue = useQuery({ queryKey: ["hospital", "queue"], queryFn: () => hospitalApi.reviewQueue() });

  const review = useMutation({
    mutationFn: ({ needId, verdict, note }) => hospitalApi.reviewNeed(needId, verdict, note),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: ["hospital", "queue"] });
      queryClient.invalidateQueries({ queryKey: ["hospital", "approvedNeeds"] });
      setDecision(null);
      setReason("");
      toast.success(
        variables.verdict === "APPROVED" ? "Requirement approved" : "Requirement rejected",
        variables.verdict === "APPROVED"
          ? "Create the BloodLink request from the request board to start matching donors."
          : "The submitter has been told the outcome.",
      );
    },
    onError: (error) => toast.error("Could not record the decision", readable(error)),
  });

  function readable(error) {
    if (error instanceof ApiError && error.details?.length) {
      return error.details.map((detail) => detail.message).filter(Boolean).join(" ") || error.message;
    }
    return error?.message ?? "Unexpected error";
  }

  const items = queue.data?.items ?? [];
  const pendingCount = items.filter((need) => need.status === "PENDING_HOSPITAL_REVIEW").length;

  const columns = [
    {
      key: "reference",
      header: "Requirement",
      render: (need) => (
        <div className="bl-stack-sm">
          <strong>
            {need.bloodGroup} · {COMPONENT_LABELS[need.component] ?? need.component} · {need.units}u
          </strong>
          <span className="bl-muted bl-small">
            {URGENCY_LABELS[need.urgency] ?? need.urgency} · required {dueLabel(need.requiredBy)}
          </span>
        </div>
      ),
    },
    {
      key: "submitter",
      header: "Submitted by",
      render: (need) => (
        <div className="bl-stack-sm">
          <span>{need.submittedBy?.fullName ?? "—"}</span>
          <span className="bl-muted bl-small">{formatDateTime(need.createdAt)}</span>
        </div>
      ),
    },
    {
      key: "notes",
      header: "Coordination notes",
      render: (need) => <span className="bl-muted">{need.additionalNotes ?? "—"}</span>,
    },
    {
      key: "status",
      header: "Status",
      render: (need) => <StatusBadge status={need.status} />,
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (need) =>
        need.status === "PENDING_HOSPITAL_REVIEW" ? (
          <div className="bl-row" style={{ gap: "var(--bl-space-2)", justifyContent: "flex-end" }}>
            <Button size="sm" variant="outline" onClick={() => setDecision({ need, verdict: "REJECTED" })}>
              Reject
            </Button>
            <Button size="sm" variant="primary" onClick={() => setDecision({ need, verdict: "APPROVED" })}>
              Approve
            </Button>
          </div>
        ) : (
          <span className="bl-muted bl-small">
            {need.status === "CONVERTED" ? "Request created" : "Reviewed"}
          </span>
        ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Review queue"
        subtitle="Requirements submitted to your hospital. Nothing is matched with donors until you approve."
        actions={
          <Button variant="outline" loading={queue.isFetching} onClick={() => queue.refetch()}>
            Refresh
          </Button>
        }
      />

      {pendingCount ? (
        <Banner tone="info" title={`${pendingCount} awaiting your decision`}>
          Approval is a coordination gate, not a clinical one — your medical team keeps every clinical
          decision.
        </Banner>
      ) : null}

      {queue.isLoading ? <LoadingState label="Loading the review queue…" /> : null}
      {queue.error ? <ErrorState message={queue.error.message} onRetry={() => queue.refetch()} /> : null}

      {!queue.isLoading && !queue.error && !items.length ? (
        <EmptyState
          title="Nothing to review"
          hint="Requirements addressed to your hospital will appear here."
        />
      ) : null}

      {items.length ? (
        <Card flush>
          <DataTable columns={columns} rows={items} rowKey={(need) => need.id} />
        </Card>
      ) : null}

      <Modal
        open={Boolean(decision)}
        title={decision?.verdict === "APPROVED" ? "Approve this requirement?" : "Reject this requirement?"}
        onClose={() => {
          setDecision(null);
          setReason("");
        }}
        footer={
          <>
            <Button
              variant="outline"
              onClick={() => {
                setDecision(null);
                setReason("");
              }}
            >
              Cancel
            </Button>
            <Button
              variant={decision?.verdict === "APPROVED" ? "primary" : "danger"}
              loading={review.isPending}
              disabled={decision?.verdict === "REJECTED" && !reason.trim()}
              onClick={() =>
                review.mutate({
                  needId: decision.need.id,
                  verdict: decision.verdict,
                  note: reason || null,
                })
              }
            >
              {decision?.verdict === "APPROVED" ? "Approve" : "Reject"}
            </Button>
          </>
        }
      >
        <div className="bl-stack">
          <p className="bl-muted">
            {decision?.need.bloodGroup} · {COMPONENT_LABELS[decision?.need.component] ?? decision?.need.component}{" "}
            · {decision?.need.units} unit(s) · required {dueLabel(decision?.need.requiredBy)}
          </p>
          {decision?.verdict === "APPROVED" ? (
            <Banner tone="muted">
              After approval, create the BloodLink request from the <strong>Request board</strong>.
              That is the step that matches compatible donors by distance.
            </Banner>
          ) : null}
          <label className="bl-field">
            <span className="bl-field__label">
              {decision?.verdict === "APPROVED" ? "Note for the submitter (optional)" : "Reason (required)"}
            </span>
            <Textarea
              rows={3}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Coordination context only — the submitter sees this."
            />
          </label>
          <div className="bl-notice">{CLINICAL_DISCLAIMER}</div>
        </div>
      </Modal>
    </>
  );
}

export { HospitalQueuePage };
