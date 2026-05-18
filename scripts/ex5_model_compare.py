"""Ex5 Task C — analysis helper.

Walks ./sessions/ for sess_* directories that have an `extras/combo.txt`
marker (written by scripts/ex5_compare_run.py). For each such session,
extracts:

  - success classification (complete / partial / spiral-capped / crash)
  - total llm_tokens_in + llm_tokens_out across all tickets
  - wall-clock latency (last trace event ts - first trace event ts)
  - tool-call counts (total + venue_search-specific)
  - whether the flyer.html exists, whether dataflow check passes

Outputs:

  - a per-combo markdown table to stdout
  - a per-run JSON dump to answers/ex5_task_c_data.md (markdown wrapper
    around fenced JSON, so the file remains rubric-compatible).

Usage:
    uv run python scripts/ex5_model_compare.py
"""

from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SESSIONS = REPO / "sessions"
OUTPUT = REPO / "answers" / "ex5_task_c_data.md"


def parse_marker(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def read_trace_events(trace_path: Path) -> list[dict]:
    events: list[dict] = []
    if not trace_path.exists():
        return events
    with trace_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def analyse_session(session_dir: Path) -> dict:
    marker = parse_marker((session_dir / "extras" / "combo.txt").read_text())
    sess_id = session_dir.name

    # Token + duration accumulation from ticket manifests
    tokens_in = 0
    tokens_out = 0
    ticket_count = 0
    ticket_durations_ms = 0
    for mpath in (session_dir / "logs" / "tickets").glob("*/manifest.json"):
        try:
            m = json.loads(mpath.read_text())
        except json.JSONDecodeError:
            continue
        metrics = m.get("metrics") or {}
        tokens_in += int(metrics.get("llm_tokens_in") or 0)
        tokens_out += int(metrics.get("llm_tokens_out") or 0)
        ticket_count += 1
        ticket_durations_ms += int(m.get("duration_ms") or 0)

    # Wall clock from trace.jsonl
    events = read_trace_events(session_dir / "logs" / "trace.jsonl")
    wall_clock_s: float | None = None
    if len(events) >= 2:
        try:
            first = parse_iso(events[0]["timestamp"])
            last = parse_iso(events[-1]["timestamp"])
            wall_clock_s = (last - first).total_seconds()
        except (KeyError, ValueError):
            wall_clock_s = None

    # Tool-call summary from executor.tool_called events
    tool_called_events = [e for e in events if e.get("event_type") == "executor.tool_called"]
    venue_search_calls = [e for e in tool_called_events if e.get("payload", {}).get("tool") == "venue_search"]
    spiral_capped = any(
        (e.get("payload", {}).get("success") is False)
        and "STOP calling venue_search" in str(e.get("payload", {}).get("summary", ""))
        for e in venue_search_calls
    )
    handoff_called = any(
        e.get("payload", {}).get("tool") == "handoff_to_structured" for e in tool_called_events
    )
    generate_flyer_called = any(
        e.get("payload", {}).get("tool") == "generate_flyer" for e in tool_called_events
    )

    # Session terminal state
    try:
        session_json = json.loads((session_dir / "session.json").read_text())
        terminal_state = session_json.get("state")
    except (FileNotFoundError, json.JSONDecodeError):
        terminal_state = None

    flyer_path = session_dir / "workspace" / "flyer.html"
    flyer_exists = flyer_path.exists()

    # Outcome classification — coarse but useful. Success (flyer produced)
    # wins regardless of whether the spiral cap also fired along the way.
    if flyer_exists and terminal_state == "complete":
        outcome = "complete"
    elif flyer_exists:
        outcome = "flyer-no-complete-state"
    elif spiral_capped:
        outcome = "spiral-capped-no-flyer"
    elif handoff_called and not generate_flyer_called:
        outcome = "handed-off-no-flyer"
    elif terminal_state in (None, "failed", "error"):
        outcome = "failed-or-incomplete"
    else:
        outcome = f"other:{terminal_state}"

    return {
        "session_id": sess_id,
        "combo": marker.get("combo", "?"),
        "planner": marker.get("planner", "?"),
        "executor": marker.get("executor", "?"),
        "outcome": outcome,
        "wall_clock_s": round(wall_clock_s, 1) if wall_clock_s is not None else None,
        "ticket_duration_total_ms": ticket_durations_ms,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_total": tokens_in + tokens_out,
        "tickets": ticket_count,
        "tool_calls_total": len(tool_called_events),
        "venue_search_calls": len(venue_search_calls),
        "spiral_capped": spiral_capped,
        "handoff_to_structured": handoff_called,
        "generate_flyer": generate_flyer_called,
        "flyer_exists": flyer_exists,
        "terminal_state": terminal_state,
    }


def fmt_int(n: int | None) -> str:
    return f"{n:,}" if isinstance(n, int) else "—"


def fmt_float(n: float | None, decimals: int = 1) -> str:
    return f"{n:.{decimals}f}" if isinstance(n, (int, float)) else "—"


def aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {}
    successes = sum(1 for r in rows if r["outcome"] == "complete")
    return {
        "runs": len(rows),
        "success_count": successes,
        "success_rate": successes / len(rows),
        "mean_tokens_in": statistics.mean(r["tokens_in"] for r in rows),
        "mean_tokens_out": statistics.mean(r["tokens_out"] for r in rows),
        "mean_tokens_total": statistics.mean(r["tokens_total"] for r in rows),
        "mean_wall_clock_s": (
            statistics.mean(r["wall_clock_s"] for r in rows if r["wall_clock_s"] is not None)
            if any(r["wall_clock_s"] is not None for r in rows)
            else None
        ),
        "mean_tool_calls": statistics.mean(r["tool_calls_total"] for r in rows),
        "spiral_capped_count": sum(1 for r in rows if r["spiral_capped"]),
    }


def main() -> int:
    if not SESSIONS.exists():
        print(f"no sessions/ dir at {SESSIONS}", file=sys.stderr)
        return 1

    all_rows: list[dict] = []
    for session_dir in sorted(SESSIONS.glob("sess_*")):
        marker = session_dir / "extras" / "combo.txt"
        if not marker.exists():
            continue
        all_rows.append(analyse_session(session_dir))

    if not all_rows:
        print("no tagged sessions found (looking for sessions/sess_*/extras/combo.txt)")
        return 0

    # Group per combo
    by_combo: dict[str, list[dict]] = {}
    for r in all_rows:
        by_combo.setdefault(r["combo"], []).append(r)

    # Summary table
    print("\n## Per-combo summary\n")
    print(
        "| Combo | Runs | Success | Mean tokens in/out | Mean wall-clock | Mean tool-calls | Spiral-capped |"
    )
    print("|---|---|---|---|---|---|---|")
    for combo in sorted(by_combo):
        agg = aggregate(by_combo[combo])
        print(
            f"| {combo} ({by_combo[combo][0]['planner']} + {by_combo[combo][0]['executor']}) "
            f"| {agg['runs']} "
            f"| {agg['success_count']}/{agg['runs']} ({agg['success_rate']*100:.0f}%) "
            f"| {fmt_int(int(agg['mean_tokens_in']))} / {fmt_int(int(agg['mean_tokens_out']))} "
            f"| {fmt_float(agg['mean_wall_clock_s'])}s "
            f"| {fmt_float(agg['mean_tool_calls'])} "
            f"| {agg['spiral_capped_count']}/{agg['runs']} |"
        )

    print("\n## Per-run detail\n")
    print(
        "| Combo | Session | Outcome | Wall-clock | Tokens (in+out) | Tool calls | venue_search | Flyer | Handoff |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    for r in sorted(all_rows, key=lambda x: (x["combo"], x["session_id"])):
        print(
            f"| {r['combo']} | `{r['session_id']}` | {r['outcome']} "
            f"| {fmt_float(r['wall_clock_s'])}s "
            f"| {fmt_int(r['tokens_in'])} + {fmt_int(r['tokens_out'])} = {fmt_int(r['tokens_total'])} "
            f"| {r['tool_calls_total']} "
            f"| {r['venue_search_calls']}{' (capped)' if r['spiral_capped'] else ''} "
            f"| {'✓' if r['flyer_exists'] else '✗'} "
            f"| {'✓' if r['handoff_to_structured'] else '✗'} |"
        )

    # Persist raw per-run JSON to answers/ex5_task_c_data.md
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w") as f:
        f.write("# Ex5 Task C — per-run raw data\n\n")
        f.write("Auto-generated by `scripts/ex5_model_compare.py`. Do not edit by hand.\n\n")
        f.write("Re-run with `make ex5-compare-analysis`.\n\n")
        f.write("## Aggregate (by combo)\n\n")
        f.write("```json\n")
        f.write(json.dumps({c: aggregate(by_combo[c]) for c in sorted(by_combo)}, indent=2))
        f.write("\n```\n\n## Per-run\n\n```json\n")
        f.write(json.dumps(sorted(all_rows, key=lambda x: (x["combo"], x["session_id"])), indent=2))
        f.write("\n```\n")
    print(f"\n✓ raw data written: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
