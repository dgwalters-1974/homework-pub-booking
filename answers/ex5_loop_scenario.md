# Ex5 — Edinburgh research loop scenario

## Your answer

For the 'offline' tests ('make ex5'), I set persist=True in example_sessions_dir, and so we can see from the terminal output (`sessions/sess_2f5bd9478e9b/`) that the planner ran and suggested two subgoals which were then performed by the executor - (1) research a venue (research venues near Haymarket for a party of 6), calculate cost and get weather and (2) make a flyer for the venue with the appropriate details (produce an HTML flyer with the chosen venue, weather, and cost)) and complete the task. Both were completed: tickets tk_844e0ff0 (planner.plan), tk_f84530ed (sg_1), tk_c5b0dbbb (sg_2).

But there is a discrepancy between the flyer and the tool outputs when i run 'make ex5'. The flyer claimed Total £540 / Deposit £0 but the actual return from calculate_cost('haymarket_tap', 6, 3, 'bar_snacks') is £556 / £111. The 540 / 0 is from the fake LLM inputs. I think this is an issue with the verify_dataflow function since tool outputs don't match the flyer and yet it still passes the integrity check. PROBLEM!

It looks like there are actually two problems here. I think the regex doesn't pick up the '540' from the html because there's a space between the '£' and the number. This causes ex5 (fake LLM) to pass even though the 540!=556. But also in integrity.py fact_appears_in_log finds the 540 in the generate_flyers own contribution to the log so it will miss any discrepancy regardless. Not sure whether to re-write the integrity check or whether this might cause problems going forward...

```
=== Dataflow integrity check ===
✓  dataflow OK: verified 2 fact(s) against tool outputs
   Verified 2 fact(s) against tool outputs.
```

We can check that the payload fed to generate_flyer (flyer_call) matches the result of our calculation which is performed on the LLM return:
Tool outputs:

```
{
  "near": "Haymarket",
  "party_size": 6,
  "results": [
    {
      "id": "haymarket_tap",
      "name": "Haymarket Tap",
      "area": "Haymarket",
      "address": "12 Dalry Rd, Edinburgh EH11 2BG",
      "open_now": true,
      "seats_available_evening": 8,
      "hire_fee_gbp": 0,
      "min_spend_gbp": 200,
      "manager_email": "haymarket-tap@example.invalid",
      "licensed_hours": "11:00-00:30",
      "accepts_card": true,
      "outdoor_space": false
    }
  ],
  "count": 1
}
{
  "city": "edinburgh",
  "date": "2026-04-25",
  "condition": "cloudy",
  "temperature_c": 12,
  "precip_mm": 0.0,
  "wind_kph": 15
}
{
  "venue_id": "haymarket_tap",
  "party_size": 6,
  "duration_hours": 3,
  "catering_tier": "bar_snacks",
  "subtotal_gbp": 324,
  "service_gbp": 32,
  "total_gbp": 556,
  "deposit_required_gbp": 111
}
```

The £556 / £111 returned by `calculate_cost` can be independently hand-derived from the fixtures, confirming this is the genuine ground truth (not a black-box claim):

| Step | Calculation | Value |
|---|---|---|
| subtotal | `int(18 × 1.0 × 6 × 3)` (rate × modifier × party × hours) | 324 |
| service | `int(324 × 10/100)` | 32 |
| total | `int(324 + 32 + 0 + 200)` (subtotal + service + hire_fee + min_spend) | **556** |
| deposit policy | `300 ≤ 556 < 1001` → `deposit_20_percent` | — |
| deposit | `int(556 × 0.20)` | **111** |

(Sources: `sample_data/catering.json` for the rates and policy; `sample_data/venues.json:haymarket_tap` for `hire_fee_gbp=0` and `min_spend_gbp=200`.)

Flyer:
```
venue_name="Haymarket Tap", venue_address="12 Dalry Rd, Edinburgh EH11 2BG", date="2026-04-25", time="19:30", party_size=6,                              
condition="cloudy", temperature_c=12,  
total_gbp=540, deposit_required_gbp=0            
```
Or we get the following output (courtesy of w3m):

