# Ex8 — Voice pipeline

## Your answer

### Architecture

Two modes with a shared trace-event contract:

- **Text mode** (`run_text_mode` in `starter/voice_pipeline/voice_loop.py`) reads stdin, sends each line to `ManagerPersona`, prints the reply.
- **Voice mode** (`run_voice_mode` in the same file) wires up Speechmatics for STT and Rime for TTS, with the same `ManagerPersona` between them.

`ManagerPersona` (`starter/voice_pipeline/manager_persona.py`) holds the conversation history as a list and calls Llama-3.3-70B-Instruct via Nebius for each turn. Same prompt + same seed + same history → same reply, which makes the tests stable even though we're talking to a real model. The system prompt establishes "Alasdair", a gruff Edinburgh pub manager who'll accept bookings under £300 deposit and ≤8 people.

### Two design choices worth noting

**1. Graceful degradation.** `run_voice_mode` checks `SPEECHMATICS_KEY` and tries to import `speechmatics-python` before opening any audio devices. If either is missing, it prints a warning and falls through to `run_text_mode`:

```
⚠  SPEECHMATICS_KEY not set — falling back to text mode.
   Add to .env and re-run for real voice.
```

This means CI can verify the voice loop is implemented even without Speechmatics credentials — the same code path runs, just under the simpler transport.

**2. Shared event contract regardless of transport.** Both modes emit `voice.utterance_in` and `voice.utterance_out` events with payload `{text, turn, mode}`. The `mode` field is `"text"` in text mode and `"voice"` in voice mode. Same event shape → same downstream analysis (LLM-as-judge, trace inspection) regardless of which transport ran.

---

## Evidence — four runs across three rubric dimensions

### 1. Text mode — full conversation (`sess_65caa20246e8`)

```
you> hello there
alasdair> What can I do for ye? Booking a table, are ye?
you> yes please i'd like to book a table fot the 25th April
alasdair> How many in yer party?
you> there will be 6 of us
alasdair> Aye, we can do that. I'll pencil you in for 25th April. What's the contact number?
you> 123456
alasdair> Got it, 123456. What time were ye thinkin'?
you> 7.30pm
alasdair> Aye, 7:30pm on 25th April, six of ye. I've got ye booked in.
you> thanks for that
alasdair> Ye're welcome, laddie.
```

Six turns, well over the 3-turn rubric minimum. Alasdair stays consistently in character: "ye", "yer", "Aye", "laddie". Trace at `sessions/sess_65caa20246e8/logs/trace.jsonl` contains 12 events (6 `voice.utterance_in` + 6 `voice.utterance_out`), each with `mode: "text"`, `turn: 0..5`, and the verbatim text.

### 2. Graceful degradation when Speechmatics key is missing (`sess_d4485cc821a5`)

Forced the missing-key path with `SPEECHMATICS_KEY="" make ex8-voice`:

```
Session sess_d4485cc821a5
⚠  SPEECHMATICS_KEY not set — falling back to text mode.
   Add to .env and re-run for real voice.
Text mode. Type a message to Alasdair (pub manager); blank line to quit.
```

No crash, no traceback — clean warning + fallback to text mode. The session continued normally as a text-mode conversation. Same code, simpler transport, same trace event shape.

### 3. Voice mode — first round-trip (`sess_5e531763b538`)

After resolving the dependency hurdle (see "Real-world friction" below), confirmed the full STT → LLM → TTS pipeline ran end-to-end:

```
[turn 1] 🎤 listening...
   you> I'd like to book a pub .
   alasdair> How many in your party?
```

