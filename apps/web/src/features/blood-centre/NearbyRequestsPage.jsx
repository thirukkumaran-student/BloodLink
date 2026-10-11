/**
 * Blood-centre discovery — OWNER: D4 (spec §5, §13).
 *
 * Open requests near the centre, and availability offers it can submit back to
 * the requesting hospital. Offers never carry patient information.
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
import { bloodCentreApi } from "../../api/endpoints";
import { COMPONENT_LABELS, URGENCY_LABELS } from "../../api/types";
import { dueLabel, formatDateTime } from "../../lib/format";

const OFFER_STATUSES = [
  { value: "AVAILABLE", label: "Available — we can supply" },
  { value: "PARTIAL", label: "Partial — fewer units than requested" },
  { value: "UNAVAILABLE", label: "Unavailable — no stock of this component" },
];

function BloodCentrePage({ user }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [radiusKm, setRadiusKm] = useState("25");
  const [offerFor, setOfferFor] = useState(null);
  const [draft, setDraft] = useState({ status: "AVAILABLE", unitsOffered: "", notes: "" });

  const nearby = useQuery({
    queryKey: ["blood-centre", "nearby", radiusKm],
    queryFn: () => bloodCentreApi.nearbyRequests(Number(radiusKm) || 25),
  });
  const offers = useQuery({
    queryKey: ["blood-centre", "offers"],
    queryFn: bloodCentreApi.myResponses,
  });

  const submitOffer = useMutation({
    mutationFn: (payload) => bloodCentreApi.submitResponse(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["blood-centre", "offers"] });
      queryClient.invalidateQueries({ queryKey: ["blood-centre", "nearby"] });
      setOfferFor(null);
      setDraft({ status: "AVAILABLE", unitsOffered: "", notes: "" });
      toast.success("Offer sent", "The requesting hospital has been notified.");
    },
    onError: (error) => toast.error("Could not send the offer", readable(error)),
  });

  function readable(error) {
    if (error instanceof ApiError && error.details?.length) {
      return error.details.map((detail) => detail.message).filter(Boolean).join(" ") || error.message;
    }
    return error?.message ?? "Unexpected error";
  }

  const items = nearby.data?.items ?? [];
  const myOffers = offers.data?.items ?? [];

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
      key: "hospital",
      header: "Hospital",
      render: (request) => (
        <div className="bl-stack-sm">
          <span>{request.hospital?.name ?? "—"}</span>
          <span className="bl-muted bl-small">{request.distanceBand ?? "distance unavailable"}</span>
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
      key: "requiredBy",
      header: "Required by",
      render: (request) => <span>{dueLabel(request.requiredBy)}</span>,
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (request) =>
        request.hasResponded ? (
          <span className="bl-muted bl-small">Offer sent</span>
        ) : (
          <Button
            size="sm"
            variant="primary"
            onClick={() => {
              setOfferFor(request);
              setDraft({ status: "AVAILABLE", unitsOffered: String(request.unitsRequired), notes: "" });
            }}
          >
            Offer availability
          </Button>
        ),
    },
  ];

  return (
    <>
      <PageHeader
        title={user?.organization?.name ?? "Blood centre"}
        subtitle="Open requests near your centre, and the availability you have offered."
        actions={
          <Button variant="outline" loading={nearby.isFetching} onClick={() => nearby.refetch()}>
            Refresh
          </Button>
        }
      />

      <div className="bl-grid-stats" style={{ marginBottom: "var(--bl-space-5)" }}>
        <StatCard label="Requests nearby" value={items.length} hint={`Within ~${radiusKm} km`} />
        <StatCard
          label="Emergency"
          value={items.filter((request) => request.urgency === "EMERGENCY").length}
          hint="Needs a fast answer"
        />
        <StatCard label="Offers sent" value={myOffers.length} hint="Across all requests" />
        <StatCard
          label="Awaiting acceptance"
          value={myOffers.filter((offer) => offer.status === "AVAILABLE" || offer.status === "PARTIAL").length}
          hint="Hospital has not closed them out"
        />
      </div>

      <div className="bl-row" style={{ marginBottom: "var(--bl-space-4)" }}>
        <FormField label="Search radius (km)">
          <Input
            type="number"
            min="1"
            max="250"
            value={radiusKm}
            style={{ maxWidth: "9rem" }}
            onChange={(event) => setRadiusKm(event.target.value)}
          />
        </FormField>
      </div>

      {nearby.isLoading ? <LoadingState label="Finding requests near you…" /> : null}
      {nearby.error ? <ErrorState message={nearby.error.message} onRetry={() => nearby.refetch()} /> : null}

      {items.length ? (
        <Card flush>
          <DataTable columns={columns} rows={items} rowKey={(request) => request.id} />
        </Card>
      ) : null}

      {!nearby.isLoading && !nearby.error && !items.length ? (
        <EmptyState
          title="No open requests in range"
          hint="Widen the radius, or wait — requests are matched as hospitals open them."
        />
      ) : null}

      <div style={{ marginTop: "var(--bl-space-5)" }}>
        <Card title="Your offers" subtitle="What your centre has committed to the network.">
          {myOffers.length ? (
            <div className="bl-stack-sm">
              {myOffers.map((offer) => (
                <div className="bl-row-between" key={offer.id}>
                  <div>
                    <div>
                      <strong>{offer.requestBloodGroup ?? "—"}</strong> · {offer.requestReference ?? "request"}
                    </div>
                    <div className="bl-muted bl-small">
                      {offer.hospitalName ?? "Hospital"} · {formatDateTime(offer.createdAt)}
                    </div>
                  </div>
                  <div className="bl-row" style={{ gap: "var(--bl-space-2)" }}>
                    {offer.unitsOffered ? <span className="bl-muted bl-small">{offer.unitsOffered}u</span> : null}
                    <StatusBadge status={offer.status} />
                    <StatusBadge status={offer.requestStatus} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="No offers yet" hint="Offer availability on a nearby request to start." />
          )}
        </Card>
      </div>

      <Modal
        open={Boolean(offerFor)}
        title="Offer availability"
        onClose={() => setOfferFor(null)}
        footer={
          <>
            <Button variant="outline" onClick={() => setOfferFor(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={submitOffer.isPending}
              onClick={() =>
                submitOffer.mutate({
                  bloodRequestId: offerFor.id,
                  status: draft.status,
                  unitsOffered: draft.unitsOffered ? Number(draft.unitsOffered) : undefined,
                  notes: draft.notes || undefined,
                })
              }
            >
              Send offer
            </Button>
          </>
        }
      >
        {offerFor ? (
          <div className="bl-stack">
            <p className="bl-muted">
              {offerFor.bloodGroup} · {COMPONENT_LABELS[offerFor.component] ?? offerFor.component} ·{" "}
              {offerFor.unitsRequired} unit(s) requested by {offerFor.hospital?.name ?? "the hospital"} ·
              required {dueLabel(offerFor.requiredBy)}
            </p>
            <FormField label="Availability" required>
              <Select
                value={draft.status}
                options={OFFER_STATUSES}
                onChange={(event) => setDraft((state) => ({ ...state, status: event.target.value }))}
              />
            </FormField>
            <FormField label="Units offered" hint="Leave blank if you cannot supply">
              <Input
                type="number"
                min="0"
                max="10"
                value={draft.unitsOffered}
                onChange={(event) => setDraft((state) => ({ ...state, unitsOffered: event.target.value }))}
              />
            </FormField>
            <FormField label="Notes for the hospital" hint="Stock, timing, collection constraints.">
              <Textarea
                rows={3}
                value={draft.notes}
                onChange={(event) => setDraft((state) => ({ ...state, notes: event.target.value }))}
              />
            </FormField>
            <Banner tone="muted">
              BloodLink coordinates availability only. Testing, processing, storage and issue remain
              with your facility.
            </Banner>
          </div>
        ) : null}
      </Modal>
    </>
  );
}

export { BloodCentrePage };
