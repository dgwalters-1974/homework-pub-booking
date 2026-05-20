# Ex9 — Reflection

## Q1 — Planner handoff decision

> "Find a point in your Ex7 logs where the planner decided to hand off to the structured half. Quote the planner's reasoning or the specific subgoal's `assigned_half` field. What signal caused the decision?"

### Your answer

In my Ex7 run (`sessions/sess_7adc10a30e4c`), the planner did not assign any subgoal to the structured half. The planner ran twice -once per round — and each call produced a single subgoal with `assigned_half: "loop"`. `session.json` only retains the latest planner state, so `.planner.subgoals` shows just the round-2 subgoal (`sg_1`: "retry with larger venue after rejection"); the round-1 subgoal ("find venue near haymarket for 12") is recoverable from `logs/trace.jsonl` via the two `planner.called` / `planner.produced_subgoals` events.

What this tells us is that the loop-to-structured transition wasn't a planner-level decision - it happened one layer down, in the executor. In `logs/trace.jsonl`, after each subgoal's `venue_search` call (this can be seen on lines 5 & 12 of the unformatted `logs/trace.jsonl`), the next `executor.tool_called` event has `payload.tool == "handoff_to_structured"` (e.g. round-1 turn 2 carries `data.venue_id = "Haymarket Tap"`). The bridge then reads `loop_result.next_action == "handoff_to_structured"` (`bridge.py:92`), calls `build_forward_handoff` / `write_handoff` (`bridge.py:103-104`) and emits `session.state_changed` with `from: "loop", to: "structured", round: 1`.

The signal that caused the decision was therefore the existence of a `handoff_to_structured` tool in the executor's tool registry, plus the executor LLM's interpretation of "venue identified" as a state worth committing under policy rules. In our offline run the FakeLLMClient script hardcoded that choice; in a real-LLM run the same conclusion would emerge from the executor system prompt (`executor/__init__.py:58-73`), which explicitly tells the LLM to call `handoff_to_structured` when appropriate.

Looking a bit deeper at this, the planner's `assigned_half` field is just advisory. The meaningful handoff decision comes in the tool layer — whether `handoff_to_structured` exists at all — and emerges from the executor LLM's tool choice. This connects to the planner info-compression issue I documented in Ex5: the planner's outputs are heavily summarised before they reach the executor, so decisions made at the planner level often don't survive intact right the way through the pipeline.

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

The Ex5 offline harness as originally shipped delivers a deliberately fabricated flyer — the FakeLLMClient script in `starter/edinburgh_research/run.py` originally hand-typed `event_details = {"total_gbp": 540, "deposit_required_gbp": 0, ...}`, while `calculate_cost('haymarket_tap', 6, 3, 'bar_snacks')` actually returns `total=556, deposit=111` (independently derivable from `sample_data/catering.json` + `sample_data/venues.json:haymarket_tap`). The committed session `sessions/sess_2f5bd9478e9b/workspace/flyer.html` preserves that fabricated state.

In the original code, `verify_dataflow` reports "OK" anyway because of two bugs in `integrity.py`:

- **Bug 1** (`integrity.py lines 64-68`): the regex `£\d+` requires `£` adjacent to a digit, but `tools.py:353,357` renders its monetary output as nested `<span>£<span data-testid="...">N</span></span>` tags that become `" £ 540 "` after tag-stripping. The details actually never get extracted at all.
- **Bug 2** (`integrity.py line 112`): `fact_appears_in_log` scans both `r.output` AND `r.arguments`, so the LLM's hallucinated values self-verify via `generate_flyer`'s own arguments dict — the artefact-builder is effectively marking its own work.

After applying fixes to both these issues (regex changed to `£\s*\d+(?:\.\d+)?`, drop the `or _scan(r.arguments)` clause) and re-running `make ex5` against the original fabricated FakeLLMClient, the harness exits non-zero with `dataflow FAIL: 1 unverified fact(s): ['£ 540']` — the check caught the fabrication. With the integrity machinery working, I then changed the logic to: update the FakeLLMClient at `run.py:79-95` to use the real tool outputs (`total_gbp=556, deposit_required_gbp=111`), so `make ex5` exits 0 going forward. Manual inspection consistently misses this kind of bug because £540 is a plausible amount — close to the real £556, follows the deposit-policy thresholds in `catering.json`, and renders identically to legitimate values. A human reviewer scanning the rendered flyer will miss this almost every time; the integrity check doesn't.