```
Booking at Haymarket Tap

12 Dalry Rd, Edinburgh EH11 2BG

Event

Date2026-04-25
Time19:30
Party size6

Weather

cloudy 12°C

Cost

Deposit due now £0
Total £540
```
So it's clear we get a 'clean' run with the fake LLM (ex5) even though these details don't match - in the real world we need to catch this kind of behaviour so the codebase needs to be amended. I made the following changes:

1. I changed the regex below to enable matching when there's a space between '£' and the number. Effect is that there are now 4 items extracted from the flyer, not 2 as before.
```
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def extract_money_facts(text: str) -> list[str]:
    """Find all £<number> occurrences, HTML tags stripped or not."""
    # Strip HTML tags first so e.g. <dd>£540</dd> matches cleanly.
    stripped = re.sub(r"<[^>]+>", " ", text)
    return re.findall(r"£\s*\d+(?:\.\d+)?", stripped) # added \s* to allow for leading/trailing whitespace

```
2. I changed the scan to only scan the output from the tools and compare to the flyer

```
def fact_appears_in_log(fact: Any, log: list[ToolCallRecord] | None = None) -> bool:
    records = log if log is not None else _TOOL_CALL_LOG
    target = str(fact).lower().strip("£°c ")

    def _scan(obj: Any) -> bool:
        if isinstance(obj, (str, int, float)):
            return str(obj).lower().strip("£°c ") == target
        if isinstance(obj, dict):
            return any(_scan(v) for v in obj.values())
        if isinstance(obj, (list, tuple, set)):
            return any(_scan(v) for v in obj)
        return False

    #return any(_scan(r.output) or _scan(r.arguments) for r in records) # original (bug2)
    return any(_scan(r.output) for r in records) # outputs only
```

```
dgwalters@boomer homework-pub-booking % make ex5
Session sess_2f5bd9478e9b
dir: /Users/dgwalters/Library/Application Support/sovereign-agent/examples/ex5-edinburgh-research/sess_2f5bd9478e9b
LLM: FakeLLMClient (offline, scripted)

Loop half outcome: complete
summary: loop half completed 2 subgoal(s); final answer: Booking researched; flyer at workspace/flyer.html.

Tickets:
  tk_844e0ff0  planner.plan                                        success
  tk_c5b0dbbb  executor.run_subgoal/sg_2                           success
  tk_f84530ed  executor.run_subgoal/sg_1                           success

=== flyer.html (1731 bytes) ===
<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Haymarket Tap — 2026-04-25</title>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; max-width: 640px;
          margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
  h1 { font-size: 2rem; margin-bottom: 0.25rem; }
  .meta { color: #555; margin-bottom: 1.5rem; }
  .card { border: 1px solid #e5e5e5; border-radius: 8px;
           padding: 1rem 1.25rem; margin-bottom: 1rem; }
  .card h2 { margin-top: 0; font-si...
[truncated]

=== Dataflow integrity check ===
✗  dataflow FAIL: 1 unverified fact(s): ['£ 540']
   Unverified facts: ['£ 540']
make: *** [ex5] Error 2
```
However the £0 / £111 discrepancy still slips through. This is a third issue I hadn't initially spotted: 'fact_appears_in_log' strips units from each fact (`integrity.py:101` — `target = str(fact).lower().strip("£°c ")`) and then matches the bare number against any scalar anywhere in any tool output. So when the flyer's `deposit_required_gbp=0` is checked against the log, it matches with `hire_fee_gbp=0` from `calculate_cost`'s output and the check returns "verified" — even though the two zeros are unrelated facts about different fields.

The fix would be to verify *typed* facts: the flyer renders every value inside a `<span data-testid="...">` (see `tools.py:336-340`), and there is already an `extract_testid_facts` helper at `integrity.py:85-96` that returns a `{testid: value}` dict. Wiring this in - along with a matching change to `fact_appears_in_log` so it only matches a flyer fact against tool-output values from the *same field name* would catch `deposit_required_gbp=0` because no `calculate_cost` output has `deposit_required_gbp=0` (it returns 111). I have not made this (bigger) change due to risk of breaking the existing codebase and lack of time.



