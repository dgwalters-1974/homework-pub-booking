"""Ex6 setup recipe — `make ex6-help`.

Prints the three-terminal recipe without probing anything or running
the scenario. Useful when students want to remember what they're
supposed to do without triggering a run.

We reuse the same layout as ex6_probe_and_run.py's bootstrap message
so students see consistent guidance everywhere.
"""

from __future__ import annotations

import os
import sys


class _C:
    _on = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    @classmethod
    def _w(cls, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if cls._on else s

    @classmethod
    def b(cls, s: str) -> str:
        return cls._w("1", s)

    @classmethod
    def cyan(cls, s: str) -> str:
        return cls._w("36", s)

    @classmethod
    def d(cls, s: str) -> str:
        return cls._w("2", s)

    @classmethod
    def y(cls, s: str) -> str:
        return cls._w("33", s)


def main() -> int:
    print()
    print(_C.y("━" * 72))
    print(_C.b("  Ex6 — running Rasa Pro locally (three-terminal recipe)"))
    print(_C.y("━" * 72))
    print()
    print(_C.b("  Why this is different from Ex5 and Ex7"))
    print()
    print("    Ex5 and Ex7 are single-process: one Python scenario that talks to a")
    print("    remote LLM via HTTP. Ex6 adds a THIRD party — Rasa — that runs as two")
    print("    separate processes on your machine. Teaching this multi-process")
    print("    coordination is the point of Ex6.")
    print()
    print(_C.b("  The three terminals"))
    print()
    print("    " + _C.cyan("Terminal 1:") + " " + _C.cyan("make rasa-actions"))
    print("      → Starts the action server on :5055.")
    print("      → Your ActionValidateBooking custom action lives here.")
    print("      → Prints every slot the flow sets.")
    print()
    print("    " + _C.cyan("Terminal 2:") + " " + _C.cyan("make rasa-serve"))
    print("      → Trains the model (if not already trained), then starts")
    print("        the Rasa server on :5005.")
    print("      → Logs every HTTP request, every command-generator call,")
    print("        every flow transition. Watch this while you debug.")
    print()
    print("    " + _C.cyan("Terminal 3:") + " " + _C.cyan("make ex6-real"))
    print("      → This terminal. Runs the scenario, POSTs to Rasa, prints")
    print("        the HalfResult. ~10 seconds.")
    print()
    print(_C.b("  Setup order matters"))
    print()
    print("    Start Terminal 1 FIRST. Terminal 2 second (so it can reach")
    print("    the action server when it boots). Terminal 3 last.")
    print()
    print(_C.b("  Ports"))
    print()
    print("    :5005 — Rasa REST API (Terminal 2 binds)")
    print("    :5055 — Custom action server (Terminal 1 binds)")
    print()
    print("    If either port is already in use you'll get a bind error.")
    print("    Check what's using them: " + _C.cyan("lsof -i :5005"))
    print()
    print(_C.b("  Alternative paths"))
    print()
    print("    " + _C.cyan("make ex6") + "          — mock-server mode, no Rasa install needed")
    print("    " + _C.cyan("make ex6-auto") + "     — auto-spawn everything (hides the lesson)")
    print()
    print(_C.b("  For the full walkthrough, read"))
    print()
    print("    " + _C.cyan("docs/rasa-setup.md"))
    print()
    print(_C.y("━" * 72))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
