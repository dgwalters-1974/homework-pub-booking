"""Ex6 — booking-policy lookup table.

Single source of truth for the rules the validator enforces. Both the
Rasa custom action (rasa_project/actions/actions.py) and the in-process
stdlib mock (_MockRasaHandler in structured_half.py) read from this
module so they can't drift.

Profiles:
  * "default" — the original homework scenario: party of 6 at Haymarket.
                Tight caps (8 / £300) so the validator rejects anything
                visibly out of scope. No vegan accounting.
  * "slide"   — the alt scenario from the recent Nebius Academy slides:
                160 people, vegan options, deposit ≤ £300, confirm-by-5pm.
                Caps loosened (170 / £300) and a new vegan_ratio guard
                (≤ 0.80) keeps the validator meaningful at scale.

The profile is selected per-booking via metadata.booking.policy_profile,
so the same Rasa server can validate both scenarios in one process. When
the field is absent we fall back to "default" — preserves Ex6 behaviour
for callers that haven't been updated.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Policy:
    """Rule bundle keyed by profile name."""

    max_party_size: int
    max_deposit_gbp: int
    # None = profile does not enforce a vegan-ratio cap (default scenario).
    max_vegan_ratio: float | None = None


POLICIES: dict[str, Policy] = {
    "default": Policy(max_party_size=8, max_deposit_gbp=300, max_vegan_ratio=None),
    "slide": Policy(max_party_size=170, max_deposit_gbp=300, max_vegan_ratio=0.80),
}


def lookup(profile_name: str | None) -> Policy:
    """Return the Policy for `profile_name`, falling back to 'default'.

    Unknown profile names fall back to default rather than raising — we
    don't want a stray typo in upstream metadata to crash the action
    server. Tests cover the two known names explicitly.
    """
    if profile_name and profile_name in POLICIES:
        return POLICIES[profile_name]
    return POLICIES["default"]


__all__ = ["POLICIES", "Policy", "lookup"]
