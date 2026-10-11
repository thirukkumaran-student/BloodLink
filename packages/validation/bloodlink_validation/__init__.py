"""bloodlink_validation — shared validation foundation (owner: D1, spec §5).

Pure functions with no framework imports. Both the API (Pydantic DTOs) and the
web client (form handling) call these, so a rule is never enforced twice in two
different ways (spec §3: "business rules live in the backend").

Nothing here performs medical eligibility determination (spec §2). The blood
group compatibility matrix is a coordination aid for outreach targeting only,
and every response surface states that clinical screening stays with the
hospital / blood centre.
"""

from bloodlink_validation.blood import (  # noqa: F401
    BLOOD_GROUP_CODES,
    COMPATIBLE_DONORS_FOR,
    COMPATIBLE_RECIPIENTS_FOR,
    cooldown_remaining_days,
    is_compatible,
)
from bloodlink_validation.common import (  # noqa: F401
    ValidationIssue,
    assert_privacy_safe_payload,
    hash_phone,
    normalise_blood_group,
    normalise_component,
    normalise_urgency,
    password_issues,
    validate_coordinates,
    validate_message_content,
    validate_person_name,
    validate_phone,
    validate_required_by,
    validate_units,
)
