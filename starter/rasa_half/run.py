"""Ex6 — runner (reference solution).

Three execution tiers:

  python -m starter.rasa_half.run          (mock, no services) → tier 1
  python -m starter.rasa_half.run --real   (assume Rasa is up)  → tier 2
  python -m starter.rasa_half.run --real --auto  (auto-spawn)    → tier 3

Tier 1 uses a stdlib mock that matches Rasa's HTTP shape. Students can
validate their normalise_booking_payload + structured_half code without
installing Rasa Pro or obtaining a license.

Tier 2 assumes Rasa is already running on localhost:5005 (rasa serve)
and localhost:5055 (actions). Students start these themselves in two
other terminals — this teaches the multi-process coordination pattern
that real agent systems use in production.

Tier 3 auto-spawns both Rasa processes via RasaHostLifecycle, runs the
scenario, and tears them down. Convenient for CI / demos but hides
what tier 2 teaches.

Two policy profiles selectable via --profile:
  default  — original Ex6 scenario (party 6, no vegan field). Caps at 8/£300.
  slide    — the Nebius Academy slides scenario (160 people, vegan options,
             deposit ≤ £300). Caps at 170/£300/0.80 vegan_ratio.

Default behaviour (no flag) is unchanged from the original Ex6.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sovereign_agent._internal.paths import example_sessions_dir
from sovereign_agent.session.directory import create_session

from starter.rasa_half.structured_half import (
    RasaHostLifecycle,
    RasaStructuredHalf,
    spawn_mock_rasa,
)

_DEFAULT_SAMPLE = {
    "data": {
        "action": "confirm_booking",
        "venue_id": "Haymarket Tap",
        "date": "25th April 2026",
        "time": "7:30pm",
        "party_size": "6",
        "deposit": "£200",
        # policy_profile omitted — validator falls back to "default".
    }
}

# Slide-spec scenario: 160 people, vegan options (we set ratio under cap so
# the booking succeeds), deposit £300 (exactly at cap), 5 PM. The booking
# only validates if `slide` profile is active — under `default` (cap 8) it
# would be rejected as party_too_large.
_SLIDE_SAMPLE = {
    "data": {
        "action": "confirm_booking",
        "venue_id": "Haymarket Tap",
        "date": "2026-05-19",
        "time": "5pm",
        "party_size": "160",
        "deposit": "£300",
        "vegan_ratio": 0.5,
        "policy_profile": "slide",
    }
}


async def run_scenario(real: bool, auto: bool, profile: str) -> int:
    with example_sessions_dir("ex6-rasa-half", persist=real) as sessions_root:
        session = create_session(
            scenario="ex6-rasa",
            task="Confirm a booking through the Rasa structured half.",
            sessions_dir=sessions_root,
        )
        print(f"📂 Session {session.session_id}")
        print(f"   dir: {session.directory}")
        print(f"   profile: {profile}")

        sample_booking = _SLIDE_SAMPLE if profile == "slide" else _DEFAULT_SAMPLE

        if real and auto:
            # Tier 3 — auto-spawn.
            log_dir = session.logs_dir / "rasa"
            log_dir.mkdir(parents=True, exist_ok=True)
            print(f"   Rasa logs: {log_dir}")
            print(
                "   (tier 3 auto-spawn mode — the scenario spawns Rasa + action\n"
                "    server subprocesses, runs, then tears them down)"
            )
            async with RasaHostLifecycle(log_dir=log_dir) as rasa_url:
                print(f"   Rasa URL: {rasa_url}")
                half = RasaStructuredHalf(rasa_url=rasa_url, request_timeout_s=30.0)
                result = await half.run(session, sample_booking)

        elif real:
            # Tier 2 — assume Rasa is already running.
            print(
                "   (tier 2: assuming rasa-actions + rasa-serve are already\n"
                "    running in two other terminals. If you see a connection\n"
                "    error below, run `make ex6-help` for the setup recipe.)"
            )
            rasa_url = "http://localhost:5005/webhooks/rest/webhook"
            print(f"   Rasa URL: {rasa_url}")
            half = RasaStructuredHalf(rasa_url=rasa_url, request_timeout_s=30.0)
            result = await half.run(session, sample_booking)

        else:
            # Tier 1 — mock.
            print("   (tier 1: stdlib mock Rasa on :5905 — no license needed)")
            server, _thread, mock_url = spawn_mock_rasa(port=5905)
            try:
                print(f"   Mock URL: {mock_url}")
                half = RasaStructuredHalf(rasa_url=mock_url)
                result = await half.run(session, sample_booking)
            finally:
                server.shutdown()

        print(f"\nStructured half outcome: {result.next_action}")
        print(f"  summary: {result.summary}")
        print(f"  output:  {result.output}")

        if real:
            print(f"\n📂 Session artifacts: {session.directory}")
            print(f"📜 Narrate this run:   make narrate SESSION={session.session_id}")

        return 0 if result.success else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--real",
        action="store_true",
        help="Hit a live Rasa server (tier 2/3 instead of the stdlib mock).",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-spawn rasa + action-server via RasaHostLifecycle (tier 3). Requires --real.",
    )
    parser.add_argument(
        "--profile",
        choices=("default", "slide"),
        default="default",
        help="Validator policy profile to exercise. 'default' = party≤8/£300; "
        "'slide' = party≤170/£300/vegan_ratio≤0.80.",
    )
    args = parser.parse_args()
    if args.auto and not args.real:
        print("✗ --auto requires --real", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(run_scenario(real=args.real, auto=args.auto, profile=args.profile)))


if __name__ == "__main__":
    main()
