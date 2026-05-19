"""Rasa custom actions — reference implementation.

ActionValidateBooking reads booking data from the UserUttered message's
`metadata.booking` dict (which is how RasaStructuredHalf POSTs data) and
validates it against the homework's business rules.

Two policy profiles are supported per booking, selected via the
`policy_profile` field in the booking metadata:

  * "default" — party ≤ 8, deposit ≤ £300, no vegan check (original
                Ex5/Ex6 homework scenario).
  * "slide"   — party ≤ 170, deposit ≤ £300, vegan_ratio ≤ 0.80 (the
                alt scenario from the Nebius Academy slides).

When `policy_profile` is absent the validator falls back to "default",
so callers that haven't been updated keep their previous behaviour.

On every outcome (success OR escalation) the action also writes a
markdown artefact under `<session_dir>/memory/semantic/booking_*.md`.
The session directory is read from `metadata.session_dir`, which
RasaStructuredHalf populates before each POST. If absent, the memory
write is skipped silently (the action still returns slot events).

Why metadata, not slots?
  Our caller POSTs this payload to Rasa's REST webhook:
    {"sender": ..., "message": "/confirm_booking",
     "metadata": {"booking": {"venue_id": ..., "party_size": 6, ...},
                  "session_dir": "/path/to/sess_..."}}

  CALM's LLM command generator turns "/confirm_booking" into a
  StartFlow(confirm_booking) command. But it does NOT read metadata
  into slots — that's our job. This action does it explicitly.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher

# rasa_project/actions/actions.py — repo root is two parents up. Add it
# to sys.path so we can import the starter package regardless of where
# `rasa run actions` was invoked from.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from starter.rasa_half.memory import write_booking_memory  # noqa: E402
from starter.rasa_half.policies import lookup  # noqa: E402


def _read_booking(tracker: Tracker) -> dict[str, Any]:
    """Extract booking dict from metadata (primary) or slots (fallback)."""
    latest = tracker.latest_message or {}
    meta = latest.get("metadata") or {}
    from_meta = meta.get("booking") if isinstance(meta, dict) else None
    if isinstance(from_meta, dict):
        return from_meta

    # Fallback — assemble from slots if the caller populated them directly
    return {
        "venue_id": tracker.get_slot("venue_id"),
        "date": tracker.get_slot("date"),
        "time": tracker.get_slot("time"),
        "party_size": tracker.get_slot("party_size"),
        "deposit_gbp": tracker.get_slot("deposit_gbp"),
    }


def _read_session_dir(tracker: Tracker) -> Path | None:
    """Pull `metadata.session_dir` if RasaStructuredHalf set it; else None."""
    latest = tracker.latest_message or {}
    meta = latest.get("metadata") or {}
    if not isinstance(meta, dict):
        return None
    raw = meta.get("session_dir")
    if not raw:
        return None
    p = Path(str(raw))
    if not p.exists():
        # The caller advertised a path that doesn't exist — log and skip
        # rather than crash. The validator's job isn't to mount filesystems.
        print(f"[actions] session_dir does not exist: {p}", file=sys.stderr)
        return None
    return p


class ActionValidateBooking(Action):
    """Validate the proposed booking against the active policy profile.

    Rules (resolved via policies.lookup at runtime):
      * party_size > policy.max_party_size       → reject ("party_too_large")
      * deposit_gbp > policy.max_deposit_gbp     → reject ("deposit_too_high")
      * vegan_ratio > policy.max_vegan_ratio     → reject ("vegan_ratio_too_high")
        (only when both the policy enforces a cap AND the booking declares one)
      * missing required field                   → reject ("missing_<field>")
      * otherwise                                → success, set booking_reference

    Side-effect: writes booking_*.md to <session_dir>/memory/semantic/
    on every outcome.
    """

    def name(self) -> str:
        return "action_validate_booking"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict[str, Any],
    ) -> list[dict[str, Any]]:
        booking = _read_booking(tracker)
        session_dir = _read_session_dir(tracker)

        profile_name = str(booking.get("policy_profile") or "default")
        policy = lookup(profile_name)

        venue_id = booking.get("venue_id")
        date = booking.get("date")
        time_slot = booking.get("time")
        party_size = booking.get("party_size")
        deposit_gbp = booking.get("deposit_gbp", 0)
        vegan_ratio = booking.get("vegan_ratio")

        # All the slot-sets we'll emit — start with populating from metadata
        # so downstream responses can reference {venue_id}, {party_size}, etc.
        # Cast to the types domain.yml declares so Rasa doesn't reject.
        def _to_float(v: Any) -> float | None:
            if v is None or v == "":
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        slot_events: list[dict[str, Any]] = [
            SlotSet("venue_id", str(venue_id) if venue_id is not None else None),
            SlotSet("date", str(date) if date is not None else None),
            SlotSet("time", str(time_slot) if time_slot is not None else None),
            SlotSet("party_size", _to_float(party_size)),
            SlotSet("deposit_gbp", _to_float(deposit_gbp)),
            SlotSet("vegan_ratio", _to_float(vegan_ratio)),
            SlotSet("policy_profile", profile_name),
        ]

        def _reject(code: str) -> list[dict[str, Any]]:
            write_booking_memory(
                session_dir,
                outcome="rejected",
                booking=booking,
                policy=policy,
                profile_name=profile_name,
                reference=None,
                reason=code,
            )
            return slot_events + [SlotSet("validation_error", code)]

        # Required-field check
        for field_name, value in [
            ("venue_id", venue_id),
            ("date", date),
            ("time", time_slot),
            ("party_size", party_size),
        ]:
            if value is None or value == "":
                return _reject(f"missing_{field_name}")

        # Cast numeric fields (they may arrive as strings from handoff JSON)
        try:
            party_int = int(float(party_size))
        except (TypeError, ValueError):
            return _reject("invalid_party_size")

        try:
            deposit_int = int(float(deposit_gbp)) if deposit_gbp is not None else 0
        except (TypeError, ValueError):
            return _reject("invalid_deposit")

        # Rule checks against the active policy
        if party_int > policy.max_party_size:
            return _reject("party_too_large")

        if deposit_int > policy.max_deposit_gbp:
            return _reject("deposit_too_high")

        # vegan_ratio is only enforced when the profile asks for it AND the
        # booking declared a value. Missing data on a slide-profile booking
        # falls through silently — we don't fail bookings for absent fields.
        if policy.max_vegan_ratio is not None and vegan_ratio is not None:
            try:
                vegan_f = float(vegan_ratio)
            except (TypeError, ValueError):
                return _reject("invalid_vegan_ratio")
            if vegan_f > policy.max_vegan_ratio:
                return _reject("vegan_ratio_too_high")

        # Success — generate a deterministic booking reference
        ref = (
            "BK-"
            + hashlib.sha1(f"{venue_id}|{date}|{time_slot}|{party_int}".encode())
            .hexdigest()[:8]
            .upper()
        )

        write_booking_memory(
            session_dir,
            outcome="confirmed",
            booking=booking,
            policy=policy,
            profile_name=profile_name,
            reference=ref,
            reason=None,
        )

        return slot_events + [
            SlotSet("validation_error", None),
            SlotSet("booking_reference", ref),
        ]
