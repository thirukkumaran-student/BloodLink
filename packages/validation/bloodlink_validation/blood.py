"""Blood-group coordination helpers (owner: D1 contract, D4 consumes).

The matrix below is the standard red-cell compatibility grouping. BloodLink uses
it **only** to decide which donors a request may be surfaced to, and to rank
candidates. It is not a medical eligibility decision: crossmatching, screening
and issue remain with the hospital / blood centre (spec §2, §11).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from bloodlink_contracts.enums import BloodComponent, BloodGroup

BLOOD_GROUP_CODES: list[BloodGroup] = list(BloodGroup)

#: recipient -> every donor group whose red cells are conventionally compatible
COMPATIBLE_DONORS_FOR: dict[BloodGroup, frozenset[BloodGroup]] = {
    BloodGroup.O_NEGATIVE: frozenset({BloodGroup.O_NEGATIVE}),
    BloodGroup.O_POSITIVE: frozenset({BloodGroup.O_NEGATIVE, BloodGroup.O_POSITIVE}),
    BloodGroup.A_NEGATIVE: frozenset({BloodGroup.O_NEGATIVE, BloodGroup.A_NEGATIVE}),
    BloodGroup.A_POSITIVE: frozenset(
        {BloodGroup.O_NEGATIVE, BloodGroup.O_POSITIVE, BloodGroup.A_NEGATIVE, BloodGroup.A_POSITIVE}
    ),
    BloodGroup.B_NEGATIVE: frozenset({BloodGroup.O_NEGATIVE, BloodGroup.B_NEGATIVE}),
    BloodGroup.B_POSITIVE: frozenset(
        {BloodGroup.O_NEGATIVE, BloodGroup.O_POSITIVE, BloodGroup.B_NEGATIVE, BloodGroup.B_POSITIVE}
    ),
    BloodGroup.AB_NEGATIVE: frozenset(
        {BloodGroup.O_NEGATIVE, BloodGroup.A_NEGATIVE, BloodGroup.B_NEGATIVE, BloodGroup.AB_NEGATIVE}
    ),
    BloodGroup.AB_POSITIVE: frozenset(BloodGroup),
}

#: donor -> recipients that donor can serve (derived, for donor-facing copy)
COMPATIBLE_RECIPIENTS_FOR: dict[BloodGroup, frozenset[BloodGroup]] = {
    donor: frozenset(r for r, donors in COMPATIBLE_DONORS_FOR.items() if donor in donors)
    for donor in BloodGroup
}

#: Plasma swaps the rule (AB plasma is the universal plasma donation).
COMPATIBLE_PLASMA_DONORS_FOR: dict[BloodGroup, frozenset[BloodGroup]] = {
    recipient: frozenset(
        donor for donor in BloodGroup if recipient in COMPATIBLE_RECIPIENTS_FOR[donor] or donor == recipient
    )
    for recipient in BloodGroup
}

COMPATIBILITY_NOTE = (
    "Compatibility shown here only targets BloodLink outreach. Screening, "
    "crossmatching, collection and issue remain with the hospital / blood centre."
)


def is_compatible(
    recipient: BloodGroup,
    donor: BloodGroup,
    component: BloodComponent = BloodComponent.PRBC,
) -> bool:
    """True when ``donor`` may be surfaced to a request for ``recipient``."""
    if component is BloodComponent.PLASMA:
        return donor in COMPATIBLE_PLASMA_DONORS_FOR[recipient]
    return donor in COMPATIBLE_DONORS_FOR[recipient]


def cooldown_remaining_days(
    last_donation_at: datetime | None,
    cooldown_days: int,
    *,
    as_of: datetime,
) -> int:
    """Whole days remaining in a donor's post-donation cooldown (0 when clear)."""
    if last_donation_at is None:
        return 0
    clear_at = last_donation_at + timedelta(days=cooldown_days)
    if clear_at <= as_of:
        return 0
    return max(1, (clear_at - as_of).days + 1)
