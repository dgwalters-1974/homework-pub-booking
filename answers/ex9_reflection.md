# Ex9 — Reflection

(answers to these questions were forced to respect the word limits requested - there are more details / more thorough discussions in some of the earlier answer sheets (Ex5 through Ex8) should you require them. It wasn't clear to me if we were supposed to fill those answers in or just this one, and if so, whether the word limit applied - pls ignore if this is the case)

## Q1 — Planner handoff decision

> "Find a point in your Ex7 logs where the planner decided to hand off to the structured half. Quote the planner's reasoning or the specific subgoal's `assigned_half` field. What signal caused the decision?"

### Your answer

In my Ex7 run (`sessions/sess_7adc10a30e4c`), the planner did **not** assign any subgoal to the structured half. The planner ran twice -once per round — and each call produced a single subgoal with `assigned_half: "loop"`. `session.json` only retains the latest planner state, so `.planner.subgoals` shows just the round-2 subgoal (`sg_1`: "retry with larger venue after rejection"); the round-1 subgoal ("find venue near haymarket for 12") is recoverable from `logs/trace.jsonl` via the two `planner.called` / `planner.produced_subgoals` events.

What this tells us is that the loop-to-structured transition wasn't a planner-level decision - it happened one layer down, in the executor. In `logs/trace.jsonl`, after each subgoal's `venue_search` call (this can be seen on lines 5 & 12 of the unformatted `logs/trace.jsonl`), the next `executor.tool_called` event has `payload.tool == "handoff_to_structured"` (e.g. round-1 turn 2 carries `data.venue_id = "Haymarket Tap"`). The bridge then reads `loop_result.next_action == "handoff_to_structured"` (`bridge.py:92`), calls `build_forward_handoff` / `write_handoff` (`bridge.py:103-104`) and emits `session.state_changed` with `from: "loop", to: "structured", round: 1`.

The signal that caused the decision was therefore the existence of a `handoff_to_structured` tool in the executor's tool registry, plus the executor LLM's interpretation of "venue identified" as a state worth committing under policy rules. In our offline run the FakeLLMClient script hardcoded that choice; in a real-LLM run the same conclusion would emerge from the executor system prompt (`executor/__init__.py:58-73`), which explicitly tells the LLM to call `handoff_to_structured` when appropriate.

Looking a bit deeper at this, the planner's `assigned_half` field is just advisory, not 'load-bearing'. The meaningful handoff decision comes in the tool layer — whether `handoff_to_structured` exists at all — and emerges from the executor LLM's tool choice. This connects to the planner info-compression issue I documented in Ex5: the planner's outputs are heavily summarised before they reach the executor, so decisions made at the planner level often don't survive intact right the way through the pipeline.

### Citation

- `sessions/sess_7adc10a30e4c/session.json` — `.planner.subgoals` showing the (round-2) subgoal with `assigned_half: "loop"`
- `sessions/sess_7adc10a30e4c/logs/trace.jsonl` — two `planner.called` / `planner.produced_subgoals` pairs (one per round, 1 subgoal each); `executor.tool_called` events for `handoff_to_structured` in both rounds; `session.state_changed` events showing the actual transitions
- `starter/handoff_bridge/bridge.py:92,103-110` — bridge reads `loop_result.next_action`, then writes the handoff and emits `session.state_changed`
- `.venv/lib/python3.12/site-packages/sovereign_agent/executor/__init__.py:58-73` — executor system prompt encouraging `handoff_to_structured` for high-stakes actions
- `.venv/lib/python3.12/site-packages/sovereign_agent/planner/__init__.py:94-101` — planner instructed to set `assigned_half` per subgoal

---

## Q2 — Dataflow integrity catch

> "Describe one instance where your Ex5 dataflow integrity check caught something manual inspection missed, OR (if you never saw it trigger) describe a plausible scenario where it WOULD catch a failure that a human reviewer wouldn't. Your scenario must be specific enough that someone else could construct the test case."

### Your answer

The Ex5 offline harness (`make ex5`, session `sessions/sess_2f5bd9478e9b`) delivers a deliberately fabricated flyer - the FakeLLMClient script in `starter/edinburgh_research/run.py` contains `event_details = {"total_gbp": 540, "deposit_required_gbp": 0, ...}`, while `calculate_cost('haymarket_tap', 6, 3, 'bar_snacks')` actually returns `total=556, deposit=111` (independently derivable from `sample_data/catering.json` + `sample_data/venues.json:haymarket_tap`).

As the code was initially, `verify_dataflow` reports "OK" anyway because of two bugs in `integrity.py`:

- **Bug 1** (`integrity.py lines 64-68`): the regex `£\d+` requires `£` adjacent to a digit, but `tools.py:353,357` renders its monetary output as nested `<span>£<span data-testid="...">N</span></span>` tags that become `" £ 540 "` after tag-stripping. The details actually never get extracted at all.
- **Bug 2** (`integrity.py line 112`): `fact_appears_in_log` scans both `r.output` AND `r.arguments`, so the LLM's hallucinated values self-verify via `generate_flyer`'s own arguments dict — the artefact-builder is marking its own work.

After applying fixes to both these issues(regex changed to `£\s*\d+(?:\.\d+)?`, drop the `or _scan(r.arguments)` clause), `make ex5` exits non-zero with `dataflow FAIL: 1 unverified fact(s): ['£ 540']`. Manual inspection consistently misses this because £540 is a plausible amount — close to the real £556, follows the deposit-policy thresholds that are provided in `catering.json` and renders identically to legitimate values. A human reviewer scanning the rendered flyer will miss this almost every time.

The lesson here (also visible in this run) is that integrity checks must verify against tool outputs (i.e. what was *produced*), never the arguments to tools (which are the LLM's claims). Field-aware matching via the unused `extract_testid_facts` helper at `integrity.py:85-96` would also resolve a third issue I documented ('bare-number' collisions on `0`).

### Citation

- `sessions/sess_2f5bd9478e9b/workspace/flyer.html` — the fabricated flyer with `total_gbp=540`, `deposit_required_gbp=0`
- `sessions/sess_2f5bd9478e9b/session.json` — completed run state (`state: "complete"`) despite the fabrication
- `sessions/sess_2f5bd9478e9b/logs/tickets/{tk_844e0ff0,tk_c5b0dbbb,tk_f84530ed}/state.json` — all three operation tickets show `"state": "success"` despite the fabrication
- `starter/edinburgh_research/run.py:79-95` — hand-typed `event_details` (the fabrication source)
- `starter/edinburgh_research/integrity.py:64-68` — Bug 1 (regex blind to whitespace)
- `starter/edinburgh_research/integrity.py:99-112` — Bug 2 (self-verification via arguments)
- `starter/edinburgh_research/sample_data/catering.json`, `venues.json:haymarket_tap` — fixtures for hand-derived ground truth

---

## Q3 — First production failure and the primitive that surfaces it

> "If you were shipping this agent to a real pub-booking business next week, what's the first production failure you'd expect, and which sovereign-agent primitive (ticket state machine, manifest discipline, IPC atomic rename, SessionQueue retry, etc.) would surface it? One specific primitive, one specific failure mode."

### Your answer

**Primitive: manifest discipline** (every tool call recorded into `_TOOL_CALL_LOG` via `record_tool_call`, with the rubric's −3pt penalty for any tool that bypasses this).
**First production failure mode I'd expect: a real LLM violating the task's HARD RULES because they don't reach the executor.**

Within a week of shipping, real-mode runs would routinely show Qwen3-32B varying `party_size`, retrying `venue_search` with new neighbourhoods, and ignoring budget caps. I observed this directly in `sessions/sess_d15fc62e370f`: 4 consecutive `venue_search` calls with `party_size ∈ {10, 10, 15, 10}` and `near {Edinburgh City Centre, Old Town, Edinburgh, Grassmarket}`, none honouring the prompt's "Do NOT call venue_search more than once. Do NOT change party_size from 6."

The cause is structural. The planner is instructed (`planner/__init__.py:94`) to emit one-sentence subgoal descriptions, and the executor's prompt construction (`executor/__init__.py:225-232`) only forwards `subgoal.description` and `subgoal.success_criterion` — never the original task text. So HARD RULES have nowhere to live in the framework's data flow. In real-mode the planner produced *"Research and compile a list of 3-5 Edinburgh venues with basic details"* — no party size, no neighbourhood, no budget. The LLM's behaviour is then a rational response to a constraint-free subgoal, not a "spiral".

Because every `venue_search` call is recorded in `_TOOL_CALL_LOG`, tools can read their own call history regardless of what the planner emitted. The spiral cap I added at `tools.py:49-64` (`if search_count >= 3: return success=False`) reads `_TOOL_CALL_LOG` and shuts down repeat calls *at the tool layer* — bypassing every constraint-loss point upstream. It's the only enforcement point that reliably runs in production.

The lesson here is that prompt-level rules are largely decorative and not to be relied upon when the framework summarises between layers. Business invariants — deposit caps, party caps, retry budgets — must live inside the tool's Python implementation (i.e. the rule following part of our pipeline). The same architectural principle is why Ex6's structured half exists at all - deterministic rules in Python at a process boundary (`actions.py:119-123`), enforced regardless of LLM behaviour — Rasa is probably overkill for two `if`-statements today but the moment users type free-form or the rule set grows it becomes essential. Without enforcement at one of these layers, no production guarantees survive the planner-executor channel.

### Citation

- `sessions/sess_d15fc62e370f/session.json` — `.planner.subgoals` showing three one-sentence, constraint-free subgoals from real-mode Qwen3-32B (sg_1/sg_2/sg_3, all `assigned_half: "loop"`)
- `sessions/sess_d15fc62e370f/logs/trace.jsonl` — 4 `venue_search` calls with varied parameters; `handoff_to_structured` after exhaustion; no `generate_flyer`
- `starter/edinburgh_research/tools.py:49-64` — the spiral cap reading `_TOOL_CALL_LOG`
- `starter/edinburgh_research/integrity.py` — `_TOOL_CALL_LOG` declaration + `record_tool_call` (the manifest discipline primitive)
- `.venv/lib/python3.12/site-packages/sovereign_agent/planner/__init__.py:94` — one-sentence-description rule
- `.venv/lib/python3.12/site-packages/sovereign_agent/executor/__init__.py:225-232` — executor's prompt construction (no original task threaded through)
- `docs/real-mode-failures.md:51-73` — recommended spiral cap implementation
