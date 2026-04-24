# homework-pub-booking — student-facing commands.
#
# The critical five (in order of use):
#   make setup         install everything, create .env
#   make verify        prove the environment works end-to-end
#   make test          run public tests
#   make check-submit  run local grader (NOT the final grade)
#   make help          list all targets with descriptions
#
# Per-exercise targets follow. They all run in offline mode unless
# suffixed with -real, in which case they hit Nebius (burns tokens).

PY := python3
UV := uv

# Load .env into Make's own environment and export every variable to
# child processes. This is how Rasa/sovereign-agent/subprocess.run all
# end up seeing RASA_PRO_LICENSE, NEBIUS_KEY, etc. without extra Python
# plumbing. Idiom borrowed from the Rasa reference Makefile.
ifneq (,$(wildcard .env))
    include .env
    export
endif

.DEFAULT_GOAL := help

# ─── help ───────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make <target>\n\nTargets:\n"} \
	/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""

# ─── setup / verify ─────────────────────────────────────────────────────

.PHONY: setup
setup: ## Install Python 3.12, deps, and create .env from the template
	@command -v $(UV) >/dev/null 2>&1 || { \
	  echo "✗ uv is not installed."; \
	  echo "  Install from https://astral.sh/uv or run: pip install uv"; \
	  exit 1; \
	}
	@$(UV) sync --all-groups
	@if [ -f .env ]; then \
	  echo "✓ .env already exists (not overwriting)."; \
	elif [ -f .env.example ]; then \
	  cp .env.example .env && echo "✓ Created .env from template. Edit it and set NEBIUS_KEY."; \
	else \
	  echo "✗ Cannot create .env — .env.example is missing from your checkout."; \
	  echo ""; \
	  echo "  Your tarball extract didn't include dotfiles. Fix with one of:"; \
	  echo "    1. Re-extract with 'tar xzvf homework-pub-booking.tar.gz'"; \
	  echo "       — look for '.env.example' in the output to confirm."; \
	  echo "    2. Or run 'make env-bootstrap' — it regenerates .env.example"; \
	  echo "       from a bundled fallback inside the Makefile."; \
	  exit 1; \
	fi
	@echo "✓ make setup done. Next: edit .env, then run 'make verify'."

.PHONY: env-bootstrap
env-bootstrap: ## Regenerate .env.example from a bundled fallback (use if .env.example is missing)
	@if [ -f .env.example ]; then \
	  echo "ℹ .env.example already exists — not overwriting."; \
	  echo "  To force-regenerate: rm .env.example && make env-bootstrap"; \
	else \
	  $(UV) run python scripts/write_env_example.py; \
	  echo "✓ Wrote .env.example. Now run 'make setup'."; \
	fi

.PHONY: verify
verify: ## Run preflight + a real 1-token LLM call; prints green ✓ or points you at the right doc
	@$(UV) run python scripts/preflight.py
	@$(UV) run python scripts/nebius_smoke.py

# ─── tests / grading ────────────────────────────────────────────────────

.PHONY: test
test: ## Run the public test suite (pass = you're on track)
	@$(UV) run pytest tests/public -v

.PHONY: test-all
test-all: ## Run public + private tests (private tests only exist in the grader CI environment)
	@$(UV) run pytest tests/ -v

.PHONY: check-submit
check-submit: ## Run the local grader (advisory — CI at deadline is the authoritative grade)
	@$(UV) run python -m grader.check_submit

# ─── per-exercise targets ───────────────────────────────────────────────

# ─── rasa host-process (for Ex6) ──────────────────────────────────────
# Ex6 needs two Rasa processes on localhost. Students run each in its
# own terminal. The educator harness spawns them automatically when
# you `make ex6-real`.

.PHONY: rasa-train
rasa-train: ## Train the Rasa model (reruns use the cached model)
	@cd rasa_project && $(UV) run rasa train

.PHONY: rasa-actions
rasa-actions: ## Terminal 1 — run the Rasa action server on :5055
	@echo "▶ Starting Rasa action server (port 5055). Ctrl-C to stop."
	@cd rasa_project && $(UV) run rasa run actions -p 5055

