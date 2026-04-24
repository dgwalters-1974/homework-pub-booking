# homework-pub-booking

**Build an AI agent that books a pub in Edinburgh.** Five exercises. One story.
Real LLMs, a real Rasa dialog engine, and a real voice pipeline (if you want it).

> The theme running through this homework is a specific, grounded task: your
> agent has to find an Edinburgh pub, check that it can seat your party, compute
> the booking cost, confirm it against deposit rules, and — in the bonus
> exercise — handle a voice callback from the manager. You'll implement each
> piece yourself. At the end you'll have an agent that works end-to-end, not
> just a stack of unit tests.

---

## What you're about to build

You're the operations manager for a consultancy. Your boss asks you:

> "Sort out a pub for tonight. We'll be 6 people, near Haymarket, starting at
> 19:30. I want a proper place — not a chain — and we need catering. The
> deposit mustn't go above £300."

That's the task. A human could do it with 30 minutes of browsing. Your agent
is going to do it autonomously, in under 10 seconds, for about £0.01 in LLM
tokens. By the end of Ex7, your agent:

1. **Searches** a small fixture of Edinburgh pubs (`venue_search`), filtering by area and party size
2. **Checks weather** for the evening (`get_weather`)
3. **Calculates cost** using base rates and venue modifiers (`calculate_cost`)
4. **Produces a flyer** in markdown (`generate_flyer`)
5. **Hands off** to a **Rasa-powered dialog system** that confirms the booking under rules — party size, deposit cap
6. If the manager pushes back (party too large, deposit too high), the Rasa half **sends control back to the research agent** to find an alternative
7. Optionally, the manager's call-back happens as a **real voice conversation** — speech-to-text via Speechmatics, text-to-speech via Rime.ai's Arcana model, a Qwen-70B "manager persona" talking to your Rasa bot

If this sounds ambitious, it is. But it's also how real production agent
systems are built: a **loop half** (the LLM with tools) hands off to a
**structured half** (deterministic rules / Rasa flows) for high-stakes
decisions. The homework teaches that pattern using a concrete, narrated
scenario.

---

## The agent architecture, in one picture

```
   ┌─────────────────────────────────────────────────────────────────┐
   │ LOOP HALF          (Ex5)                                         │
   │ "Find me a pub"                                                  │
   │                                                                  │
   │   Planner (Qwen3-80B-Thinking) ─┐                                │
   │                                  │                                │
   │   Executor (Qwen3-32B) ──► tools:                                 │
   │     venue_search, get_weather, calculate_cost, generate_flyer    │
   │                                                                  │
   │                           writes workspace/flyer.md              │
   └─────────────────────────────────────────────────────────────────┘
                                │
                  ipc/handoff_to_structured.json
                                │
                                ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │ STRUCTURED HALF    (Ex6)                                         │
   │ "Can I confirm this?"                                            │
   │                                                                  │
   │   Rasa Pro CALM flow: confirm_booking                            │
   │     ├─ action_validate_booking                                   │
   │     │    ├─ party > 8       ─► rejected ("party_too_large")      │
   │     │    ├─ deposit > £300  ─► rejected ("deposit_too_high")     │
   │     │    └─ otherwise        ─► committed with booking ref       │
   │     └─ utter_booking_{confirmed,rejected}                        │
   └─────────────────────────────────────────────────────────────────┘
                │                    │
         rejected + reason        committed
                │                    │
                ▼                    ▼
   ┌──────────────────────┐    ┌────────────────┐
   │ Ex7: bridge sends    │    │ done           │
   │ a REVERSE task back  │    └────────────────┘
   │ to the loop half     │
   │ → find another venue │
   └──────────────────────┘

              Ex8 (bonus): manager calls back. Speech-to-text (Speechmatics)
              → Rasa → TTS (Rime.ai Arcana). Real voice.
```

Every piece writes to `sessions/sess_<id>/`. Every step leaves a ticket.
Every tool call is logged to `logs/trace.jsonl`. When something goes wrong,
`make narrate-latest` reads the trace back to you in English.

---

## Quick start

