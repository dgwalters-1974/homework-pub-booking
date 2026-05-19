"""Ex7 — reference solution runner.

Default profile (the original Ex7 scenario):
  round 1: loop picks haymarket_tap, structured rejects (party=12 > cap=8)
  round 2: loop picks royal_oak, scaled-down party, structured accepts.

Slide profile (--profile slide, added for the Nebius Academy alt scenario):
  round 1: loop hands off a 160-person booking with vegan_ratio=0.9; the
           slide-policy validator rejects on vegan_ratio_too_high (a rule
           that only exists under the slide profile — party_size=160 is
           under the 170 cap, so this proves a slide-specific rule fired).
  round 2: loop fixes the menu (vegan_ratio=0.5) and resubmits; structured
           accepts.

The slide path is what end-to-end verifies that the new `policy_profile`
field threads through `handoff_to_structured` → bridge → RasaStructuredHalf
→ normaliser → validator without being stripped along the way.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sovereign_agent._internal.llm_client import (
    FakeLLMClient,
    ScriptedResponse,
    ToolCall,
)
from sovereign_agent._internal.paths import example_sessions_dir
from sovereign_agent.executor import DefaultExecutor
from sovereign_agent.halves.loop import LoopHalf
from sovereign_agent.planner import DefaultPlanner
from sovereign_agent.session.directory import create_session

from starter.edinburgh_research.tools import build_tool_registry
from starter.handoff_bridge.bridge import HandoffBridge
from starter.rasa_half.structured_half import RasaStructuredHalf, spawn_mock_rasa


def _build_fake_client_two_rounds() -> FakeLLMClient:
    """Default profile: round 1 reject on party_too_large, round 2 accept."""
    plan_r1 = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "find venue near haymarket for 12",
                "success_criterion": "candidate identified",
                "estimated_tool_calls": 2,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )
    # round 2 — loop gets rejection reason, retries with different area
    plan_r2 = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "retry with larger venue after rejection",
                "success_criterion": "different venue with enough seats",
                "estimated_tool_calls": 2,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )

    return FakeLLMClient(
        [
            # === ROUND 1 ===
            ScriptedResponse(content=plan_r1),  # planner turn 1
            ScriptedResponse(  # executor turn 1: search
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="venue_search",
                        arguments={"near": "Haymarket", "party_size": 12, "budget_max_gbp": 2000},
                    )
                ]
            ),
            ScriptedResponse(  # executor turn 2: handoff
                tool_calls=[
                    ToolCall(
                        id="c2",
                        name="handoff_to_structured",
                        arguments={
                            "reason": "loop half identified a candidate venue; passing to structured half for confirmation under policy rules",
                            "context": "party of 12 near Haymarket on 2026-04-25 19:30; chosen venue haymarket_tap",
                            "data": {
                                "action": "confirm_booking",
                                "venue_id": "Haymarket Tap",
                                "date": "2026-04-25",
                                "time": "19:30",
                                "party_size": "12",
                                "deposit": "£0",
                            },
                        },
                    )
                ]
            ),
            # === ROUND 2 (after reverse handoff from structured rejecting party=12) ===
            ScriptedResponse(content=plan_r2),  # planner turn 2
            ScriptedResponse(  # executor turn 1: new search with smaller party
                tool_calls=[
                    ToolCall(
                        id="c3",
                        name="venue_search",
                        arguments={"near": "Old Town", "party_size": 6, "budget_max_gbp": 2000},
                    )
                ]
            ),
            ScriptedResponse(  # executor turn 2: handoff royal_oak with party=6
                tool_calls=[
                    ToolCall(
                        id="c4",
                        name="handoff_to_structured",
                        arguments={
                            "reason": "retry after reverse handoff — scaled down to fit policy",
                            "context": "party was originally 12; rejected; re-proposing party of 6 at royal_oak (16 seats)",
                            "data": {
                                "action": "confirm_booking",
                                "venue_id": "The Royal Oak",
                                "date": "2026-04-25",
                                "time": "19:30",
                                "party_size": "6",
                                "deposit": "£0",
                            },
                        },
                    )
                ]
            ),
        ]
    )


def _build_fake_client_slide() -> FakeLLMClient:
    """Slide profile: round 1 reject on vegan_ratio_too_high, round 2 accept.

    The vegan_ratio rejection is slide-specific — under the default policy
    that rule isn't enforced, so a positive outcome here is direct evidence
    that policy_profile threaded all the way through to the validator.
    """
    plan_r1 = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "find venue for 160-person webinar event near Haymarket with vegan options",
                "success_criterion": "candidate identified, deposit within budget",
                "estimated_tool_calls": 2,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )
    plan_r2 = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "renegotiate menu to bring vegan share under the cap",
                "success_criterion": "lower vegan_ratio with same venue",
                "estimated_tool_calls": 1,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )

    return FakeLLMClient(
        [
            # === ROUND 1 — vegan_ratio=0.9 will be rejected ===
            ScriptedResponse(content=plan_r1),
            ScriptedResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="venue_search",
                        arguments={
                            "near": "Haymarket",
                            "party_size": 160,
                            "budget_max_gbp": 2000,
                        },
                    )
                ]
            ),
            ScriptedResponse(
                tool_calls=[
                    ToolCall(
                        id="c2",
                        name="handoff_to_structured",
                        arguments={
                            "reason": "loop half identified a 160-person candidate venue; passing for slide-policy confirmation",
                            "context": "party of 160 near Haymarket on 2026-05-19 17:00; vegan-heavy menu proposed",
                            "data": {
                                "action": "confirm_booking",
                                "venue_id": "Haymarket Tap",
                                "date": "2026-05-19",
                                "time": "17:00",
                                "party_size": "160",
                                "deposit": "£300",
                                "vegan_ratio": 0.9,
                                "policy_profile": "slide",
                            },
                        },
                    )
                ]
            ),
            # === ROUND 2 — vegan_ratio dropped to 0.5; should accept ===
            ScriptedResponse(content=plan_r2),
            ScriptedResponse(
                tool_calls=[
                    ToolCall(
                        id="c3",
                        name="venue_search",
                        arguments={
                            "near": "Haymarket",
                            "party_size": 160,
                            "budget_max_gbp": 2000,
                        },
                    )
                ]
            ),
            ScriptedResponse(
                tool_calls=[
                    ToolCall(
                        id="c4",
                        name="handoff_to_structured",
                        arguments={
                            "reason": "retry with renegotiated menu — vegan share now 50%",
                            "context": "same venue and party size; vegan_ratio reduced from 0.9 to 0.5 to satisfy slide policy",
                            "data": {
                                "action": "confirm_booking",
                                "venue_id": "Haymarket Tap",
                                "date": "2026-05-19",
                                "time": "17:00",
                                "party_size": "160",
                                "deposit": "£300",
                                "vegan_ratio": 0.5,
                                "policy_profile": "slide",
                            },
                        },
                    )
                ]
            ),
        ]
    )


async def run_scenario(real: bool, profile: str) -> int:
    with example_sessions_dir(
        "ex7-handoff-bridge", persist=True
    ) as sessions_root:  # persist amended to preserve trace
        if profile == "slide":
            initial_task = "book a 160-person webinar venue near Haymarket on 2026-05-19, vegan options"
            scenario_label = "ex7-handoff-bridge-slide"
        else:
            initial_task = "book for party of 12 in Haymarket"
            scenario_label = "ex7-handoff-bridge"
        session = create_session(
            scenario=scenario_label,
            task=initial_task,
            sessions_dir=sessions_root,
        )
        print(f"Session {session.session_id}")
        print(f"  dir: {session.directory}")
        print(f"  profile: {profile}")

        # Spawn mock Rasa unless --real
        server = None
        if not real:
            server, _thread, mock_url = spawn_mock_rasa(port=5906)
            rasa_half = RasaStructuredHalf(rasa_url=mock_url)
        else:
            rasa_half = RasaStructuredHalf()

        client = _build_fake_client_slide() if profile == "slide" else _build_fake_client_two_rounds()
        tools = build_tool_registry(session)
        loop_half = LoopHalf(
            planner=DefaultPlanner(model="fake", client=client),
            executor=DefaultExecutor(model="fake", client=client, tools=tools),  # type: ignore[arg-type]
        )
        bridge = HandoffBridge(
            loop_half=loop_half,
            structured_half=rasa_half,
            max_rounds=3,
        )

        try:
            result = await bridge.run(session, {"task": initial_task})
        finally:
            if server is not None:
                server.shutdown()

        print(f"\nBridge outcome: {result.outcome}")
        print(f"  rounds: {result.rounds}")
        print(f"  summary: {result.summary}")
        return 0 if result.outcome == "completed" else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--real",
        action="store_true",
        help="Hit a live Rasa server instead of the stdlib mock.",
    )
    parser.add_argument(
        "--profile",
        choices=("default", "slide"),
        default="default",
        help="Bridge scenario profile. 'default' = the original party_too_large "
        "round-trip; 'slide' = a vegan_ratio_too_high round-trip that exercises "
        "the slide-policy rules end-to-end through the bridge.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run_scenario(real=args.real, profile=args.profile)))


if __name__ == "__main__":
    main()
