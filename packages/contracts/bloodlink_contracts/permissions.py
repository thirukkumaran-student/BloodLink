"""Capability matrix (owner: D1, spec §16).

Capabilities are the contract between the API's authorization rules and the web
client's role-aware navigation. The web app uses them to decide what to *show*;
the API independently enforces the same rule server-side (spec §16: frontend
route protection is UX, not the security boundary).
"""

from __future__ import annotations

from bloodlink_contracts.enums import Role

# --- capability vocabulary -------------------------------------------------- #
NEED_SUBMIT = "patient_need.submit"
NEED_VIEW_OWN = "patient_need.view_own"
NEED_REVIEW = "patient_need.review"
NEED_CANCEL_OWN = "patient_need.cancel_own"

REQUEST_CREATE = "blood_request.create"
REQUEST_VIEW_ORG = "blood_request.view_organization"
REQUEST_MANAGE = "blood_request.manage"
REQUEST_RESPOND = "blood_request.respond"
REQUEST_VIEW_NEARBY = "blood_request.view_nearby"

RESPONSE_VIEW_FOR_REQUEST = "response.view_for_request"
RESPONSE_SELECT = "response.select_donor"
RESPONSE_ORGANIZATION_SUBMIT = "response.organization_submit"
RESPONSE_ORGANIZATION_DECIDE = "response.organization_decide"

DONOR_PROFILE_MANAGE = "donor.profile_manage"
DONOR_VIEW_MATCHES = "donor.view_matched_requests"
DONOR_HISTORY = "donor.view_history"
DONOR_SUBSCRIBE_HOSPITAL = "donor.subscribe_hospital"

COMMUNICATION_DONOR = "communication.donor_side"
COMMUNICATION_ORGANIZATION = "communication.organization_side"

NOTIFICATION_MANAGE = "notification.manage_own"

ADMIN_ORGANIZATIONS = "admin.organizations"
ADMIN_USERS = "admin.users"
ADMIN_AUDIT = "admin.audit"
ADMIN_REQUESTS = "admin.requests"

_HOSPITAL_CAPABILITIES = frozenset(
    {
        NEED_SUBMIT,  # staff may raise a need on a patient's behalf
        NEED_VIEW_OWN,
        NEED_REVIEW,
        REQUEST_CREATE,
        REQUEST_VIEW_ORG,
        REQUEST_MANAGE,
        RESPONSE_VIEW_FOR_REQUEST,
        RESPONSE_SELECT,
        RESPONSE_ORGANIZATION_DECIDE,
        COMMUNICATION_ORGANIZATION,
        NOTIFICATION_MANAGE,
        DONOR_PROFILE_MANAGE,  # hospital staff may also be donors
        DONOR_VIEW_MATCHES,
        DONOR_HISTORY,
        DONOR_SUBSCRIBE_HOSPITAL,
    }
)

_BLOOD_CENTRE_CAPABILITIES = frozenset(
    {
        REQUEST_VIEW_NEARBY,
        RESPONSE_ORGANIZATION_SUBMIT,
        COMMUNICATION_ORGANIZATION,
        NOTIFICATION_MANAGE,
        DONOR_PROFILE_MANAGE,
        DONOR_VIEW_MATCHES,
        DONOR_HISTORY,
    }
)

_INDIVIDUAL_CAPABILITIES = frozenset(
    {
        NEED_SUBMIT,
        NEED_VIEW_OWN,
        NEED_CANCEL_OWN,
        DONOR_PROFILE_MANAGE,
        DONOR_VIEW_MATCHES,
        DONOR_HISTORY,
        DONOR_SUBSCRIBE_HOSPITAL,
        REQUEST_RESPOND,
        COMMUNICATION_DONOR,
        NOTIFICATION_MANAGE,
    }
)

_ADMIN_CAPABILITIES = frozenset(
    {
        ADMIN_ORGANIZATIONS,
        ADMIN_USERS,
        ADMIN_AUDIT,
        ADMIN_REQUESTS,
        NEED_REVIEW,
        REQUEST_VIEW_ORG,
        NOTIFICATION_MANAGE,
    }
)

CAPABILITIES_BY_ROLE: dict[Role, frozenset[str]] = {
    Role.INDIVIDUAL: _INDIVIDUAL_CAPABILITIES,
    Role.HOSPITAL: _HOSPITAL_CAPABILITIES,
    Role.BLOOD_CENTRE: _BLOOD_CENTRE_CAPABILITIES,
    Role.ADMIN: _ADMIN_CAPABILITIES,
}

#: Human-readable labels used by generated RBAC documentation.
CAPABILITY_LABELS: dict[str, str] = {
    NEED_SUBMIT: "Submit a PatientNeed",
    NEED_VIEW_OWN: "View own submissions",
    NEED_REVIEW: "Review PatientNeeds for the organization",
    NEED_CANCEL_OWN: "Cancel an own pending need",
    REQUEST_CREATE: "Create a BloodRequest from an approved need",
    REQUEST_VIEW_ORG: "View organizational requests",
    REQUEST_MANAGE: "Drive the request lifecycle",
    REQUEST_RESPOND: "Accept a matched request as a donor",
    REQUEST_VIEW_NEARBY: "See nearby open requests",
    RESPONSE_VIEW_FOR_REQUEST: "Review donor responses",
    RESPONSE_SELECT: "Select / place donors on standby",
    RESPONSE_ORGANIZATION_SUBMIT: "Respond to a request as an organization",
    RESPONSE_ORGANIZATION_DECIDE: "Accept or decline organization responses",
    DONOR_PROFILE_MANAGE: "Manage a donor profile",
    DONOR_VIEW_MATCHES: "See matched requests as a donor",
    DONOR_HISTORY: "View donation history",
    DONOR_SUBSCRIBE_HOSPITAL: "Subscribe to hospital alerts",
    COMMUNICATION_DONOR: "Use request-scoped coordination threads (donor side)",
    COMMUNICATION_ORGANIZATION: "Use request-scoped coordination threads (organization side)",
    NOTIFICATION_MANAGE: "Manage notification subscriptions",
    ADMIN_ORGANIZATIONS: "Verify / suspend organizations",
    ADMIN_USERS: "Administer users",
    ADMIN_AUDIT: "Read the audit trail",
    ADMIN_REQUESTS: "Monitor all requests",
}


def capabilities_for(role: Role) -> list[str]:
    return sorted(CAPABILITIES_BY_ROLE.get(role, frozenset()))


def has_capability(role: Role, capability: str) -> bool:
    return capability in CAPABILITIES_BY_ROLE.get(role, frozenset())
