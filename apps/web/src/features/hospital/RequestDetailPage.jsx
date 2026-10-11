/**
 * Request coordination workspace — OWNER: D3 (spec §9, §10).
 *
 * One screen for the whole lifecycle: the journal, the responders, the outreach
 * picture, and the three decisions a hospital makes — drive the status, select
 * the donor, confirm fulfilment.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Banner,
  Button,
  Card,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  Modal,
  PageHeader,
  StatCard,
  StatusBadge,
  Textarea,
  useToast,
} from "@bloodlink/ui";
import { ApiError } from "../../api/client";
import { hospitalApi } from "../../api/endpoints";
import {
  COMPONENT_LABELS,
  REQUEST_ACCEPTS_RESPONSES,
  REQUEST_TERMINAL_STATUSES,
  REQUEST_TRANSITIONS,
  URGENCY_LABELS,
} from "../../api/types";
import { CLINICAL_DISCLAIMER } from "../../lib/capabilities";
import { dueLabel, formatDateTime, relativeTime } from "../../lib/format";

function HospitalRequestDetailPage() {
  const { requestId } = useParams();
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [transitionTarget, setTransitionTarget] = useState(null);
  const [reason, setReason] = useState("");
  const [selectTarget, setSelectTarget] = useState(null);
  const [standbyIds, setStandbyIds] = useState([]);
  const [fulfilOpen, setFulfilOpen] = useState(false);
  const [hospitalReference, setHospitalReference] = useState("");

  const detail = useQuery({
    queryKey: ["hospital", "request", requestId],
    queryFn: () => hospitalApi.requestDetail(requestId),
    enabled: Boolean(requestId),
  });
  const outreach = useQuery({
    queryKey: ["hospital", "request", requestId, "outreach"],
    queryFn: () => hospitalApi.outreach(requestId),
    enabled: Boolean(requestId),
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["hospital", "request", requestId] });
    queryClient.invalidateQueries({ queryKey: ["hospital", "requests"] });
    queryClient.invalidateQueries({ queryKey: ["hospital", "request", requestId, "outreach"] });
  }

  function readable(error) {
    if (error instanceof ApiError && error.details?.length) {
      return error.details.map((item) => item.message).filter(Boolean).join(" ") || error.message;
    }
    return error?.message ?? "Unexpected error";
  }

  const transition = useMutation({
    mutationFn: (payload) => hospitalApi.transition(requestId, payload.toStatus, payload.reason),
    onSuccess: (_result, variables) => {
      invalidate();
      setTransitionTarget(null);
      setReason("");
      toast.success(`Moved to ${variables.toStatus.replace(/_/g, " ")}`, "The lifecycle journal records it.");
    },
    onError: (error) => toast.error("Could not change the status", readable(error)),
  });

  const selectDonor = useMutation({
    mutationFn: (payload) =>
      hospitalApi.selectDonor(requestId, payload.donorResponseId, payload.alsoMoveToStandby ?? []),
    onSuccess: () => {
      invalidate();
      setSelectTarget(null);
      setStandbyIds([]);
      toast.success(
        "Donor selected",
        "They have been told they were selected; standby donors were told to hold.",
      );
    },
    onError: (error) => toast.error("Could not select the donor", readable(error)),
  });

  const confirmFulfillment = useMutation({
    mutationFn: (payload) => hospitalApi.confirmFulfillment(requestId, payload),
    onSuccess: () => {
      invalidate();
      setFulfilOpen(false);
      setHospitalReference("");
      toast.success(
        "Request fulfilled",
        "Donation records were created for the donors who donated; their cooldown starts now.",
      );
    },
    onError: (error) => toast.error("Could not confirm fulfilment", readable(error)),
  });

  if (detail.isLoading) return <LoadingState label="Loading the request…" />;
  if (detail.error)
    return <ErrorState message={detail.error.message} onRetry={() => detail.refetch()} />;

  const request = detail.data;
  if (!request) return <EmptyState title="Request not found" />;

  const nextStates = REQUEST_TRANSITIONS[request.status] ?? [];
  const responders = request.responses ?? [];
  const activeResponders = responders.filter((item) =>
    ["ACCEPTED", "SELECTED", "STANDBY"].includes(item.status),
  );
  const selectable = responders.filter((item) => ["ACCEPTED", "STANDBY"].includes(item.status));
  const canCoordinate = !REQUEST_TERMINAL_STATUSES.includes(request.status);
  const summary = outreach.data;

  function openSelect(response) {
    setSelectTarget(response);
    setStandbyIds(selectable.filter((item) => item.id !== response.id).map((item) => item.id));
  }

  return (
    <>
      <PageHeader
        title={`${request.bloodGroup} · ${COMPONENT_LABELS[request.component] ?? request.component}`}
        subtitle={
          <span>
            <span className="bl-mono">{request.reference}</span> · {request.hospital?.name} · required{" "}
            {dueLabel(request.requiredBy)}
          </span>
        }
        actions={
          <>
            <Button variant="outline" onClick={() => navigate("/hospital/requests")}>
              Back to board
            </Button>
            <StatusBadge status={request.status} />
          </>
        }
      />

      {!canCoordinate ? (
        <Banner tone={request.status === "FULFILLED" ? "success" : "muted"} title={`This request is ${request.status.toLowerCase()}`}>
          Terminal requests keep their journal for audit; no further coordination actions are
          available.
        </Banner>
      ) : null}

      {request.status === "BACKUP_REQUIRED" ? (
        <Banner tone="danger" title="Backup coordination required">
          {request.backupReason ?? "A selected donor could not continue."} BloodLink widened outreach to
          the next donor tier — activate a standby donor or select a new one.
        </Banner>
      ) : null}

      <div className="bl-grid-stats" style={{ marginBottom: "var(--bl-space-5)" }}>
        <StatCard label="Units" value={`${request.unitsCoordinated}/${request.unitsRequired}`} hint="Coordinated / required" />
        <StatCard
          label="Responders"
          value={activeResponders.length}
          hint={`${request.responders?.accepted ?? 0} accepted · ${request.responders?.standby ?? 0} standby`}
        />
        <StatCard
          label="Outreach"
          value={summary?.notified ?? "—"}
          hint={`${summary?.candidates ?? 0} candidates · tier ${request.outreachTier || 0}`}
        />
        <StatCard label="Urgency" value={URGENCY_LABELS[request.urgency] ?? request.urgency} hint={`Opened ${relativeTime(request.openedAt)}`} />
      </div>

      <div className="bl-grid-2" style={{ alignItems: "start" }}>
        <Card
          title="Lifecycle"
          subtitle="Every move is validated against the platform transition table."
          actions={
            canCoordinate ? (
              <Button size="sm" variant="outline" onClick={() => setTransitionTarget({ toStatus: "" })}>
                Change status
              </Button>
            ) : null
          }
        >
          <div className="bl-stack-sm">
            {nextStates.length ? (
              <div className="bl-row" style={{ flexWrap: "wrap", gap: "var(--bl-space-2)" }}>
                {nextStates.map((status) => (
                  <Button
                    key={status}
                    size="sm"
                    variant={status === "BACKUP_REQUIRED" ? "danger" : "outline"}
                    onClick={() => setTransitionTarget({ toStatus: status })}
                  >
                    {status.replace(/_/g, " ")}
                  </Button>
                ))}
              </div>
            ) : (
              <span className="bl-muted bl-small">No further transitions from this status.</span>
            )}
            <div className="bl-timeline">
              {(request.events ?? []).slice().reverse().map((event) => (
                <div className="bl-timeline__item" key={event.id}>
                  <div className="bl-timeline__dot" aria-hidden="true" />
                  <div>
                    <div>
                      <strong>{event.eventType.replace(/_/g, " ")}</strong>
                      {event.toStatus ? <> → <StatusBadge status={event.toStatus} /></> : null}
                    </div>
                    <div className="bl-muted bl-small">
                      {formatDateTime(event.createdAt)}
                      {event.detail?.reason ? ` · ${event.detail.reason}` : ""}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <Card
          title="Responders"
          subtitle="Compatible donors who accepted. Coordinates are never shared."
          actions={
            canCoordinate ? (
              <Button size="sm" variant="primary" onClick={() => setFulfilOpen(true)}>
                Confirm fulfilment
              </Button>
            ) : null
          }
        >
          {responders.length ? (
            <div className="bl-stack-sm">
              {responders.map((response) => (
                <div className="bl-responder" key={response.id}>
                  <div className="bl-responder__main">
                    <div className="bl-responder__name">{response.donorName ?? "Donor"}</div>
                    <div className="bl-muted bl-small">
                      {response.distanceBand ?? "Distance withheld"} · accepted{" "}
                      {relativeTime(response.confirmedAt)}
                    </div>
                  </div>
                  <div className="bl-responder__side">
                    <StatusBadge status={response.status} />
                    {canCoordinate && ["ACCEPTED", "STANDBY"].includes(response.status) ? (
                      <Button size="sm" variant="outline" onClick={() => openSelect(response)}>
                        Select
                      </Button>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No responses yet"
              hint={`Donors in tier ${request.outreachTier || 0} were notified. Widen outreach or move the request to backup if time is short.`}
            />
          )}
        </Card>
      </div>

      <div style={{ marginTop: "var(--bl-space-5)" }}>
      <Card title="Outreach" subtitle="Aggregate counts by tier — no donor identities.">
        {summary?.tiers?.length ? (
          <div className="bl-stack-sm">
            {summary.tiers.map((tier) => (
              <div className="bl-row-between" key={tier.tier}>
                <span>Tier {tier.tier}</span>
                <span className="bl-muted">
                  {tier.notified} notified of {tier.candidates} candidates
                </span>
              </div>
            ))}
            <div className="bl-row-between">
              <span>Units outstanding</span>
              <span className="bl-muted">{summary.unitsOutstanding}</span>
            </div>
          </div>
        ) : (
          <span className="bl-muted">No outreach has been dispatched yet.</span>
        )}
        {request.coordinationNote ? (
          <div className="bl-notice" style={{ marginTop: "var(--bl-space-4)" }}>
            <strong>Coordination note:</strong> {request.coordinationNote}
          </div>
        ) : null}
        <div className="bl-muted bl-small" style={{ marginTop: "var(--bl-space-4)" }}>
          <Link to="/messages">Open the coordination thread</Link> to message responders.
        </div>
      </Card>
      </div>

      <Modal
        open={Boolean(transitionTarget)}
        title="Change the request status"
        onClose={() => setTransitionTarget(null)}
        footer={
          <>
            <Button variant="outline" onClick={() => setTransitionTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={transition.isPending}
              disabled={!transitionTarget?.toStatus}
              onClick={() =>
                transition.mutate({ toStatus: transitionTarget.toStatus, reason: reason || null })
              }
            >
              Apply transition
            </Button>
          </>
        }
      >
        {transitionTarget ? (
          <div className="bl-stack">
            <p className="bl-muted">
              Current status <StatusBadge status={request.status} /> — choose the next step. Only moves
              the platform allows from here are offered.
            </p>
            <FormField label="Next status" required>
              <div className="bl-row" style={{ flexWrap: "wrap", gap: "var(--bl-space-2)" }}>
                {nextStates.map((status) => (
                  <Button
                    key={status}
                    size="sm"
                    variant={transitionTarget.toStatus === status ? "primary" : "outline"}
                    onClick={() => setTransitionTarget({ toStatus: status })}
                  >
                    {status.replace(/_/g, " ")}
                  </Button>
                ))}
              </div>
            </FormField>
            <FormField label="Reason / coordination note" hint="Recorded in the journal. No clinical detail.">
              <Textarea rows={3} value={reason} onChange={(event) => setReason(event.target.value)} />
            </FormField>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(selectTarget)}
        title="Select this donor"
        onClose={() => setSelectTarget(null)}
        footer={
          <>
            <Button variant="outline" onClick={() => setSelectTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={selectDonor.isPending}
              onClick={() =>
                selectDonor.mutate({
                  donorResponseId: selectTarget.id,
                  alsoMoveToStandby: standbyIds,
                })
              }
            >
              Confirm selection
            </Button>
          </>
        }
      >
        {selectTarget ? (
          <div className="bl-stack">
            <p className="bl-muted">
              <strong>{selectTarget.donorName ?? "Donor"}</strong> ·{" "}
              {selectTarget.distanceBand ?? "distance withheld"} ·{" "}
              accepted {relativeTime(selectTarget.confirmedAt)}
            </p>
            <FormField
              label="Keep as standby"
              hint="Standby donors are held for the backup path; the others are released."
            >
              <div className="bl-stack-sm">
                {selectable
                  .filter((item) => item.id !== selectTarget.id)
                  .map((item) => (
                    <label key={item.id} className="bl-check">
                      <input
                        type="checkbox"
                        checked={standbyIds.includes(item.id)}
                        onChange={(event) =>
                          setStandbyIds((current) =>
                            event.target.checked
                              ? [...current, item.id]
                              : current.filter((id) => id !== item.id),
                          )
                        }
                      />
                      <span>
                        {item.donorName ?? "Donor"} · {item.distanceBand ?? "distance withheld"}
                      </span>
                    </label>
                  ))}
                {selectable.length < 2 ? (
                  <span className="bl-muted bl-small">No other responders to hold.</span>
                ) : null}
              </div>
            </FormField>
            <Banner tone="muted">
              Selection tells the donor they were chosen and moves the request to COORDINATING. It is
              still not a donation.
            </Banner>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={fulfilOpen}
        title="Confirm fulfilment"
        onClose={() => setFulfilOpen(false)}
        footer={
          <>
            <Button variant="outline" onClick={() => setFulfilOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={confirmFulfillment.isPending}
              onClick={() =>
                confirmFulfillment.mutate({
                  hospitalReference: hospitalReference || null,
                  donorProfileIds: [],
                })
              }
            >
              Record donation and close
            </Button>
          </>
        }
      >
        <div className="bl-stack">
          <p className="bl-muted">
            Confirming records a donation for the selected and standby donors, starts their recovery
            cooldown, and closes the request. Only confirm once blood has been received.
          </p>
          <FormField label="Hospital reference" hint="Your internal record id, shown to the donor">
            <Input
              value={hospitalReference}
              placeholder="e.g. BB-2026-0912"
              onChange={(event) => setHospitalReference(event.target.value)}
            />
          </FormField>
          <div className="bl-notice">
            {CLINICAL_DISCLAIMER} BloodLink stores no screening or crossmatch result.
          </div>
        </div>
      </Modal>
    </>
  );
}

export { HospitalRequestDetailPage };
