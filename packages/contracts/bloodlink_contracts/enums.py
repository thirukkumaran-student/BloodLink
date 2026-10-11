"""Canonical enums for BloodLink (owner: D1).

Every enum value is a *wire value*: it appears in API payloads, database rows and
UI badges. Never rename a value without a contract change (spec §24).

All enums inherit ``str`` so they serialise to JSON as plain strings.
"""

from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    """str-backed enum with a stable ``value`` wire format."""

    def __str__(self) -> str:  # pragma: no cover - convenience
        return str(self.value)

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]

    @classmethod
    def coerce(cls, raw: object):
        """Return the enum member for ``raw`` (value or name), else ``None``."""
        if raw is None:
            return None
        if isinstance(raw, cls):
            return raw
        text = str(raw).strip()
        for member in cls:
            if text == member.value or text.upper() == member.name:
                return member
        return None


# --------------------------------------------------------------------------- #
# Identity & authorization (D1)
# --------------------------------------------------------------------------- #
class Role(_StrEnum):
    INDIVIDUAL = "INDIVIDUAL"
    HOSPITAL = "HOSPITAL"
    BLOOD_CENTRE = "BLOOD_CENTRE"
    ADMIN = "ADMIN"


class OrgType(_StrEnum):
    HOSPITAL = "HOSPITAL"
    BLOOD_CENTRE = "BLOOD_CENTRE"


