# guarded-agent-kit

A starter kit for running a Claude Code agent unattended, on a schedule, with limits on spend, money, accounts and facts.

It is extracted from an agent we have run every day since 2026-10-30, with nobody watching the sessions. That agent has earned **0 €** so far (2026-11-08). We publish the kit because the guardrails are the reusable part, not because it makes money. If someone sells you an "autonomous money agent", ask for bank statements.

## What is enforced, and what is only asked

Two layers, and the difference matters:

- **Enforced in code** by `runner/run_agent.py`: a `STOP` file blocks every session (no override flag); one session at a time (atomic lock, refreshed while the session runs); no new session once today's logged spend reaches the limit; no session while `CLAUDE.md` still contains template placeholders; tools limited to `allowed_tools`.
- **Asked in text** by `template/CLAUDE.md`: never handle money, never type a password, never create an account, mark every fact VERIFIED (official source + date) or UNVERIFIED, no commitment without a margin calculation. The model reads these rules every session. Nothing in code stops it from ignoring them, so keep the tool list short.

## What is in it

| Path | What it does |
|---|---|
| `template/CLAUDE.md` | The agent charter: hard limits, truth rule, shopkeeper rules, experiment method, money tiers granted by the owner only, daily report format. Claude Code reloads it every session, so it survives context resets. |
| `template/*.md`, `AGENTS.json` | Empty state files read at the start of each session: state, log, experiments, accounts, permissions, knowledge, report, corrections, sub-agent registry. |
| `runner/run_agent.py` | One unattended session, with the checks above. Lowers its CPU priority and waits (up to 4 h) while a program you list is running, then re-checks STOP and spend. Appends one line per attempt to `COSTS.jsonl`. |
| `runner/run_agent.vbs`, `runner/install_tasks.ps1` | Windows: hidden launch, and scheduled tasks named after the agent folder. Read the script before running it. |
| `agent.example.json` | Daily cap, allowed tools, modes (task, model, max turns, per-mode limit), session rules, programs to wait for. |
| `tools/new_agent.py` | Creates an agent folder from the template, fills the path in the launcher, runs `git init`. |
| `tools/scan_private.py` | Looks for e-mails, user paths, API-key-like strings, IBAN-like strings, French phone numbers and your own list of private terms, in every UTF-8 file. It does not read git history. |
| `tests/` | 17 tests, no network, no SDK needed: `uv run --with pytest python -m pytest -q tests`. |

## Quick start (Windows)

Requirements: [uv](https://docs.astral.sh/uv/), git, Claude Code logged in on the machine (the SDK uses that login).

```
git clone https://github.com/businessiajc/guarded-agent-kit
cd guarded-agent-kit
uv run python tools/new_agent.py C:/agents/my-agent
```

Then, in `C:/agents/my-agent`:

1. Fill every `<...>` in `CLAUDE.md`. The runner refuses to start until you do.
2. Edit `agent.json`: daily cap, allowed tools, tasks, which modes use the light model.
3. Run one session by hand: `cd runner` then `uv run --with claude-agent-sdk --with anyio python run_agent.py daily`.
4. Read `COSTS.jsonl`, `LOG.md` and `REPORT.md`.
5. Read `runner/install_tasks.ps1`, then: `powershell -ExecutionPolicy Bypass -File runner\install_tasks.ps1 -AgentDir C:\agents\my-agent`.

`uv run python runner/run_agent.py --status` prints today's spend without starting anything. To stop everything: create a file named `STOP` in the agent folder.

On Linux or macOS the runner works the same; use cron instead of the two Windows scripts.

## Defaults worth knowing

- `permission_mode` is `acceptEdits` and `allowed_tools` lists file tools, web reading and a few `git` commands. Anything else (other shell commands) is refused in an unattended run. `bypassPermissions` lets the agent run any command your user can; the spend cap does not limit what those commands do.
- The spend check happens **before** a session starts. A running session is bounded by `max_turns`, not by the cap.
- `daily_cap_usd` is shared: a mode with `daily_limit_usd: 6` is skipped once the whole day's spend reaches 6, whichever mode spent it.
- The cost is the one the SDK reports (`total_cost_usd`). On a subscription plan it is an API-equivalent estimate, not a bill.
- A lock untouched for 3 hours is treated as left over by a killed run and replaced.

## Notes from our own run (anecdotes, not measurements)

- The agent drifts toward volume: it published 40+ web pages that got almost no search traffic. The charter now asks each session to produce something new and to write it down before acting.
- The truth rule costs effort and pays back: several claims taken from secondary sources were wrong or out of date once we read the official page.
- Every correction from the owner goes into `CORRECTIONS.md` as a rule with its reason.
- A separate sub-agent re-reading as an adversary caught errors the writing agent had missed. It reviewed this kit too: 15 findings before the first push; 14 fixed, 1 kept on purpose (agent folders keep `COSTS.jsonl` under git).

## Tested with

Windows 11, Python 3.12.13 (via uv), claude-agent-sdk 0.2.179, on 2026-11-08: a real session on the light model that created a file and committed it with git (0.0086 USD logged); the hidden launcher refused to start with a STOP file present; the task installer registered two tasks, which we then removed.

## License

MIT. No warranty. You are responsible for what your agent does in your name.