```bash
git clone https://github.com/sovereignagents/homework-pub-booking.git
cd homework-pub-booking

# 1. Install Python 3.12 deps + sovereign-agent 0.2.0
make setup

# 2. Put your API keys in .env (see "Keys you'll need" below)
$EDITOR .env

# 3. Confirm the environment works (one free 1-token Nebius call)
make verify

# 4. You're ready. Start with Ex5.
```

If `make verify` prints green ✓ on every line, you're good. If something is
red, the message tells you exactly which doc to read (most commonly
`docs/nebius-signup.md`).

---

## Keys you'll need

Fill these into `.env` before running anything real. `.env.example` has the
full list with comments.

| Key | What for | Cost |
|---|---|---|
| `NEBIUS_KEY` | All LLM calls (Ex5, Ex7 executor/planner, Ex8 manager persona) | ~£0.01 per scenario run |
| `RASA_PRO_LICENSE` | Ex6 real Rasa server (tier 2 and 3) | [Free developer license](https://rasa.com/rasa-pro-developer-edition/) |
| `SPEECHMATICS_KEY` | Ex8 voice only — STT | Free tier is generous |
| `RIME_API_KEY` | Ex8 voice only — TTS (Arcana model) | Free tier available |

**Text-only path:** you can finish Ex5, Ex6 (mock mode), Ex7, and Ex9 with
just `NEBIUS_KEY`. `RASA_PRO_LICENSE` unlocks the real Rasa integration for
Ex6 (worth doing — that's the meat of the exercise). Ex8 degrades to text
mode if speech keys are missing; you'll still get points.

---

## The five exercises

| Ex | File to fill in | What you build | Time |
|---|---|---|---|
| **Ex5** | `starter/edinburgh_research/tools.py` + `integrity.py` | Four tools + a dataflow-integrity check that catches LLM fabrication | 3–4h |
| **Ex6** | `starter/rasa_half/validator.py` + `structured_half.py` + `rasa_project/` | Normalise booking data + POST to Rasa + real `ActionValidateBooking` | 4–5h |
| **Ex7** | `starter/handoff_bridge/bridge.py` | Orchestrate round-trips between loop and structured halves | 2–3h |
| **Ex8** | `starter/voice_pipeline/voice_loop.py` | Real Speechmatics STT + Rime.ai TTS + manager persona | 3–5h |
| **Ex9** | `answers/ex9_reflection.md` | Three reflection questions, grounded in YOUR session logs | 1–2h |

Every exercise ships with:
- A scaffold that `make setup` compiles cleanly
- A public test file that currently SKIPS (implement TODOs → skips become passes)
- A hand-holding docstring on each function
- Reference pattern in `sovereign-agent/examples/*` for how a similar thing
  is implemented in the framework itself

Run `make test` between commits. If all skips turn into passes, you're on
track. The grader runs the same tests plus private ones you don't see.

---

## How to run your work

Every exercise has an offline and a real mode:

```bash
make ex5                 # offline — FakeLLMClient, scripted trajectory
make ex5-real            # live — real Nebius API call, costs ~£0.02
```

`ex5-real` is how you'll check your work against actual LLM behaviour.
Offline mode is for fast iteration while you're implementing.

**After any run**, you can replay what happened in plain English:

```bash
make narrate-latest
```

That reads your most recent session's `trace.jsonl` and tells you the story:

```
06:49:28  🧠  Planner is thinking about how to break this down...
06:49:28  📋  Planner produced 2 subgoal(s)
06:49:28  — tool call —
  🔍  venue_search near='Haymarket', party=6
      → venue_search('Haymarket', party=6): 1 result(s)
06:49:28  — tool call —
  🌤️   get_weather city='edinburgh', date='2026-04-25'
      → get_weather('edinburgh', '2026-04-25'): cloudy, 12C
06:49:28  — tool call —
  💷  calculate_cost venue='haymarket_tap', party=6
      → calculate_cost(haymarket_tap, party=6): total £556, deposit £111
06:49:28  — tool call —
  ✍️   generate_flyer venue='Haymarket Tap', total=£556
      → generate_flyer: wrote workspace/flyer.md (243 bytes)
06:49:28  — tool call —
  🏁  complete_task ← agent says it's done

  Artifacts
    📄 workspace/flyer.md (243 bytes)
```

This is the fastest way to debug. When your scenario fails silently,
`make narrate-latest` usually shows why in one screen. For a specific session:

```bash
make narrate SESSION=sess_ac9861096e43
```

---

## Ex6 is different — you'll need three terminals

**Ex5, Ex7, and Ex8 are single-process: one Python scenario that talks to a
remote LLM.** `make ex5-real` just works if your `.env` is set up.

**Ex6 is multi-process.** The Rasa structured half runs as two independent
processes on your machine — a Rasa server and an action server — that
your scenario POSTs to. This is not an accident of how we built the
homework; it's how Rasa is designed, and it's how production agent systems
actually deploy. Watching three log streams in three terminals is the
point.

### The three-terminal layout

```
 ┌────────────────┐        ┌────────────────┐        ┌──────────────────┐
 │  Terminal 3    │───────▶│  Terminal 2    │───────▶│  Terminal 1      │
 │                │ HTTP   │                │ HTTP   │                  │
 │  make ex6-real │  POST  │ make rasa-serve│  POST  │ make rasa-actions│
 │                │        │    :5005       │        │   :5055          │
 │  (scenario)    │        │                │        │                  │
 └────────────────┘        └────────────────┘        └──────────────────┘
```

Open three terminals in the repo, and run these in order:

```bash
# Terminal 1 — action server (runs ActionValidateBooking)
make rasa-actions

# Terminal 2 — Rasa server (trains model first time, then serves)
make rasa-serve

# Terminal 3 — your scenario (probes Rasa, runs if green)
make ex6-real
```

Leave terminals 1 and 2 running the whole time you're working on Ex6.
When you change `rasa_project/flows.yml` or `actions.py`, Ctrl-C terminal 2
and re-run `make rasa-serve` to retrain.

### `make ex6-real` won't guess for you

If you run `make ex6-real` before starting the other two terminals, you
get this:

```
✗ Rasa not reachable at localhost:5005.

Ex6 real mode needs two processes running in separate terminals:

  ┌──────────────────────────────────────────────────────────────┐
  │  Terminal 1 (action server):    make rasa-actions            │
  │  Terminal 2 (rasa server):      make rasa-serve              │
  │  Terminal 3 (this one):         make ex6-real                │
  └──────────────────────────────────────────────────────────────┘
```

Clear failure. Specific fix. The exercise deliberately does NOT auto-start
Rasa for you because watching the logs in separate terminals is half the
lesson.

### `make ex6-help` if you forget the recipe

Any time you want the three-terminal setup printed out:

```bash
make ex6-help
```

### What if you don't have a Rasa Pro license yet?

Ex6 has three tiers:

| Tier | Command | Needs | What it teaches |
|---|---|---|---|
| **1** | `make ex6` | nothing | HTTP contract shape (mock server inside the scenario) |
| **2** | `make ex6-real` | Rasa Pro license + 3 terminals | Multi-process coordination, real CALM flows |
| **3** | `make ex6-auto` | Rasa Pro license only | Fast feedback loop once you've learned tier 2 |

**Tier 1 lets you progress without a license.** The mock server matches
Rasa's HTTP response shape, so your `normalise_booking_payload` and
`RasaStructuredHalf.run` implementations validate end-to-end. You lose
about 40% of Ex6's Behavioural points (the ones that grade against real
CALM flows) but keep everything else.

Tier 3 auto-spawns the two Rasa processes inside the scenario runner.
Use this when you've internalised the two-terminal pattern and just want
quick validation — e.g. right before committing. The CI grader uses
tier 3 for reproducible scoring.

### Full walkthrough

[`docs/rasa-setup.md`](docs/rasa-setup.md) has the complete guide —
license signup, first-run timing, what each log file means, and the
top-5 things that break on first run. If you hit anything weird, that
doc is the first place to look.

---

## A worked example — Ex5 walkthrough

### Step 1 — implement the tools

Open `starter/edinburgh_research/tools.py`. Four functions with
`raise NotImplementedError`:

```python
def venue_search(near: str, party_size: int, budget_max_gbp: int = 1000) -> ToolResult:
    """Search Edinburgh venues near <near> that can seat the party.

    Reads sample_data/venues.json. Filters by:
      * open_now == True
      * area contains <near> (case-insensitive substring match)
      * seats_available_evening >= party_size
      * hire_fee_gbp + min_spend_gbp <= budget_max_gbp
    """
    raise NotImplementedError("TODO 1: implement venue_search")
```

Implement each. The hardest function is the last one, `generate_flyer`,
which has to write a well-formed markdown flyer to `workspace/flyer.md`.

### Step 2 — implement the dataflow integrity check

`starter/edinburgh_research/integrity.py` has a single TODO — `verify_dataflow`.
This function reads the flyer AND the tool-call log, and verifies that every
money amount, every temperature, every condition in the flyer came from a
real tool call.

This is the heart of Ex5. The LLM can fabricate plausible values. A flyer
that says "Total: £560" when `calculate_cost` actually returned £540 is a
fabrication. Your check catches it.

We grade this by planting an obvious fabrication (like £9999) into the
flyer and confirming your check rejects it.

### Step 3 — run it

```bash
make ex5               # offline run — should be fast
make narrate-latest    # see what happened
make ex5-real          # live run — uses real LLM
```

### Step 4 — make the integrity check fail on purpose

This is part of the exercise. Edit the flyer your agent produced — change
`£540` to `£9999` — and run `verify_dataflow` against it. Your check should
fail. If it passes, it's too lenient. The grader will plant such a
fabrication on your behalf during scoring.

### Step 5 — write up Ex9-Q2

You'll describe this experiment in `answers/ex9_reflection.md` — what you
planted, what the check caught, what it missed. That's one of the three
reasoning questions for Ex9.

---

## The session directory — your main debugging tool

Every run creates `sessions/sess_<id>/`. Look inside:

```
sessions/sess_ac9861096e43/
├── session.json             # what state the session is in
├── workspace/
│   └── flyer.md             # what the agent produced
├── logs/
│   └── trace.jsonl          # every event, every tool call
├── tickets/
│   └── tk_*.json            # one per operation
└── ipc/
    └── handoff_to_*.json    # messages between halves
```

You don't need special tools. `cat`, `ls`, `jq` are the whole debugger.
Every question you could ask about what happened ("which tool got called
when", "what did the planner output", "what did the structured half say")
answers to a file in that directory. This is [Decision 1](https://github.com/sovereignagents/sovereign-agent)
from the sovereign-agent architecture — sessions are directories. It's
worth internalising: your future self, debugging at 2 AM, will thank you.

If you get lost, `make narrate SESSION=<id>` walks the trace for you.

---

## Testing — keep these green

```bash
make test                    # run all public tests
make lint                    # ruff check
make format                  # ruff format
make ci                      # everything CI runs on PR
```

`make test` is the fastest signal. On a fresh clone it reports:

```
24 passed, 3 skipped in 0.4s
```

The 3 skips are `test_verify_dataflow_*`, `test_normalise_booking_payload_*`,
and `test_ex6_validates_party_size`. Each skip comes from a `pytest.skip()`
call that triggers when your TODO raises `NotImplementedError`. Your goal is
to turn all three into `passed`. When that happens, you know you've made
meaningful progress.

---

## Grading

Your code is graded by `grader/check_submit.py`. Run it yourself:

```bash
make check-submit
```

```
## Mechanical (27 points)
  ✓ repo_has_required_top_level_files
  ✓ pyproject_pins_sovereign_agent_0_2_0
  ✓ ruff_lint_clean
  ✓ ruff_format_clean
  ✓ pytest_collects
  ✗ public_tests_pass                     — 0/5 (tests still skip)
  ✓ answers_files_exist
  ✗ answers_not_empty                     — 0/3 (Ex9 placeholder)
  ✗ all_scenarios_have_integrity_check    — 0/5 (handoff_bridge has no integrity.py)

## Behavioural (19 points)
  ✗ ex5_scenario_runs_end_to_end          — 0/6 (flyer.md not written)
  ✗ ex6_structured_half_runs              — 0/4 (Rasa half stub)
  ✗ ex7_round_trip_completes              — 0/6 (bridge stub)
  ✗ ex8_voice_loop_implemented            — 0/3 (voice_loop.run_voice_mode stub)

## Reasoning (30 points)
  Scored by CI with LLM judge. Answer quality matters; cite real session IDs.
```

**Fresh scaffold starts at ~4/76.** That's 14 mechanical freebies (ruff,
pytest-collect, file-shape) minus a 10-point penalty for missing
integrity checks. Every exercise you complete moves that number up.

A complete, well-implemented submission scores ~70/76 locally (the Reasoning
30 come from CI where the LLM judge runs). The cohort average is typically
55–65; anything above 65 is solid.

---

## Where things go when they break

Four layers of defence from "most helpful" to "actually digging into the
code":

1. **`make verify`** — one-shot diagnostic. Tells you if the environment
   is broken.
2. **`make narrate-latest`** — narrates your last run in English.
3. **`docs/troubleshooting.md`** — organised by error message.
4. **`logs/trace.jsonl`** + `cat` — the source of truth. Nothing is
   hidden in an SDK; every decision the agent made is one `cat` away.

If all four fail, file a GitHub issue. Include the output of `make verify`
and `make narrate-latest`. Usually we can spot the problem from those.

---

## Pinning policy

This cohort pins `sovereign-agent == 0.2.0` exactly.

```toml
[project]
dependencies = [
    "sovereign-agent == 0.2.0",    # do not change without a CHANGELOG entry
    ...
]
```

If sovereign-agent ships `0.2.1` with a bug fix, you can bump the pin after
reading its CHANGELOG. `0.3.0` is a minor version — breaking changes
possible — and is never automatic. We'll tell you cohort-wide when (if) to
upgrade.

Why exact-pin for a cohort? The grader runs against `0.2.0`. Different
versions produce slightly different planner outputs and trace shapes. One
pin = one set of expected behaviours = fair grading.

---

## Three surfaces, one repo

```
homework-pub-booking/
├── starter/                    # where you implement
│   ├── edinburgh_research/     # Ex5
│   ├── rasa_half/              # Ex6
│   ├── handoff_bridge/         # Ex7
│   └── voice_pipeline/         # Ex8
├── answers/                    # where you write reflections (Ex9)
├── rasa_project/               # Rasa flows + custom actions
├── tests/public/               # tests you can see (the grader also has private ones)
├── scripts/                    # make verify, make narrate, etc
└── docs/                       # setup, troubleshooting, grading rubric
```

Three things are deliberately kept OUT of this repo:

- **Solution code.** Lives in a private educator-only repo. If you see a
  `solution/` directory in your checkout, please open an issue — you
  shouldn't have access to it.
- **Real session artifacts.** `sessions/` is gitignored. Don't commit it
  (it'll contain API tokens in tool call logs).
- **`.env`.** Contains secrets. Gitignored. `.env.example` is the template.

---

## Lineage

The homework design follows the [sovereign-agent](https://github.com/sovereignagents/sovereign-agent)
teaching pattern, inspired by:

- **[fastai](https://github.com/fastai/fastai)** (Jeremy Howard) — library + course
  as one thing
- **[nanoGPT](https://github.com/karpathy/nanoGPT)** (Andrej Karpathy) — small,
  readable, no magic
- **[LLMs-from-scratch](https://github.com/rasbt/LLMs-from-scratch)** (Sebastian
  Raschka) — reading order matters
- **[minitorch](https://github.com/minitorch/minitorch)** (Sasha Rush) —
  rebuild-the-framework pedagogy

The agent architecture itself — sessions-as-directories, two halves, atomic
IPC, tickets-as-commits — descends from **[NanoClaw](https://github.com/qwibitai/nanoclaw)**
(Gavriel Cohen), with lessons from Claude Code, OpenHands, Aider, and the
SWE-agent paper.

---

## License

MIT. See [`LICENSE`](LICENSE).

---

**Next:** [`SETUP.md`](SETUP.md) walks you through `.env` configuration,
[`ASSIGNMENT.md`](ASSIGNMENT.md) has the full five-exercise spec, and
[`docs/grading-rubric.md`](docs/grading-rubric.md) is how the grader
assigns points. Start with `make setup`.