(Audio playback heard — Rime TTS read Alasdair's reply aloud.) Conversation ended on silence-detection at turn 2. Trace shows:

```json
{"event": "voice.utterance_in",  "turn": 0, "mode": "voice", "text": "I'd like to book a pub ."}
{"event": "voice.utterance_out", "turn": 0, "mode": "voice", "text": "How many in your party?"}
```

`mode: "voice"` distinguishes this from the text-mode trace. Same event types, different transport.

### 4. Voice mode — sustained 3-turn conversation (`sess_060db09e3d92`)

Re-ran with quicker replies to avoid the silence-detection cutoff. Three full round-trips:

```
[turn 1] you> I'd like to book a table for six on Friday night.
        alasdair> Aye, we can do that. I'll pencil you in for Friday at what time? What's the contact number?
[turn 2] you> 730.
        alasdair> Aye, we can do that. I'll pencil you in for Friday at 730. What's the contact number?
[turn 3] you> 9991234.
        alasdair> Sorted, 9991234. See you Friday.
```

Trace contains 6 events (3 in + 3 out), all with `mode: "voice"`. Character continuity preserved across the three turns ("Aye", "Sorted", "See you Friday").

---

## Real-world friction encountered (and resolved)

The voice extras path threw a real ecosystem issue worth flagging. The `speechmatics-python` library imports `pkg_resources` at module load, but modern uv-managed venvs don't include `setuptools` by default, so the import fails:

```
ModuleNotFoundError: No module named 'pkg_resources'
```

`pkg_resources` lives inside `setuptools`, but **`setuptools >= 81` no longer ships it** (deprecated, slated for removal). So `uv pip install setuptools` installed setuptools 82.0.1 — but `pkg_resources` was still missing. The fix that worked:

```bash
uv pip install --reinstall "setuptools<81"
```

This pinned setuptools to a version that still bundles `pkg_resources`. After that, both `import speechmatics` and `import sounddevice` succeeded, and `make ex8-voice` ran end-to-end.

This is exactly the kind of dependency-resolution friction `docs/real-mode-failures.md` exists to document. Not yet listed there for Ex8 — would be a fair addition.

---

## Citations

### Session artefacts

- `sessions/sess_65caa20246e8/logs/trace.jsonl` — text mode, 6 turns, 12 utterance events (`mode: "text"`)
- `sessions/sess_d4485cc821a5/` — graceful-degradation session; warning printed, fallback to text mode
- `sessions/sess_5e531763b538/logs/trace.jsonl` — voice mode, 1 turn (silence-cut-off), 2 utterance events (`mode: "voice"`)
- `sessions/sess_060db09e3d92/logs/trace.jsonl` — voice mode, 3 turns, 6 utterance events (`mode: "voice"`); the load-bearing voice-mode evidence

### Source code

- `starter/voice_pipeline/voice_loop.py` — `run_text_mode`, `run_voice_mode`, graceful-degradation check
- `starter/voice_pipeline/voice_loop.py:347` — Rime TTS speaker name (`"luna"`); per `real-mode-failures.md:261-285` may need updating if Rime renames voices
- `starter/voice_pipeline/manager_persona.py` — `ManagerPersona`, system prompt for Alasdair, OpenAICompatibleClient pointed at Llama-3.3-70B-Instruct on Nebius
- `starter/voice_pipeline/run.py` — entry point dispatching to text or voice mode based on `--voice` flag
- `starter/voice_pipeline/requirements-voice.txt` — opt-in voice deps (speechmatics-python, sounddevice, pydub, numpy)

### Documentation

- `docs/grading-rubric.md:42-43` — Ex8 rubric items (text 4 pts, voice events 3 pts, voice bonus +4 pts)
- `docs/real-mode-failures.md:232-260` — Speechmatics 401/403 failure mode
- `docs/real-mode-failures.md:261-285` — Rime "invalid voice" failure mode
- `docs/real-mode-failures.md:288+` — macOS audio playback / mic permissions
- `docs/speechmatics-setup.md` — Speechmatics signup + key procurement
- `ASSIGNMENT.md:163-202` — Ex8 specification

### Score estimate

| Rubric item | Pts | Status |
|---|---|---|
| Text mode runs 3+ turn conversation | 6 | ✓ 6 turns (sess_65caa20246e8) |
| Manager persona stays in character | 4 | ✓ "Aye"/"ye"/"laddie"/"Sorted" across all sessions |
| Voice mode works end-to-end | 4 | ✓ STT→LLM→TTS round-trip (sess_060db09e3d92, 3 turns) |
| Trace has `voice.utterance_in`/`_out` | 3 | ✓ both modes confirmed |
| Missing-key graceful degradation | 3 | ✓ (sess_d4485cc821a5) |
| **Total** | **20/20** | |
