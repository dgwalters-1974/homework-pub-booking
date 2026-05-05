# Ex9 — Reflection

## Q1 — Planner handoff decision

### Your answer

In my Ex7 run (`sessions/sess_7adc10a30e4c`), the planner did **not** assign any subgoal to the structured half. Both subgoals from `session.json:planner.subgoals` came back with `assigned_half: "loop"`:

- `sg_1`: "find venue near haymarket for 12" — `assigned_half: "loop"`
- `sg_1` (round 2): "retry with larger venue after rejection" — `assigned_half: "loop"`

So the loop→structured transition wasn't a planner-level decision; it happened one layer down, at the executor's tool-call boundary. In `logs/trace.jsonl`, after each subgoal's `venue_search` call, the next `executor.tool_called` event has `payload.tool == "handoff_to_structured"` (e.g. round-1 turn 2 carries `data.venue_id = "Haymarket Tap"`). The bridge then reads `loop_result.next_action == "handoff_to_structured"` (`bridge.py:103`) and POSTs to Rasa, emitting `session.state_changed` with `from: "loop", to: "structured", round: 1`.

The signal that caused the decision was therefore the existence of a `handoff_to_structured` tool in the executor's tool registry, plus the executor LLM's interpretation of "venue identified" as a state worth committing under policy rules. In our offline run the FakeLLMClient script hardcoded that choice; in a real-LLM run the same conclusion would emerge from the executor system prompt (`executor/__init__.py:58-73`), which explicitly tells the LLM to call `handoff_to_structured` for high-stakes actions.

The deeper observation: in this codebase, the planner's `assigned_half` field is **advisory**, not load-bearing. The architecturally meaningful handoff decision is encoded in the tool layer — whether `handoff_to_structured` exists at all — and emerges from the executor LLM's tool choice. This connects to the planner-compression issue I documented in Ex5: the planner's outputs are heavily summarised before they reach the executor, so structural decisions made at the planner level often don't survive to runtime.

### Citation

- `sessions/sess_7adc10a30e4c/session.json` — `.planner.subgoals` showing both subgoals with `assigned_half: "loop"`
- `sessions/sess_7adc10a30e4c/logs/trace.jsonl` — `executor.tool_called` events for `handoff_to_structured` in both rounds; `session.state_changed` events showing the actual transitions
- `starter/handoff_bridge/bridge.py:103` — bridge reads `loop_result.next_action`
- `.venv/lib/python3.12/site-packages/sovereign_agent/executor/__init__.py:58-73` — executor system prompt encouraging `handoff_to_structured` for high-stakes actions
- `.venv/lib/python3.12/site-packages/sovereign_agent/planner/__init__.py:94-101` — planner instructed to set `assigned_half` per subgoal

---

## Q2 — Dataflow integrity catch

### Your answer

The Ex5 offline harness (`make ex5`, session `sessions/sess_2f5bd9478e9b`) ships a deliberately-fabricated flyer: the FakeLLMClient script in `starter/edinburgh_research/run.py:79-95` hand-types `event_details = {"total_gbp": 540, "deposit_required_gbp": 0, ...}`, while `calculate_cost('haymarket_tap', 6, 3, 'bar_snacks')` actually returns `total=556, deposit=111` (independently derivable from `sample_data/catering.json` + `sample_data/venues.json:haymarket_tap`).

As shipped, `verify_dataflow` reports "OK" anyway because of two bugs in `integrity.py`:

- **Bug 1** (`integrity.py:64-68`): the regex `£\d+` requires `£` adjacent to a digit, but `tools.py:336-340` renders money as nested `<span>` tags that become `" £ 540 "` after tag-stripping. Money facts never get extracted at all.
- **Bug 2** (`integrity.py:112`): `fact_appears_in_log` scans both `r.output` AND `r.arguments`, so the LLM's hallucinated values self-verify via `generate_flyer`'s own arguments dict — the artefact-builder grading its own work.

After applying both fixes (regex `£\s*\d+(?:\.\d+)?`, drop the `or _scan(r.arguments)` clause), `make ex5` exits non-zero with `dataflow FAIL: 1 unverified fact(s): ['£ 540']`. Manual inspection consistently misses this because £540 is plausible — close to the real £556, follows the deposit-policy thresholds in `catering.json`, and renders identically to legitimate values. A human reviewer scanning the rendered flyer sees no red flags.