# Why the integrity check matters: planner-to-executor data compression

There's an upstream issue that justifies why the integrity check exists at all. Inspecting `session.json:planner.subgoals` from the persisted session, the planner's two subgoals are:

- `sg_1.description = "research Edinburgh venues near Haymarket for a party of 6"`
- `sg_2.description = "produce an HTML flyer with the chosen venue, weather, and cost"`

If we compare these to the original task string at `run.py:201-220`, which contains explicit HARD RULES — 
"REQUIRED tool sequence (all four tools MUST run, in order)", 
"Do NOT call venue_search more than once", 
"Do NOT change party_size from 6", 
and exact tool argument shapes. 

None of those constraints survive into the executor's prompt. 

In offline mode this doesn't change behaviour because `FakeLLMClient` runs scripted responses regardless of prompt. In real mode (`make ex5-real`), this is the documented root cause of the Qwen3-32B `venue_search` spiral described in `docs/real-mode-failures.md:15-83`.

(It's important to remember that Qwen3-32B is an instruct model not a reasoning one so when it gets a negative result e.g. 0 search results, it doesn't 'reason' why, it just tries something else in an 'pattern matching' manner.)

**Confirmed in real mode (session `sess_d15fc62e370f`).** A `make ex5-real` run produced *three* subgoals — and dropped *more* constraints than offline did:

- `sg_1`: "Research and compile a list of 3-5 Edinburgh venues with basic details"
- `sg_2`: "Gather detailed information about the top venue including amenities and contact details"
- `sg_3`: "Create a promotional flyer using the selected venue's details"

Even "Haymarket" and "party of 6" — which the offline subgoals had retained — are gone. The downstream `venue_search` calls captured in `logs/trace.jsonl` (`party_size` {10, 10, 15, 10}, `near` {Edinburgh City Centre, Old Town, Edinburgh, Grassmarket}, `budget_max_gbp` {150, 300, 500, 1000}) are not a 'spiral' in the sense of a misbehaving LLM ignoring rules — they're a rational response to a constraint-free subgoal. The original task's HARD RULES (party=6, near=Haymarket, budget=800, four-tool sequence) never reached the executor's prompt at all. After 4 zero-result calls, the agent escalated to the structured half via `handoff_to_structured`; no `generate_flyer` call ever ran, and the integrity check therefore never fired.

This compression is structural in the way the system is designed - the planner gives out 1 sentence descriptions and so the executor prompt construction never sees all the available data.

This reframes the integrity check's role. It's not a sanity check on a well-instructed LLM; it's the **last line of defence** for an LLM that was never told the rules.

It also reframes the spiral cap inside `venue_search` recommended at `docs/real-mode-failures.md:51-73`. The doc describes that cap as "defense-in-depth: the task prompt is the first line, the tool itself is the second". Given the compression observation, the first line is in fact empty — the tool-level cap is the *only* runtime constraint that reaches an executor LLM. I have implemented the cap in `tools.py:venue_search` (lines 49-64): after 3 prior `venue_search` entries in `_TOOL_CALL_LOG`, the tool returns `success=False` with `output={"error": "too_many_searches", "count": <n>}` and a `STOP calling venue_search; use the results you already have.` summary. This is the only mechanism that would have stopped the real-mode Qwen run from progressing past 4 consecutive zero-result calls — and it does so via data the tool *can* see (the prior call log), bypassing the planner-compression problem entirely.

### Bug 4 — framework drops the rich task before the planner sees it

While building Task C I traced the prompt path more carefully and found that the framing above (planner *compresses* the task) is slightly understated. The rich task string passed to `create_session(task=...)` at `run.py:201-220` is written to `sessions/sess_*/SESSION.md` under a heading that says verbatim *"The loop half reads this file on every turn."* — but it isn't read. `LoopHalf.run` at `halves/loop.py:51` reads `input_payload.get("task")` and **only that**; grepping the sovereign-agent package for any read of `session.task` or `SESSION.md` content returns zero hits, and `session.json` doesn't even persist the task field. The string that actually reaches the planner is therefore the bare one-liner `"research Edinburgh venue and write flyer"` from `run.py:250` — i.e. `half.run(session, {"task": "research Edinburgh venue and write flyer"})`. So the constraints aren't being compressed by the planner; they're being **dropped by the framework before the planner is ever invoked**. That changes the diagnosis: the scenario author *did* try to give the planner the rules, and put them in the slot the framework's own SESSION.md template advertises as load-bearing. The advertising is wrong. This is a documentation-vs-implementation drift in `sovereign-agent` itself, not a scenario bug — and it's worth flagging to the educator since it materially affects what every student's Ex5 real-mode run will look like.

