const STATUS_TONES = {
  // PatientNeed
  PENDING_HOSPITAL_REVIEW: "warning",
  APPROVED: "success",
  REJECTED: "danger",
  CONVERTED: "accent",
  CANCELLED: "neutral",
  // BloodRequest
  OPEN: "info",
  RESPONSES_RECEIVED: "primary",
  COVERED: "accent",
  COORDINATING: "primary",
  FULFILLMENT_PENDING: "warning",
  FULFILLMENT_CONFIRMED: "success",
  FULFILLED: "success",
  BACKUP_REQUIRED: "danger",
  EXPIRED: "neutral",
  // DonorResponse / standby
  ACCEPTED: "primary",
  SELECTED: "success",
  STANDBY: "warning",
  WITHDRAWN: "neutral",
  DECLINED: "neutral",
  RELEASED: "neutral",
  ACTIVATED: "accent",
  // Organization response + verification
  AVAILABLE: "success",
  PARTIAL: "warning",
  UNAVAILABLE: "danger",
  PENDING: "warning",
  VERIFIED: "success",
  SUSPENDED: "danger",
  // Communication
  CLOSED: "neutral",
  ARCHIVED: "neutral",
  // Urgency
  ROUTINE: "neutral",
  URGENT: "warning",
  EMERGENCY: "danger"
};
function statusTone(status) {
  if (!status) return "neutral";
  return STATUS_TONES[status.toUpperCase()] ?? "neutral";
}
function urgencyTone(urgency) {
  return statusTone(urgency);
}
function humanise(value) {
  if (!value) return "";
  return value.toLowerCase().split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}
export {
  humanise,
  statusTone,
  urgencyTone
};