The scenario is fully reproducible by anyone: clone the repo, apply the two-line fix, run `make ex5`. The deeper lesson — also visible in this run — is that integrity checks must verify against tool **outputs** (what was *produced*), never the **arguments** to consumer tools (which are the LLM's claims). Field-aware matching via the unused `extract_testid_facts` helper at `integrity.py:85-96` would also resolve a third issue I documented (bare-number collisions on `0`).

### Citation

- `sessions/sess_2f5bd9478e9b/workspace/flyer.html` — the fabricated flyer with `total_gbp=540`, `deposit_required_gbp=0`
- `sessions/sess_2f5bd9478e9b/session.json` — completed run state; tickets `tk_844e0ff0`, `tk_c5b0dbbb`, `tk_f84530ed` all "success" despite the fabrication
- `starter/edinburgh_research/run.py:79-95` — hand-typed `event_details` (the fabrication source)
- `starter/edinburgh_research/integrity.py:64-68` — Bug 1 (regex blind to whitespace)
- `starter/edinburgh_research/integrity.py:99-112` — Bug 2 (self-verification via arguments)
- `starter/edinburgh_research/sample_data/catering.json`, `venues.json:haymarket_tap` — fixtures for hand-derived ground truth

---

## Q3 — Removing one framework primitive

### Your answer

**Primitive: manifest discipline** (every tool call recorded into `_TOOL_CALL_LOG` via `record_tool_call`, with the rubric's −3pt penalty for any tool that bypasses this).
**First production failure mode I'd expect: a real LLM violating the task's HARD RULES because they don't reach the executor.**

Within a week of shipping, real-mode runs would routinely show Qwen3-32B varying `party_size`, retrying `venue_search` with new neighbourhoods, and ignoring budget caps. I observed this directly in `sessions/sess_d15fc62e370f`: 4 consecutive `venue_search` calls with `party_size ∈ {10, 10, 15, 10}` and `near ∈ {Edinburgh City Centre, Old Town, Edinburgh, Grassmarket}`, none honouring the prompt's "Do NOT call venue_search more than once. Do NOT change party_size from 6."

The cause is structural. The planner is instructed (`planner/__init__.py:94`) to emit one-sentence subgoal descriptions, and the executor's prompt construction (`executor/__init__.py:225-232`) only forwards `subgoal.description` and `subgoal.success_criterion` — never the original task text. So HARD RULES have nowhere to live in the framework's data flow. In real-mode the planner produced *"Research and compile a list of 3-5 Edinburgh venues with basic details"* — no party size, no neighbourhood, no budget. The LLM's behaviour is then a rational response to a constraint-free subgoal, not a "spiral".

Manifest discipline surfaces this. Because every `venue_search` call is recorded in `_TOOL_CALL_LOG`, tools can read their own call history regardless of what the planner emitted. The spiral cap I added at `tools.py:49-64` (`if search_count >= 3: return success=False`) reads `_TOOL_CALL_LOG` and shuts down repeat calls *at the tool layer* — bypassing every constraint-loss point upstream. It's the only enforcement point that reliably runs in production.

The lesson: prompt-level rules are decorative when the framework summarises between layers. Business invariants — deposit caps, party caps, retry budgets — must live inside the tool's Python implementation, gated on observable runtime state captured by manifest discipline. Without it, no production guarantees survive the planner→executor channel.

### Citation

- `sessions/sess_d15fc62e370f/session.json` — `.planner.subgoals` showing constraint-free three-line subgoals from real-mode Qwen3-32B
- `sessions/sess_d15fc62e370f/logs/trace.jsonl` — 4 `venue_search` calls with varied parameters; `handoff_to_structured` after exhaustion; no `generate_flyer`
- `starter/edinburgh_research/tools.py:49-64` — the spiral cap reading `_TOOL_CALL_LOG`
- `starter/edinburgh_research/integrity.py` — `_TOOL_CALL_LOG` declaration + `record_tool_call` (the manifest discipline primitive)
- `.venv/lib/python3.12/site-packages/sovereign_agent/planner/__init__.py:94` — one-sentence-description rule
- `.venv/lib/python3.12/site-packages/sovereign_agent/executor/__init__.py:225-232` — executor's prompt construction (no original task threaded through)
- `docs/real-mode-failures.md:51-73` — recommended spiral cap implementation