## Citations

### Session artefacts (offline run, `make ex5`)

- `sessions/sess_2f5bd9478e9b/session.json` — `.planner.subgoals` shows the compressed two-line subgoal descriptions
- `sessions/sess_2f5bd9478e9b/logs/trace.jsonl` — chronological event log; `event_type` values include `planner.called`, `planner.produced_subgoals`, `executor.tool_called`
- `sessions/sess_2f5bd9478e9b/workspace/flyer.html` — the produced flyer with `total_gbp=540`, `deposit_required_gbp=0`
- Tickets: `tk_844e0ff0` (planner.plan), `tk_c5b0dbbb` (executor sg_2), `tk_f84530ed` (executor sg_1) — all "success"

### Session artefacts (real-mode run, `make ex5-real`)

- `sessions/sess_d15fc62e370f/session.json` — three subgoals with no surviving constraints (worse compression than offline)
- `sessions/sess_d15fc62e370f/logs/trace.jsonl` — 4 `venue_search` calls (varied `near` / `party_size` / `budget`), then `handoff_to_structured`; no `generate_flyer` call and the integrity check never fired
- `sessions/sess_d15fc62e370f/workspace/flyer.html` — does not exist; the run aborted before flyer creation

### Source code

- `starter/edinburgh_research/run.py:79-95` — hand-typed `event_details` in the FakeLLMClient script (the deliberate fabrication: `total_gbp=540`, `deposit_required_gbp=0`)
- `starter/edinburgh_research/run.py:201-220` — the original task string with HARD RULES that don't survive planner compression
- `starter/edinburgh_research/integrity.py:64-68` — `extract_money_facts` regex (Bug 1)
- `starter/edinburgh_research/integrity.py:85-96` — unused `extract_testid_facts` helper (would fix Bug 3)
- `starter/edinburgh_research/integrity.py:99-112` — `fact_appears_in_log` (Bug 2 at line 112; Bug 3 root at line 101)
- `starter/edinburgh_research/tools.py:33-78` — `venue_search`, currently has no spiral cap
- `starter/edinburgh_research/tools.py:336-340` — nested-span money rendering that triggers Bug 1
- `starter/edinburgh_research/tools.py:356` — `record_tool_call` for `generate_flyer` (the line that feeds the LLM's own claims into the verification log)

### Fixtures (ground-truth derivation)

- `starter/edinburgh_research/sample_data/catering.json` — base rates, venue modifiers, service charge, deposit policy thresholds
- `starter/edinburgh_research/sample_data/venues.json:haymarket_tap` — `hire_fee_gbp=0`, `min_spend_gbp=200`
- `starter/edinburgh_research/sample_data/weather.json` — `edinburgh / 2026-04-25 → cloudy, 12°C`

### Documentation

- `docs/real-mode-failures.md:15-83` — Qwen3-32B `venue_search` spiral in real mode
- `docs/real-mode-failures.md:51-73` — recommended spiral-cap implementation
- `docs/grading-rubric.md:34-36` — Ex5 behavioural rubric items
- `ASSIGNMENT.md:79` — "verify_dataflow catches planted fabrication" (6 pts)

---

## Task C — Three-model comparison (addendum, added 2026-05-18)

> The original answer above covers Task A (scenario implementation) and Task B (dataflow integrity). This addendum covers Task C — the three-model comparison — which was clarified to me late in the cycle. The original Task A/B prose is unchanged.

### Method

Three planner/executor combinations run 3× each (9 sessions total), holding the scenario task constant (`research Edinburgh venue and write flyer`). The runner is `scripts/ex5_compare_run.py` (Make targets `ex5-compare-combo{1,2,3}` / `ex5-compare-all`). Each session lands in `sessions/sess_<id>/` with a marker file `extras/combo.txt` recording the combo name, the two model IDs, wall-clock seconds and exit code. Analysis is generated by `scripts/ex5_model_compare.py` (Make target `ex5-compare-analysis`); raw per-run data lives in `answers/ex5_task_c_data.md`.

**Important**: the spiral cap I added in Task A (`tools.py:49-64`) was left in place for all runs — it changes the failure *signature* but not the underlying success rate, and removing it would have given Qwen3-32B an unbounded budget that none of the other combos enjoy. Comparing with the cap on is the fairer apples-to-apples test.

### Headline result

| Combo | Planner / Executor | Runs | Success | Mean wall-clock | Mean tokens in/out | Mean tool calls | Spiral-capped |
|---|---|---|---|---|---|---|---|
| 1 | Qwen3-Next-80B-Thinking / Qwen3-235B-Instruct | 3 | **0/3** | 31.2s | 262 / 3,017 | 4.7 | 2/3 |
| 2 | MiniMax-M2.5 / Qwen3-235B-Instruct | 3 | **0/3** | 30.1s | 261 / 253 | 6.7 | 2/3 |
| 3 | Qwen3-32B / Qwen3-32B | 3 | **0/3** | 66.8s | 260 / 625 | 2.3 | 0/3 |

**Zero combos produced a flyer.** Every run terminated via `handoff_to_structured` instead.

### Why nothing succeeded — same root cause as Q3, sharper

The shared failure mode is the constraint-loss issue documented in this exercise's Bug 4 and re-examined in Ex9 Q3. The string the planner actually receives is the bare one-liner `"research Edinburgh venue and write flyer"` from `run.py:250` — the rich `create_session(task=...)` block at `run.py:201-220` is written to `SESSION.md` and dropped by the framework before the planner sees it (Bug 4). Every executor (Qwen3-235B, Qwen3-32B) then hallucinates a `party_size` — **50** in most runs, **10** in some — which doesn't match any venue in `sample_data/venues.json` (the fixture caps at 8). All venue_search calls return 0 results; the executor either spirals until the cap fires (combos 1, 2) or surrenders quickly (combo 3). The handoff-to-structured at the end is rational behaviour from a constraint-starved executor.

This finding **confirms rather than contradicts** the Q3 analysis: the constraint-loss is model-agnostic. Switching to a larger executor doesn't fix it; switching planners doesn't fix it. No combo of the three could have succeeded, because none of them were given the rules.

### Per-combo failure signatures (the interesting bit)

Even though success rate is identical, the combos fail very differently:

**Combo 1 — Qwen3-Next-80B-Thinking + Qwen3-235B-Instruct.** Highest-spend failure: ~3,000 output tokens/run, almost all from the thinking-planner's reasoning trace. Executor (235B) is the model most willing to retry venue_search with varied parameters — spiral-capped on 2 of 3 runs. Sessions: `sess_e11860274d75`, `sess_be1d30d58399`, `sess_ac1ebfaa3d20`.

**Combo 2 — MiniMax-M2.5 + Qwen3-235B-Instruct.** Cheapest failure: ~250 output tokens/run, an **order of magnitude less** than combo 1 despite the same executor. MiniMax is more concise as a planner, so the executor receives shorter context and emits shorter reasoning per turn — but does more tool turns (6.7 mean vs combo 1's 4.7). Spiral-capped on 2 of 3 runs. Sessions: `sess_e52af16804e0`, `sess_09c06c5b90d8`, `sess_917eaa9a4337`.

**Combo 3 — Qwen3-32B alone.** Slowest failure: 66.8s mean (over 2× the others) but only 2.3 tool calls per run — the small model takes longer to decide each turn and gives up quickly. One run (`sess_b02cad67463d`) made **zero tool calls** before handing off. Never trips the spiral cap. Sessions: `sess_5365f9a91b87`, `sess_b02cad67463d`, `sess_61d26231d8eb`.

### Which is best for this scenario?

For *this* scenario as-written, **none of them** — but if forced to pick, **combo 2 (MiniMax + 235B)** has the cleanest cost profile: it fails fast and cheap (~30s, ~515 total tokens). Combo 1 burns 6× the tokens for the same outcome. Combo 3 is slowest and least informative (the model isn't capable enough to even spiral correctly).

The honest takeaway, though, is that **comparing models on a task with a structural defect (planner compression) is the wrong comparison**. The right next experiment would be to enrich the task or the subgoal description so the executor sees the real constraints, then re-run — which is exactly what the control experiment below does.

### Control experiment — does rich input change anything?

The bare-input rounds above all suffer from Bug 4: the framework drops the rich `create_session(task=...)` string before the planner sees it, leaving the planner with only the one-liner *"research Edinburgh venue and write flyer"*. To isolate Bug 4 from any other model-level effect, I added an `EX5_RICH_TASK` env-var hook (`run.py:250-258`) that swaps the bare one-liner for the rich task string when set, and re-ran each combo **once** via `scripts/ex5_compare_run.py --rich`. Combo marker is tagged `<combo>-rich` so the analysis tool groups them as separate buckets.

| Combo | Input | Runs | Planner subgoals | Mean tokens out | Mean tool calls | Spiral-capped | `party_size` arg used |
|---|---|---|---|---|---|---|---|
| 1 | bare | 3 | 3 (vague) | 3,017 | 4.7 | 2/3 | hallucinated 10/50 |
| 1 | **rich** | 1 | **5 (1:1 with required sequence)** | 5,098 | **12** | **0/1** | **correct = 6** |
| 2 | bare | 3 | 3 (vague) | 253 | 6.7 | 2/3 | hallucinated 10/50 |
| 2 | **rich** | 1 | **5 (1:1)** | 855 | 6 | **0/1** | **correct = 6** |
| 3 | bare | 3 | 3 (vague) | 625 | 2.3 | 0/3 | hallucinated 10/50 |
| 3 | **rich** | 1 | — (planner crashed) | 0 | 0 | 0/1 | — |

Three findings, in order of importance:

**1. Bug 4 is behaviourally confirmed.** With rich input, combos 1 and 2 produce **5 well-formed subgoals that map 1:1 to the required tool sequence** (`sg_1`: "Search for pubs near Haymarket station accommodating 6 people within a £800 budget"; `sg_2`: weather; `sg_3`: cost; `sg_4`: flyer; `sg_5`: complete) and call `venue_search` with the *exact* prompt-specified arguments (`near='Haymarket station', party_size=6, budget_max_gbp=800`). No combo hallucinates `party_size` any more. Neither combo trips the spiral cap. **Conclusion: the framework was eating the constraints, not the planner.** Sessions: `sess_bbd6694560d0` (combo 1 rich), `sess_0b39c226a8d2` (combo 2 rich).

**2. A second, smaller bug shows up.** Even with a 1:1 plan, neither combo executes all 5 subgoals to completion — combo 1 made 12 tool calls without reaching `generate_flyer`; combo 2 made 6 calls and gave up. So Bug 4 isn't the only thing broken — there's a *separate* executor-side issue (probably max-turns or context limits) that the rich-task fix exposes but doesn't solve. This is the right kind of progress: one bug at a time.

**3. Qwen3-32B can't handle rich input as a planner.** Combo 3 rich crashed with `SA_VAL_INVALID_PLANNER_OUTPUT` — the model emitted invalid JSON for the subgoal schema (`sess_8796fd54ec73`). With bare input it returned valid JSON every time (3/3). This is exactly the kind of small-model-as-planner failure the original Task C "too-small control" was meant to expose, just in a different shape than expected: not slow-and-incoherent, but *unable to format under load*.

**Revised answer to "which is best for this scenario?"**: combo 1 (Qwen3-Next-80B-Thinking + Qwen3-235B-Instruct) — it's the only combo whose planner can handle a rich task without crashing AND whose executor uses the prompt-specified arguments. It's also the most expensive (5.6k tokens for the rich run), so the recommendation depends on what's gating cost vs correctness. Combo 2 is competitive at much lower spend (1.4k tokens for the rich run, ~4× cheaper) but produces fewer tool calls before giving up. Combo 3 is unsuitable as the planner side of any rich-task pipeline.

**What this means for the rubric.** The Task C zero-success result in the bare table is real, but it's measuring a framework bug (Bug 4) rather than model capability. The rich-input table is the apples-to-apples comparison; the bare-input table is the documentation of what every student's `make ex5-real` currently does and why. Both are useful evidence; only the second is a fair model comparison.

### Slide-scenario probe (single run)

For completeness, I also ran the **exact slide-deck scenario** verbatim through combo 1 (best performer above) by routing it via a third env-var hook `EX5_TASK_STR` (`run.py:255-261`) that lets the runner feed an arbitrary string to the planner. Invocation: `uv run python scripts/ex5_compare_run.py combo1 --tag slide --task-string "Sort the pub for tonight. 160 people, vegan options, quiet corner for a webinar segment. Deposit max £300. Confirm by 5 PM."` → `sess_66016e7e54d4`.

The result was the cleanest run of the whole comparison. The planner produced **four constraint-preserving subgoals** — *sg_1: confirm capacity for 160 + quiet corner; sg_2: arrange vegan menu; sg_3: deposit ≤ £300; sg_4: confirm before 5 PM*. The executor made exactly one `venue_search({'near': 'Edinburgh', 'party_size': 160})` call (no hallucinated party_size, no spiral) and, on getting 0 results from the fixture, wrote a well-formed `ipc/handoff_to_structured.json` whose `reason` is *"No venues found for 160 people in Edinburgh"* and whose `data` field carries `{party_size: 160, need_quiet_area: true}`. Slide steps 1 (loop half runs) and 2 (handoff fires, on disk) are satisfied verbatim by this single session; no flyer is produced because no venue in `sample_data/venues.json` has 160 capacity (which is *correct* behaviour for the fixture, not a bug). Step 3-5 of the slide flow would require routing this handoff through the Ex7 bridge → Rasa, which would reject on `party_too_large` (160 ≫ 8) — a path already proven independently in Ex6.

Session: `sessions/sess_66016e7e54d4` (marker `combo1-slide`, with the literal task string persisted under `task_string` for reproducibility).

### Citations

- `sessions/sess_e11860274d75`, `sess_be1d30d58399`, `sess_ac1ebfaa3d20` — combo 1 (bare)
- `sessions/sess_e52af16804e0`, `sess_09c06c5b90d8`, `sess_917eaa9a4337` — combo 2 (bare)
- `sessions/sess_5365f9a91b87`, `sess_b02cad67463d`, `sess_61d26231d8eb` — combo 3 (bare)
- `sessions/sess_bbd6694560d0` — combo 1 **rich** (Bug 4 control)
- `sessions/sess_0b39c226a8d2` — combo 2 **rich** (Bug 4 control)
- `sessions/sess_8796fd54ec73` — combo 3 **rich** (planner JSON-format crash)
- `sessions/sess_66016e7e54d4` — combo 1 **slide-scenario** probe (literal slide-deck prompt; 4-subgoal plan, clean handoff, no hallucinations)
- each session carries `extras/combo.txt` with planner/executor IDs, `rich_task` flag, wall-clock and exit code
- `starter/edinburgh_research/run.py:18` — `import os`
- `starter/edinburgh_research/run.py:199-219` — `rich_task` local with the full constraint string
- `starter/edinburgh_research/run.py:252-261` — `EX5_RICH_TASK` and `EX5_TASK_STR` env-var hooks that swap bare/rich/arbitrary at the `half.run` call (default unchanged)
- `scripts/ex5_compare_run.py` — runner (env vars + `--rich` / `--task-string` / `--tag` flags + session copy + marker)
- `scripts/ex5_model_compare.py` — analysis (reads ticket manifests + trace events; groups bare/rich separately via combo marker)
- `answers/ex5_task_c_data.md` — auto-generated raw JSON for every run
- `Makefile:288-313` — `ex5-compare-combo{1,2,3}` / `ex5-compare-all` / `ex5-compare-analysis` targets