The lesson here is that integrity checks must verify against tool outputs (i.e. what was produced), never the arguments to tools (which are the LLM's claims). Field-aware matching via the unused `extract_testid_facts` helper at `integrity.py:85-96` would also resolve a third issue I documented ('bare-number' collisions on `0`).

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

**Primitive: manifest discipline** (every tool call recorded into `_TOOL_CALL_LOG` via `record_tool_call`).
**First production failure mode I'd expect: a real LLM violating the task's HARD RULES because they don't reach the executor.**

Within a week of shipping, real-mode runs would routinely show Qwen3-32B varying `party_size`, retrying `venue_search` with new neighbourhoods, and ignoring budget caps. I observed this directly in `sessions/sess_d15fc62e370f`: 4 consecutive `venue_search` calls with `party_size ∈ {10, 10, 15, 10}` and `near {Edinburgh City Centre, Old Town, Edinburgh, Grassmarket}`, none respecting the prompt's "Do NOT call venue_search more than once. Do NOT change party_size from 6."

The cause is structural. The planner is instructed (`planner/__init__.py:94`) to emit one-sentence subgoal descriptions, and the executor's prompt construction (`executor/__init__.py:225-232`) only forwards `subgoal.description` and `subgoal.success_criterion` — never the original task text. So HARD RULES have nowhere to live in the framework's data flow. In real-mode the planner produced "Research and compile a list of 3-5 Edinburgh venues with basic details" — no party size, no neighbourhood, no budget. The LLM's behaviour is then a rational response to a constraint-free subgoal, not a "spiral".

Because every `venue_search` call is recorded in `_TOOL_CALL_LOG`, tools can read their own call history regardless of what the planner emitted. The spiral cap I added at `tools.py:49-64` (`if search_count >= 3: return success=False`) reads `_TOOL_CALL_LOG` and shuts down repeat calls *at the tool layer* — bypassing every constraint loss point upstream. It's the only enforcement point that reliably runs in production.

The lesson here is that prompt-level rules are largely decorative and not to be relied upon when the framework summarises between layers. Business invariants — deposit caps, party caps, retry budgets etc — must live inside the tool's Python implementation (i.e. the rule following part of our pipeline). The same architectural principle is why Ex6's structured half exists at all - deterministic rules in Python at a process boundary (`actions.py:185-200`), enforced regardless of LLM behaviour — Rasa is probably overkill for two `if`-statements today but the moment users type free-form or the rule set grows it becomes essential. Indeed, post-submission I extended the validator with a `policy_profile` lookup (`starter/rasa_half/policies.py`) so the slide-deck scenario (party ≤ 170, vegan_ratio ≤ 0.80) plugs in as data, not code — exactly the "rule set grows" case. Without enforcement at one of these layers, no production guarantees survive the planner-executor channel.

### Citation

- `sessions/sess_d15fc62e370f/session.json` — `.planner.subgoals` showing three one-sentence, constraint-free subgoals from real-mode Qwen3-32B (sg_1/sg_2/sg_3, all `assigned_half: "loop"`)
- `sessions/sess_d15fc62e370f/logs/trace.jsonl` — 4 `venue_search` calls with varied parameters; `handoff_to_structured` after exhaustion; no `generate_flyer`
- `starter/edinburgh_research/tools.py:49-64` — the spiral cap reading `_TOOL_CALL_LOG`
- `starter/edinburgh_research/integrity.py` — `_TOOL_CALL_LOG` declaration + `record_tool_call` (the manifest discipline primitive)
- `.venv/lib/python3.12/site-packages/sovereign_agent/planner/__init__.py:94` — one-sentence-description rule
- `.venv/lib/python3.12/site-packages/sovereign_agent/executor/__init__.py:225-232` — executor's prompt construction (no original task threaded through)
- `docs/real-mode-failures.md:51-73` — recommended spiral cap implementation

---

## Added later (2026-05-19) — slide-version of this project had different questions Q1–Q3

The lecture slides circulated a slightly different Q1–Q3 set after I'd written the answers above. Rather than rewrite, I've added the slide versions here. Each ≥100 words, grounded in specific sessions.

### Slide Q1 — Which of yesterday's eight failure modes did you hit in your own build?

> "Which of yesterday's eight failure modes did you hit in your own build? Reference the specific ticket IDs / trace lines."

Three of the eight catalogued in `docs/real-mode-failures.md`. Summary:

| # | Mode | Hit | Evidence |
|---|---|:---:|---|
| 1 | Ex5 — Qwen3-32B spiral on `venue_search` | ✓ | `sessions/sess_d15fc62e370f` — 4 `venue_search` calls with `party_size ∈ {10,10,15,10}`, varied neighbourhoods, no `generate_flyer`. Fix shipped: tool-layer spiral cap at `starter/edinburgh_research/tools.py:49-64` reading `_TOOL_CALL_LOG`. |
| 2 | Ex6 — `action_validate_booking` internal_error | ✗ | code path not exercised |
| 3 | Ex6 — Embeddings 401 | ✗ | not exercised |
| 4 | Ex7 — Loop half uses FakeLLMClient in `--real` | ✓ | `starter/handoff_bridge/run.py:139-141` — `--real` only swaps the structured half; every Ex7 session shows `"model": "fake"` in ticket manifests. |
| 5 | Ex7 — FakeLLMClient response exhaustion | ✗ | scripts extended sufficiently |
| 6 | Ex8 — Speechmatics 401 / 403 | ✓ | `sessions/sess_d4485cc821a5/` — graceful-degradation path; absence of `trace.jsonl` is the load-bearing evidence (refuses to silently proceed with broken auth). |
| 7 | Ex8 — Rime TTS 400 | ✗ | voice path not exercised at that stage |
| 8 | Ex8 — macOS mic / audio | ✗ | local env didn't trigger |

The three hits share a pattern: each is a place where a *deterministic guarantee* (planner subgoal completeness, real-LLM coverage, credential availability) silently degrades to a weaker one. The fix in each case is to make the degradation explicit and fail-loud rather than fail-silent — see Q3 above for the deeper architectural treatment of the planner-subgoal-compression cause behind #1.

### Slide Q2 — Did the dataflow integrity check catch any silent failures?

> "The dataflow integrity check — did it catch any silent failures in your scenario? If yes, describe the failure and the fix. If no, construct a planted failure (edit a tool to return a fabricated value) and show the check catching it."

**Yes — caught a planted fabrication wired into the offline scaffold itself.** As originally shipped, the FakeLLMClient at `starter/edinburgh_research/run.py:79-95` hand-typed `event_details={"total_gbp": 540, "deposit_required_gbp": 0, ...}` while the real `calculate_cost('haymarket_tap', 6, 3, 'bar_snacks')` (derivable from `sample_data/catering.json` + `venues.json:haymarket_tap`) returns `total=556, deposit=111`. That is the planted fabrication.

When I first ran `make ex5` the check reported "OK" — a silent failure of the silent-failure detector. Two bugs in `starter/edinburgh_research/integrity.py`: (a) the regex `£\d+` required `£` adjacent to a digit, but tag-stripping `<span>£<span>540</span></span>` produces `"£ 540"` with whitespace; (b) `fact_appears_in_log` scanned both `r.output` and `r.arguments`, so the LLM's hallucinated values self-verified via `generate_flyer`'s own argument dict.

Three fixes shipped in order: (1) widen the regex to `£\s*\d+(?:\.\d+)?` (`integrity.py:69`); (2) drop the `_scan(r.arguments)` clause (`integrity.py:115`); (3) update the FakeLLMClient `event_details` to use real tool outputs so `make ex5` exits 0 going forward. With (1) and (2) in place, re-running against the original fabricated client first exited non-zero with `dataflow FAIL: 1 unverified fact(s): ['£ 540']` — the check caught the planted failure. The committed session `sessions/sess_2f5bd9478e9b/workspace/flyer.html` preserves the original fabricated state for inspection; the same session's `logs/tickets/*/state.json` all show `"state": "success"`, which is precisely why the integrity check matters — every other primitive said the run succeeded. The check is the only thing that disagreed.

### Slide Q3 — If you had to reduce the homework to three exercises, which would you keep?

> "If you had to reduce the homework to three exercises, which would you keep? Honest feedback. No wrong answer; we grade on the quality of your reasoning."

**Keep: Ex5, Ex6, Ex7. Cut: Ex8.** (Ex9 is reflection, not an "exercise" in this sense.)

**Ex5 (loop half + dataflow integrity)** This is the main body of the homework - it highlights the planner-executor loop and its information loss, shows how the LLM treats a real model and makes us aware of the data integrity issues and how verifying against tool outputs is priceless.

**Ex6 (structured half + Rasa)** This example shows us what the pipeline does well - deterministic rules (written in Python) at the boundary irrespective of LLM behaviour. Using Rasa for our needs is probably a little bit over the top, but it highlights how LLM only architecture would cause problems (and likely not work) in practice.

**Ex7 (the bridge)** is what connects Ex5 and Ex6. Without it the two halves are separate demos that never talk to each other. Ex7 teaches what happens when they do: the loop half proposes a booking, the structured half can reject it ("party too big"), the loop half tries again with different parameters, and the whole exchange stops after a fixed number of rounds so it can't loop forever. Every step is recorded in the trace so any bugs can be followed through the workflow.



**Cut Ex8 (voice pipeline)** because STT and TTS are I/O adapters around whatever LLM call sits behind them — no unique *agent* concept. The manager-persona work is a vanilla executor pattern Ex5 already covers. The only genuinely new lesson — graceful degradation under missing credentials — is generic (same pattern applies to Nebius key, Rasa license, etc.). Ex8's install/credential friction is also the largest dropout point in the course; removing it is a useful gain for marginal pedagogical loss.
