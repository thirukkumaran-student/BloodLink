import { can } from "../lib/capabilities";
function navForUser(user) {
  if (!user) return [];
  const groups = [];
  const personal = [];
  if (can(user, "patient_need.submit")) personal.push({ to: "/needs", label: "My blood requests", icon: "\u{1FA78}" });
  if (can(user, "donor.view_matched_requests")) personal.push({ to: "/donor", label: "Donor dashboard", icon: "\u{1F91D}" });
  if (can(user, "donor.view_history")) personal.push({ to: "/donor/commitments", label: "My commitments", icon: "\u{1F4CC}" });
  if (can(user, "donor.subscribe_hospital")) personal.push({ to: "/donor/hospitals", label: "Hospital alerts", icon: "\u{1F514}" });
  if (can(user, "donor.profile_manage")) personal.push({ to: "/donor/profile", label: "Donor profile", icon: "\u2699\uFE0F" });
  if (can(user, "communication.donor_side") || can(user, "communication.organization_side"))
    personal.push({ to: "/messages", label: "Coordination threads", icon: "\u{1F4AC}" });
  if (personal.length) groups.push({ label: "For you", links: personal });
  const organization = [];
  if (can(user, "patient_need.review")) organization.push({ to: "/hospital/queue", label: "Review queue", icon: "\u{1F4E5}" });
  if (can(user, "blood_request.create") || can(user, "blood_request.view_organization"))
    organization.push({ to: "/hospital/requests", label: "Request board", icon: "\u{1F4CB}" });
  if (can(user, "request.view_nearby") || can(user, "response.organization_submit"))
    organization.push({ to: "/blood-centre", label: "Nearby requests", icon: "\u{1F3E5}" });
  if (organization.length) groups.push({ label: "Organization", links: organization });
  const administration = [];
  if (can(user, "admin.organizations")) administration.push({ to: "/admin/organizations", label: "Organizations", icon: "\u{1F3E8}" });
  if (can(user, "admin.users")) administration.push({ to: "/admin/users", label: "Accounts", icon: "\u{1F465}" });
  if (can(user, "admin.audit")) administration.push({ to: "/admin/audit", label: "Audit trail", icon: "\u{1F9FE}" });
  if (administration.length) groups.push({ label: "Administration", links: administration });
  groups.push({
    label: "Platform",
    links: [
      { to: "/platform", label: "Modules & ownership", icon: "\u{1F9E9}" },
      { to: "/account", label: "My account", icon: "\u{1F64B}" }
    ]
  });
  return groups;
}
export {
  navForUser
};