.PHONY: rasa-serve
rasa-serve: ## Terminal 2 — run the Rasa server on :5005 (trains if needed)
	@cd rasa_project && \
	  if [ ! -d models ] || [ -z "$$(ls -A models 2>/dev/null)" ]; then \
	    echo "▶ No trained model found; running rasa train first..."; \
	    $(UV) run rasa train; \
	  fi
	@echo "▶ Starting Rasa server (port 5005). Ctrl-C to stop."
	@cd rasa_project && $(UV) run rasa run --enable-api --cors "*" -p 5005

.PHONY: rasa-clean
rasa-clean: ## Remove Rasa's trained models and cache
	@rm -rf rasa_project/models rasa_project/.rasa 2>/dev/null
	@echo "✓ rasa_project/models/ and .rasa/ removed"

# ─── log / session discovery ──────────────────────────────────────────

.PHONY: logs
logs: ## Print the path to your most recent session (across all scenarios)
	@$(UV) run python -c "import sys; sys.path.insert(0, 'scripts'); \
		from narrator import _platform_data_dir; \
		from pathlib import Path; \
		cands = []; \
		[cands.extend(Path('sessions').glob('sess_*'))] if Path('sessions').exists() else None; \
		root = _platform_data_dir(); \
		[cands.extend(root.glob('examples/*/sess_*'))] if root.exists() else None; \
		cands = [c for c in cands if c.is_dir()]; \
		cands.sort(key=lambda p: p.stat().st_mtime, reverse=True); \
		print(cands[0] if cands else '(no sessions yet)')"

# ─── narration ────────────────────────────────────────────────────────

.PHONY: narrate
narrate: ## Narrate a session by id: make narrate SESSION=sess_abc123
	@if [ -z "$(SESSION)" ]; then \
	  echo "Usage: make narrate SESSION=<session-id>"; \
	  echo "Tip:   make narrate-latest   # narrate the most recent session"; \
	  exit 2; \
	fi
	@$(UV) run python scripts/narrator.py --session $(SESSION)

.PHONY: narrate-latest
narrate-latest: ## Narrate the most recent session — useful right after `make ex5-real`
	@$(UV) run python scripts/narrator.py --latest

.PHONY: ex5
ex5: ## Run Ex5 (Edinburgh research) in offline FakeLLMClient mode
	@$(UV) run python -m starter.edinburgh_research.run

.PHONY: ex5-real
ex5-real: ## Run Ex5 against the real Nebius LLM (uses tokens!)
	@$(UV) run python -m starter.edinburgh_research.run --real

.PHONY: ex6
ex6: ## Ex6 (mock) — offline Rasa mock, no setup needed (tier 1)
	@$(UV) run python -m starter.rasa_half.run

.PHONY: ex6-real
ex6-real: ## Ex6 (two-terminal) — probe localhost:5005, run if Rasa is up (tier 2, recommended)
	@$(UV) run python scripts/ex6_probe_and_run.py

.PHONY: ex6-auto
ex6-auto: ## Ex6 (one-terminal) — auto-spawn Rasa + action server, run, tear down (tier 3)
	@$(UV) run python -m starter.rasa_half.run --real --auto

.PHONY: ex6-help
ex6-help: ## Print the three-terminal recipe for Ex6 real mode
	@$(UV) run python scripts/ex6_help.py

.PHONY: ex7
ex7: ## Run Ex7 (handoff bridge) end-to-end
	@$(UV) run python -m starter.handoff_bridge.run

.PHONY: ex8-text
ex8-text: ## Run Ex8 (voice pipeline) in TEXT-ONLY mode — no Speechmatics needed
	@$(UV) run python -m starter.voice_pipeline.run --text

.PHONY: ex8-voice
ex8-voice: ## Run Ex8 with real STT/TTS — requires SPEECHMATICS_KEY
	@$(UV) run python -m starter.voice_pipeline.run --voice

.PHONY: ex9
ex9: ## Validate that your Ex9 reflection answers are populated and well-formed
	@$(UV) run python -m grader.check_submit --only ex9

# ─── housekeeping ───────────────────────────────────────────────────────

.PHONY: lint
lint: ## Ruff check
	@$(UV) run ruff check starter/ grader/ tests/ scripts/

.PHONY: format
format: ## Ruff format
	@$(UV) run ruff format starter/ grader/ tests/ scripts/

