/**
 * Individual needs — OWNER: D2 (spec §5, §8).
 *
 * Submit a blood requirement to a chosen verified hospital and follow its review
 * outcome. The form enforces the same rules the API enforces (units range,
 * required-by lead time), and the API re-checks every one of them.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  Select,
  StatusBadge,
  Textarea,
  useToast,
} from "@bloodlink/ui";
import { ApiError } from "../../api/client";
import { patientNeedApi } from "../../api/endpoints";
import {
  BLOOD_COMPONENTS,
  BLOOD_GROUPS,
  COMPONENT_LABELS,
  URGENCIES,
  URGENCY_LABELS,
} from "../../api/types";
import { CLINICAL_DISCLAIMER, can } from "../../lib/capabilities";
import { formatDateTime, dueLabel } from "../../lib/format";

const EMPTY_FORM = {
  hospitalId: "",
  bloodGroup: "O+",
  component: "PRBC",
  units: "1",
  urgency: "URGENT",
  requiredBy: "",
  additionalNotes: "",
};

/** `datetime-local` wants `YYYY-MM-DDTHH:mm`; default to six hours from now. */
function defaultRequiredBy() {
  const target = new Date(Date.now() + 6 * 60 * 60 * 1000);
  target.setMinutes(target.getMinutes() - target.getTimezoneOffset());
  return target.toISOString().slice(0, 16);
}

