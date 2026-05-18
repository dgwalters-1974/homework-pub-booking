"""Ex5 Task C — three-model comparison runner.

Sets SOVEREIGN_AGENT_LLM_PLANNER_MODEL / ..._EXECUTOR_MODEL for the requested
combo, invokes `python -m starter.edinburgh_research.run --real`, then copies
the newly-produced session directory from the platform data dir into the
repo's ./sessions/ and stamps an `extras/combo.txt` marker so the analysis
helper can group runs.

Usage:
    uv run python scripts/ex5_compare_run.py combo1
    uv run python scripts/ex5_compare_run.py combo2
    uv run python scripts/ex5_compare_run.py combo3
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

COMBOS: dict[str, tuple[str, str]] = {
    "combo1": ("Qwen/Qwen3-Next-80B-A3B-Thinking", "Qwen/Qwen3-235B-A22B-Instruct-2507"),
    "combo2": ("MiniMaxAI/MiniMax-M2.5", "Qwen/Qwen3-235B-A22B-Instruct-2507"),
    "combo3": ("Qwen/Qwen3-32B", "Qwen/Qwen3-32B"),
}

EXAMPLE_NAME = "ex5-edinburgh-research"


def persist_root() -> Path:
    override = os.environ.get("SOVEREIGN_AGENT_DATA_DIR")
    if override:
        return Path(override) / "examples" / EXAMPLE_NAME
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "sovereign-agent"
            / "examples"
            / EXAMPLE_NAME
        )
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "sovereign-agent" / "examples" / EXAMPLE_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "sovereign-agent" / "examples" / EXAMPLE_NAME


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("combo", choices=list(COMBOS))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the env vars and command that would run, then exit.",
    )
    parser.add_argument(
        "--rich",
        action="store_true",
        help=(
            "Set EX5_RICH_TASK=1 so the rich `rich_task` string in run.py "
            "is fed to the planner via input_payload (control experiment "
            "for Task C addendum Bug 4). Combo marker is tagged "
            "'<combo>-rich' so the analysis tool groups them separately."
        ),
    )
    parser.add_argument(
        "--task-string",
        default=None,
        help=(
            "Override the planner input with this exact string (sets "
            "EX5_TASK_STR in env). Use --tag to set the combo marker "
            "label. Takes precedence over --rich."
        ),
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Suffix for the combo marker label (e.g. 'slide' -> 'combo1-slide').",
    )
    args = parser.parse_args()

    planner, executor = COMBOS[args.combo]
    if args.tag:
        combo_label = f"{args.combo}-{args.tag}"
    elif args.rich:
        combo_label = f"{args.combo}-rich"
    else:
        combo_label = args.combo

    env = os.environ.copy()
    env["SOVEREIGN_AGENT_LLM_PLANNER_MODEL"] = planner
    env["SOVEREIGN_AGENT_LLM_EXECUTOR_MODEL"] = executor
    if args.task_string:
        env["EX5_TASK_STR"] = args.task_string
    elif args.rich:
        env["EX5_RICH_TASK"] = "1"

    print(f"▶ Combo: {combo_label}")
    print(f"  planner:  {planner}")
    print(f"  executor: {executor}")
    print(f"  rich-task: {'yes' if args.rich else 'no'}")

    if args.dry_run:
        print("(dry-run — not invoking run.py)")
        return 0

    root = persist_root()
    root.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in root.glob("sess_*") if p.is_dir()}

    started = time.monotonic()
    rc = subprocess.run(
        ["uv", "run", "python", "-m", "starter.edinburgh_research.run", "--real"],
        env=env,
    ).returncode
    elapsed = time.monotonic() - started
    print(f"  exit code: {rc}   wall-clock: {elapsed:.1f}s")

    after = {p.name for p in root.glob("sess_*") if p.is_dir()}
    new = sorted(after - before)
    if not new:
        print("ERROR: no new sess_* directory appeared in", root)
        return 1
    if len(new) > 1:
        print(f"WARN: multiple new sessions detected: {new} — picking newest by mtime")

    new_paths = [root / name for name in new]
    src = max(new_paths, key=lambda p: p.stat().st_mtime)
    sess_id = src.name
    dst = Path("sessions") / sess_id
    if dst.exists():
        print(f"ERROR: destination already exists: {dst}")
        return 1
    shutil.copytree(src, dst)

    extras = dst / "extras"
    extras.mkdir(exist_ok=True)
    marker = extras / "combo.txt"
    marker_lines = [
        f"combo={combo_label}",
        f"planner={planner}",
        f"executor={executor}",
        f"rich_task={'1' if args.rich and not args.task_string else '0'}",
        f"task_str_override={'1' if args.task_string else '0'}",
        f"wall_clock_s={elapsed:.2f}",
        f"exit_code={rc}",
    ]
    if args.task_string:
        # Persist the literal task string so the session is self-describing.
        marker_lines.append(f"task_string={args.task_string!r}")
    marker.write_text("\n".join(marker_lines) + "\n", encoding="utf-8")

    print(f"✓ Session copied to {dst}")
    print(f"✓ Marker        :  {marker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
