"""bloodlink_contracts — canonical cross-domain contracts (owner: D1).

This package is the single source of truth shared by *every* application in the
monorepo (API, web client, tests, seeders). Feature developers consume these
contracts; they do not fork them (spec §15, §24).

Exports
-------
enums     : roles, blood groups, components, urgency, every lifecycle status
errors    : machine-readable error codes + canonical HTTP mapping
envelope  : the single canonical success/error response convention (§14)
"""

from bloodlink_contracts.enums import (  # noqa: F401
    NEED_STATUS_PENDING_REVIEW,
    OrgType,
    OrgVerificationStatus,
    PatientNeedStatus,
    BloodComponent,
    BloodGroup,
    BloodRequestStatus,
    ConversationStatus,
    DonorResponseStatus,
    DonorStandbyStatus,
    NotificationType,
    OrganizationResponseStatus,
    Platform,
    Role,
    Urgency,
)
from bloodlink_contracts.dto import APIModel, ORMModel  # noqa: F401
from bloodlink_contracts.envelope import error_envelope, success_envelope  # noqa: F401
from bloodlink_contracts.permissions import (  # noqa: F401
    CAPABILITIES_BY_ROLE,
    CAPABILITY_LABELS,
    capabilities_for,
    has_capability,
)
from bloodlink_contracts.errors import ErrorCode, HTTP_STATUS_FOR  # noqa: F401

API_PREFIX = "/api/v1"