function IndividualNeedsPage({ user }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM, requiredBy: defaultRequiredBy() });
  const [cancelTarget, setCancelTarget] = useState(null);

  const needs = useQuery({ queryKey: ["needs"], queryFn: patientNeedApi.listMine });
  const hospitals = useQuery({
    queryKey: ["needs", "hospitals"],
    queryFn: () => patientNeedApi.discoverHospitals(),
    enabled: formOpen,
  });

  const hospitalOptions = useMemo(
    () =>
      (hospitals.data?.items ?? []).map((hospital) => ({
        value: hospital.id,
        label: hospital.distanceBand
          ? `${hospital.name} — ${hospital.locationLabel ?? hospital.city ?? ""} (${hospital.distanceBand})`
          : `${hospital.name} — ${hospital.locationLabel ?? hospital.city ?? ""}`,
      })),
    [hospitals.data],
  );

  const createNeed = useMutation({
    mutationFn: (payload) => patientNeedApi.create(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["needs"] });
      setForm({ ...EMPTY_FORM, requiredBy: defaultRequiredBy() });
      setFormOpen(false);
      toast.success(
        "Request submitted",
        "The hospital will review it. You will be notified of the outcome.",
      );
    },
    onError: (error) =>
      toast.error("Could not submit the request", readable(error)),
  });

  const cancelNeed = useMutation({
    mutationFn: ({ id, reason }) => patientNeedApi.cancel(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["needs"] });
      setCancelTarget(null);
      toast.info("Request cancelled", "The hospital has been relieved of this requirement.");
    },
    onError: (error) => toast.error("Could not cancel", readable(error)),
  });

  function readable(error) {
    if (error instanceof ApiError && error.details?.length) {
      return error.details.map((detail) => detail.message).filter(Boolean).join(" ") || error.message;
    }
    return error?.message ?? "Unexpected error";
  }

  function submitForm() {
    createNeed.mutate({
      hospitalId: form.hospitalId,
      bloodGroup: form.bloodGroup,
      component: form.component,
      units: Number(form.units),
      urgency: form.urgency,
      requiredBy: form.requiredBy,
      additionalNotes: form.additionalNotes || null,
    });
  }

  const items = needs.data?.items ?? [];
  const pending = items.filter((need) => need.status === "PENDING_HOSPITAL_REVIEW").length;

  return (
    <>
      <PageHeader
        title="My blood requests"
        subtitle="Send a requirement to a hospital and follow its review."
        actions={
          <Button variant="primary" onClick={() => setFormOpen(true)}>
            New request
          </Button>
        }
      />

      {user?.hasDonorProfile ? null : (
        <Banner tone="muted" title="Coordinating for someone else?">
          Submit the requirement against the hospital that will treat the patient. BloodLink stores
          coordination context only — never a diagnosis or medical record.
        </Banner>
      )}

      {needs.isLoading ? <LoadingState label="Loading your requests…" /> : null}
      {needs.error ? (
        <ErrorState message={needs.error.message} onRetry={() => needs.refetch()} />
      ) : null}

      {!needs.isLoading && !items.length ? (
        <EmptyState
          title="No requests yet"
          hint="Raise a request when you know which hospital should handle it."
          action={<Button onClick={() => setFormOpen(true)}>New request</Button>}
        />
      ) : null}

      {pending ? (
        <Banner tone="info" title={`${pending} awaiting hospital review`}>
          A hospital reviews each request before it becomes an official BloodLink request. Donors are
          never contacted before that gate.
        </Banner>
      ) : null}

      <div className="bl-grid-cards">
        {items.map((need) => (
          <Card
            key={need.id}
            title={
              <span className="bl-row" style={{ gap: "var(--bl-space-2)" }}>
                {need.bloodGroup} · {COMPONENT_LABELS[need.component] ?? need.component}
                <StatusBadge status={need.status} />
              </span>
            }
            subtitle={need.hospital?.name ?? "Hospital"}
          >
            <div className="bl-stack-sm">
              <div className="bl-row-between">
                <span className="bl-muted">Units</span>
                <span>{need.units}</span>
              </div>
              <div className="bl-row-between">
                <span className="bl-muted">Urgency</span>
                <span>{URGENCY_LABELS[need.urgency] ?? need.urgency}</span>
              </div>
              <div className="bl-row-between">
                <span className="bl-muted">Required by</span>
                <span>{dueLabel(need.requiredBy)}</span>
              </div>
              <div className="bl-row-between">
                <span className="bl-muted">Submitted</span>
                <span>{formatDateTime(need.createdAt)}</span>
              </div>
              {need.reviewReason ? (
                <div className="bl-notice">
                  <strong>Hospital review:</strong> {need.reviewReason}
                </div>
              ) : null}
              {need.status === "PENDING_HOSPITAL_REVIEW" ? (
                <Button variant="outline" block onClick={() => setCancelTarget(need)}>
                  Cancel request
                </Button>
              ) : null}
            </div>
          </Card>
        ))}
      </div>

      <Modal
        open={formOpen}
        title="Request blood from a hospital"
        onClose={() => setFormOpen(false)}
        footer={
          <>
            <Button variant="outline" onClick={() => setFormOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={createNeed.isPending}
              disabled={!form.hospitalId || !form.requiredBy}
              onClick={submitForm}
            >
              Submit to hospital
            </Button>
          </>
        }
      >
        <div className="bl-stack">
          <FormField label="Hospital" required hint="Verified hospitals only">
            <Select
              value={form.hospitalId}
              placeholder={hospitals.isLoading ? "Loading hospitals…" : "Choose a hospital"}
              options={hospitalOptions}
              onChange={(event) => setForm((state) => ({ ...state, hospitalId: event.target.value }))}
            />
          </FormField>

          <div className="bl-grid-2">
            <FormField label="Blood group" required>
              <Select
                value={form.bloodGroup}
                options={BLOOD_GROUPS.map((group) => ({ value: group, label: group }))}
                onChange={(event) => setForm((state) => ({ ...state, bloodGroup: event.target.value }))}
              />
            </FormField>
            <FormField label="Component" required>
              <Select
                value={form.component}
                options={BLOOD_COMPONENTS.map((component) => ({
                  value: component,
                  label: COMPONENT_LABELS[component] ?? component,
                }))}
                onChange={(event) => setForm((state) => ({ ...state, component: event.target.value }))}
              />
            </FormField>
          </div>

          <div className="bl-grid-2">
            <FormField label="Units" required hint="1–10">
              <Input
                type="number"
                min="1"
                max="10"
                value={form.units}
                onChange={(event) => setForm((state) => ({ ...state, units: event.target.value }))}
              />
            </FormField>
            <FormField label="Urgency" required>
              <Select
                value={form.urgency}
                options={URGENCIES.map((urgency) => ({
                  value: urgency,
                  label: URGENCY_LABELS[urgency] ?? urgency,
                }))}
                onChange={(event) => setForm((state) => ({ ...state, urgency: event.target.value }))}
              />
            </FormField>
          </div>

          <FormField label="Required by" required hint="Exact date and time, at least 30 minutes ahead">
            <Input
              type="datetime-local"
              value={form.requiredBy}
              onChange={(event) => setForm((state) => ({ ...state, requiredBy: event.target.value }))}
            />
          </FormField>

          <FormField
            label="Coordination notes"
            hint="Ward, contact window, instructions. No diagnosis or test results."
          >
            <Textarea
              rows={3}
              value={form.additionalNotes}
              onChange={(event) =>
                setForm((state) => ({ ...state, additionalNotes: event.target.value }))
              }
            />
          </FormField>

          <Banner tone="muted">{CLINICAL_DISCLAIMER}</Banner>
        </div>
      </Modal>

      <Modal
        open={Boolean(cancelTarget)}
        title="Cancel this request?"
        onClose={() => setCancelTarget(null)}
        footer={
          <>
            <Button variant="outline" onClick={() => setCancelTarget(null)}>
              Keep it
            </Button>
            <Button
              variant="danger"
              loading={cancelNeed.isPending}
              onClick={() =>
                cancelNeed.mutate({ id: cancelTarget.id, reason: "No longer required" })
              }
            >
              Cancel request
            </Button>
          </>
        }
      >
        <p className="bl-muted">
          Only a request still awaiting hospital review can be cancelled. Once a hospital approves
          it, its coordination continues through the request lifecycle.
        </p>
      </Modal>
    </>
  );
}

export { IndividualNeedsPage };