.PHONY: format-check
format-check: ## Ruff format --check (used by CI)
	@$(UV) run ruff format --check starter/ grader/ tests/ scripts/

.PHONY: clean
clean: ## Delete local session artifacts (does NOT delete your answers or code)
	@rm -rf sessions/ demo_sessions_* .pytest_cache/ .ruff_cache/ 2>/dev/null || true
	@echo "✓ cleaned session artifacts (your answers/ and starter/ are untouched)"

.PHONY: clean-all
clean-all: clean ## Full reset — delete .venv too, start over fresh
	@rm -rf .venv/ uv.lock
	@echo "✓ full reset. Run 'make setup' to start over."

.PHONY: doctor
doctor: ## Like sovereign-agent doctor but scoped to this repo
	@$(UV) run python scripts/preflight.py

.PHONY: ci
ci: lint format-check test ## Everything CI runs on a PR, in order
	@echo "✓ make ci green — your scaffold still compiles and tests pass."

# ─── educator-only targets (hidden from students) ───────────────────
# These require solution/ to exist. Students don't have it; running
# any of these from a student's checkout will print a helpful error.

.PHONY: educator-apply-solution
educator-apply-solution: ## [EDUCATOR] Copy solution/ over starter/ for validation
	@if [ ! -d solution ]; then \
	  echo "✗ solution/ not found — this target is educator-only."; \
	  echo "  Solutions live in a private sibling repo and are copied in manually."; \
	  exit 1; \
	fi
	@bash solution/apply_solution.sh

.PHONY: educator-reset
educator-reset: ## [EDUCATOR] Restore starter/, answers/, rasa_project/ from .educator_backup/
	@if [ ! -d .educator_backup ]; then \
	  echo "✗ .educator_backup/ not found. Did you ever run educator-apply-solution?"; \
	  exit 1; \
	fi
	@rm -rf starter answers rasa_project
	@cp -r .educator_backup/starter starter
	@cp -r .educator_backup/answers answers
	@if [ -d .educator_backup/rasa_project ]; then cp -r .educator_backup/rasa_project rasa_project; fi
	@echo "✓ starter/, answers/, rasa_project/ restored"

.PHONY: educator-validate
educator-validate: ## [EDUCATOR] Back up, apply solution, run all scenarios (offline), grade, restore
	@if [ ! -d solution ]; then \
	  echo "✗ solution/ not found — this target is educator-only."; \
	  exit 1; \
	fi
	@$(UV) run python scripts/educator_validate.py

.PHONY: educator-validate-real
educator-validate-real: ## [EDUCATOR] Like educator-validate but runs every -real scenario against live services (~$0.20)
	@if [ ! -d solution ]; then \
	  echo "✗ solution/ not found — this target is educator-only."; \
	  exit 1; \
	fi
	@echo ""
	@echo "⚠  This runs EVERY scenario against LIVE services:"
	@echo "   - Ex5/Ex7: Nebius API (~\$$0.05 each)"
	@echo "   - Ex6:     Rasa Pro container via Docker (needs RASA_PRO_LICENSE + 60-90s)"
	@echo "   - Ex8:     Nebius Llama-3.3 for the manager persona (~\$$0.02)"
	@echo "   Total: roughly \$$0.20 and ~3 minutes on first run."
	@echo ""
	@echo "   Ctrl-C in 5 seconds to abort."
	@sleep 5
	@$(UV) run python scripts/educator_validate.py --real

.PHONY: educator-diagnostics
educator-diagnostics: ## [EDUCATOR] Comprehensive diagnostics — paste output when asking for help
	@$(UV) run python scripts/educator_diagnostics.py

.PHONY: educator-diagnostics-quick
educator-diagnostics-quick: ## [EDUCATOR] Diagnostics without network probes (fast)
	@$(UV) run python scripts/educator_diagnostics.py --quick

.PHONY: educator-backup
educator-backup: ## [EDUCATOR] Snapshot starter/, answers/, and rasa_project/ to .educator_backup/
	@rm -rf .educator_backup
	@mkdir .educator_backup
	@cp -r starter .educator_backup/starter
	@cp -r answers .educator_backup/answers
	@if [ -d rasa_project ]; then cp -r rasa_project .educator_backup/rasa_project; fi
	@echo "✓ starter/, answers/, rasa_project/ snapshotted to .educator_backup/"