class OrgVerificationStatus(_StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    SUSPENDED = "SUSPENDED"


ROLE_TO_ORG_TYPE = {
    Role.HOSPITAL: OrgType.HOSPITAL,
    Role.BLOOD_CENTRE: OrgType.BLOOD_CENTRE,
}


# --------------------------------------------------------------------------- #
# Clinical vocabulary (shared vocabulary only — no medical logic, spec §2)
# --------------------------------------------------------------------------- #
class BloodGroup(_StrEnum):
    A_POSITIVE = "A+"
    A_NEGATIVE = "A-"
    B_POSITIVE = "B+"
    B_NEGATIVE = "B-"
    AB_POSITIVE = "AB+"
    AB_NEGATIVE = "AB-"
    O_POSITIVE = "O+"
    O_NEGATIVE = "O-"


class BloodComponent(_StrEnum):
    WHOLE_BLOOD = "WHOLE_BLOOD"
    PRBC = "PRBC"  # packed red blood cells
    PLASMA = "PLASMA"
    PLATELETS = "PLATELETS"
    CRYOPRECIPITATE = "CRYOPRECIPITATE"


COMPONENT_LABELS = {
    BloodComponent.WHOLE_BLOOD: "Whole blood",
    BloodComponent.PRBC: "Packed red cells (PRBC)",
    BloodComponent.PLASMA: "Plasma",
    BloodComponent.PLATELETS: "Platelets",
    BloodComponent.CRYOPRECIPITATE: "Cryoprecipitate",
}

# Units are inventory units. BloodLink coordinates; it never stores or issues
# blood (spec §2).
UNITS_MIN = 1
UNITS_MAX = 10


class Urgency(_StrEnum):
    ROUTINE = "ROUTINE"
    URGENT = "URGENT"
    EMERGENCY = "EMERGENCY"


URGENCY_LABELS = {
    Urgency.ROUTINE: "Routine",
    Urgency.URGENT: "Urgent",
    Urgency.EMERGENCY: "Emergency",
}


# --------------------------------------------------------------------------- #
# PatientNeed (D2)
# --------------------------------------------------------------------------- #
class PatientNeedStatus(_StrEnum):
    PENDING_HOSPITAL_REVIEW = "PENDING_HOSPITAL_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CONVERTED = "CONVERTED"  # a BloodRequest now carries the need
    CANCELLED = "CANCELLED"


NEED_STATUS_PENDING_REVIEW = PatientNeedStatus.PENDING_HOSPITAL_REVIEW


# --------------------------------------------------------------------------- #
# BloodRequest lifecycle (D3)
# --------------------------------------------------------------------------- #
class BloodRequestStatus(_StrEnum):
    OPEN = "OPEN"
    RESPONSES_RECEIVED = "RESPONSES_RECEIVED"
    COVERED = "COVERED"
    COORDINATING = "COORDINATING"
    FULFILLMENT_PENDING = "FULFILLMENT_PENDING"
    FULFILLMENT_CONFIRMED = "FULFILLMENT_CONFIRMED"
    FULFILLED = "FULFILLED"
    BACKUP_REQUIRED = "BACKUP_REQUIRED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


#: Allowed transitions (spec §9). Any transition outside this map is a 409.
BLOOD_REQUEST_TRANSITIONS: dict[BloodRequestStatus, set[BloodRequestStatus]] = {
    BloodRequestStatus.OPEN: {
        BloodRequestStatus.RESPONSES_RECEIVED,
        BloodRequestStatus.COVERED,
        BloodRequestStatus.CANCELLED,
        BloodRequestStatus.EXPIRED,
    },
    BloodRequestStatus.RESPONSES_RECEIVED: {
        BloodRequestStatus.COVERED,
        BloodRequestStatus.BACKUP_REQUIRED,
        BloodRequestStatus.CANCELLED,
        BloodRequestStatus.EXPIRED,
    },
    BloodRequestStatus.COVERED: {
        BloodRequestStatus.COORDINATING,
        BloodRequestStatus.BACKUP_REQUIRED,
        BloodRequestStatus.CANCELLED,
    },
    BloodRequestStatus.COORDINATING: {
        BloodRequestStatus.FULFILLMENT_PENDING,
        BloodRequestStatus.BACKUP_REQUIRED,
        BloodRequestStatus.CANCELLED,
    },
    # Failure / backup path: standby, expanded outreach or reopened coordination.
    BloodRequestStatus.BACKUP_REQUIRED: {
        BloodRequestStatus.RESPONSES_RECEIVED,
        BloodRequestStatus.COVERED,
        BloodRequestStatus.COORDINATING,
        BloodRequestStatus.CANCELLED,
    },
    BloodRequestStatus.FULFILLMENT_PENDING: {
        BloodRequestStatus.FULFILLMENT_CONFIRMED,
        BloodRequestStatus.COORDINATING,
        BloodRequestStatus.BACKUP_REQUIRED,
    },
    BloodRequestStatus.FULFILLMENT_CONFIRMED: {BloodRequestStatus.FULFILLED},
    BloodRequestStatus.FULFILLED: set(),
    BloodRequestStatus.CANCELLED: set(),
    BloodRequestStatus.EXPIRED: set(),
}

TERMINAL_REQUEST_STATUSES = {
    BloodRequestStatus.FULFILLED,
    BloodRequestStatus.CANCELLED,
    BloodRequestStatus.EXPIRED,
}

#: Requests in these states still accept fresh donor responses.
OUTREACH_ACTIVE_STATUSES = {
    BloodRequestStatus.OPEN,
    BloodRequestStatus.RESPONSES_RECEIVED,
    BloodRequestStatus.BACKUP_REQUIRED,
    BloodRequestStatus.COORDINATING,
}


# --------------------------------------------------------------------------- #
# Responses (D4)
# --------------------------------------------------------------------------- #
class DonorResponseStatus(_StrEnum):
    ACCEPTED = "ACCEPTED"  # donor confirmed they will donate
    SELECTED = "SELECTED"  # hospital chose this donor
    STANDBY = "STANDBY"  # suitable, not chosen, kept on hold
    WITHDRAWN = "WITHDRAWN"  # donor pulled out
    DECLINED = "DECLINED"  # donor explicitly declined after accepting
    RELEASED = "RELEASED"  # hospital released the donor


class DonorStandbyStatus(_StrEnum):
    NONE = "NONE"
    STANDBY = "STANDBY"
    ACTIVATED = "ACTIVATED"


class OrganizationResponseStatus(_StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class OrganizationResponseOutcome(_StrEnum):
    PENDING = "PENDING"
    ACCEPTED_BY_HOSPITAL = "ACCEPTED_BY_HOSPITAL"
    DECLINED_BY_HOSPITAL = "DECLINED_BY_HOSPITAL"
    FULFILLED = "FULFILLED"


# --------------------------------------------------------------------------- #
# Coordination (D4)
# --------------------------------------------------------------------------- #
class ConversationStatus(_StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


class ConversationParticipantRole(_StrEnum):
    HOSPITAL = "HOSPITAL"
    DONOR = "DONOR"
    BLOOD_CENTRE = "BLOOD_CENTRE"


MESSAGE_MAX_LENGTH = 2000


# --------------------------------------------------------------------------- #
# Notifications (D4)
# --------------------------------------------------------------------------- #
class Platform(_StrEnum):
    WEB = "WEB"
    MOBILE = "MOBILE"


class NotificationType(_StrEnum):
    NEED_SUBMITTED = "NEED_SUBMITTED"  # -> hospital
    #: Contract extension (D1): the submitter must learn the review outcome, and
    #: none of the original types described that event (spec §8 review gate).
    NEED_REVIEWED = "NEED_REVIEWED"  # -> submitter
    REQUEST_OPENED = "REQUEST_OPENED"  # -> donors (tiered outreach)
    REQUEST_OUTREACH_EXPANDED = "REQUEST_OUTREACH_EXPANDED"  # -> donors (tier 2/3)
    DONOR_ACCEPTED = "DONOR_ACCEPTED"  # -> hospital
    DONOR_SELECTED = "DONOR_SELECTED"  # -> donor
    DONOR_STANDBY = "DONOR_STANDBY"  # -> donor
    ORGANIZATION_RESPONDED = "ORGANIZATION_RESPONDED"  # -> hospital
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"  # -> counterpart
    FULFILLMENT_PENDING = "FULFILLMENT_PENDING"  # -> donor / blood centre
    FULFILLMENT_CONFIRMED = "FULFILLMENT_CONFIRMED"  # -> hospital
    REQUEST_FULFILLED = "REQUEST_FULFILLED"  # -> hospital + donor
    REQUEST_BACKUP_REQUIRED = "REQUEST_BACKUP_REQUIRED"  # -> hospital staff
    SUBSCRIPTION_ALERT = "SUBSCRIPTION_ALERT"  # -> subscribed donor
    ACCOUNT = "ACCOUNT"


#: Keys that must never appear in a push payload (spec §12, §21).
PUSH_PAYLOAD_FORBIDDEN_KEYS = frozenset(
    {
        "patient",
        "patientname",
        "patientid",
        "diagnosis",
        "indication",
        "notes",
        "additionalnotes",
        "address",
        "homeaddress",
        "latitude",
        "longitude",
        "lat",
        "lng",
        "coordinates",
        "phone",
        "email",
        "medicalrecord",
    }
)
