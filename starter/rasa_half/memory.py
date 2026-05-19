"""Ex6 — booking memory writer.

Shared helper for persisting a markdown artefact of each booking
validator outcome. Used by both the real Rasa action
(`rasa_project/actions/actions.py`) and the in-process stdlib mock
(`_MockRasaHandler` in `structured_half.py`), so the two paths produce
the same on-disk shape.

The slide spec asks for `memory/semantic/booking_*.md` to be written on
success AND on escalation. This module is the single place we describe
that file's contents and naming.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from starter.rasa_half.policies import Policy


def write_booking_memory(
    session_dir: Path | str | None,
    *,
    outcome: str,
    booking: dict[str, Any],
    policy: Policy,
    profile_name: str,
    reference: str | None,
    reason: str | None,
) -> Path | None:
    """Persist a markdown stub describing the validator's verdict.

    Returns the file path on write, or None if no session_dir is wired.
    Idempotent on repeated invocations for the same (venue, date, time)
    + outcome — uses a deterministic suffix so retries overwrite rather
    than fan out.
    """
    if session_dir is None:
        return None
    session_path = Path(session_dir) if isinstance(session_dir, str) else session_dir
    if not session_path.exists():
        return None

    target_dir = session_path / "memory" / "semantic"
    target_dir.mkdir(parents=True, exist_ok=True)

    if outcome == "confirmed" and reference:
        stem = f"booking_{reference}"
    else:
        suffix = (reason or "rejected").replace("/", "_")
        ident_basis = (
            f"{booking.get('venue_id', '')}|{booking.get('date', '')}|{booking.get('time', '')}"
        )
        ident = hashlib.sha1(ident_basis.encode()).hexdigest()[:8]
        stem = f"booking_{ident}_{suffix}"

    path = target_dir / f"{stem}.md"
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# Booking validator — {outcome}",
        "",
        f"- Timestamp (UTC): {now}",
        f"- Profile: `{profile_name}`",
        f"- Outcome: **{outcome}**",
    ]
    if reference:
        lines.append(f"- Reference: `{reference}`")
    if reason:
        lines.append(f"- Reason: `{reason}`")
    lines += [
        "",
        "## Policy applied",
        f"- max_party_size: {policy.max_party_size}",
        f"- max_deposit_gbp: {policy.max_deposit_gbp}",
        f"- max_vegan_ratio: {policy.max_vegan_ratio}",
        "",
        "## Booking payload",
        "```json",
        json.dumps(booking, indent=2, default=str),
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


__all__ = ["write_booking_memory"]
