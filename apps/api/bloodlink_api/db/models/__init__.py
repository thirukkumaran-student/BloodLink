"""Canonical model registry (owner: D1, spec §7, §23).

Importing this package registers every table on the shared metadata object used
by Alembic and ``create_all``. Feature developers add their models to the
matching module file and re-export them here.
"""

from bloodlink_api.db.base import Base  # noqa: F401
from bloodlink_api.db.models.coordination import (  # noqa: F401
    Conversation,
    Message,
    PushSubscription,
)
from bloodlink_api.db.models.donors import (  # noqa: F401
    DonationRecord,
    DonorProfile,
    DonorResponse,
    HospitalSubscription,
    Notification,
    NotificationDelivery,
    OrganizationResponse,
)
from bloodlink_api.db.models.identity import (  # noqa: F401
    AuditLog,
    IdempotencyRecord,
    Organization,
    OrganizationMembership,
    RefreshToken,
    User,
    VerificationDocument,
)
from bloodlink_api.db.models.needs import PatientNeed  # noqa: F401
from bloodlink_api.db.models.blood_requests import (  # noqa: F401
    BloodRequest,
    BloodRequestEvent,
    DonorOutreach,
)

__all__ = [
    "AuditLog",
    "BloodRequest",
    "BloodRequestEvent",
    "Conversation",
    "DonationRecord",
    "DonorOutreach",
    "DonorProfile",
    "DonorResponse",
    "HospitalSubscription",
    "IdempotencyRecord",
    "Message",
    "Notification",
    "NotificationDelivery",
    "Organization",
    "OrganizationMembership",
    "OrganizationResponse",
    "PatientNeed",
    "PushSubscription",
    "RefreshToken",
    "User",
    "VerificationDocument",
]
