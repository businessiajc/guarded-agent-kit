"""Run one unattended Claude Code session for a guarded agent (meant for a scheduled task).

Usage:
    uv run --with claude-agent-sdk --with anyio python run_agent.py <mode> [--ignore-budget]
    uv run python run_agent.py --status          # today's spend, no session started

Enforced in code (the charter in CLAUDE.md is only text the model reads; these checks are not):
  - a STOP file in the agent folder blocks every session, with no override;
  - one session at a time: the lock file is created atomically before anything else and refreshed
    while the session runs; a lock untouched for LOCK_HOURS is considered left over by a killed run;
  - today's logged spend must be below the mode's limit (checked before and after the wait);
  - CLAUDE.md must not contain unfilled template placeholders.
The runner lowers its CPU priority and waits (up to 4 hours) while a listed program is running.
Every attempt appends one line to COSTS.jsonl, with the cost reported by the SDK for real sessions.
Settings: agent.json next to CLAUDE.md (see agent.example.json).
"""
import sys, os, json, math, time, datetime, subprocess, pathlib

ROOT = pathlib.Path(os.environ.get("AGENT_ROOT") or pathlib.Path(__file__).resolve().parent.parent)
LOCK_HOURS = 3
WAIT_HOURS = 4
PLACEHOLDERS = ("<AGENT_NAME>", "<OWNER>", "<GOAL", "<DAILY_CAP>")


def load_config(root=None):
    root = root or ROOT
    try:
        with open(root / "agent.json", encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError) as e:
        raise SystemExit(f"Cannot read {root / 'agent.json'}: {e}")
    for key in ("daily_cap_usd", "modes"):
        if key not in cfg:
            raise SystemExit(f"agent.json: missing key '{key}'")
    return cfg


def spent_today(costs_file, today=None):
    """Sum cost_usd of today's lines. Bad lines are skipped, never fatal."""
    today = today or datetime.date.today().isoformat()
    total = 0.0
    if not costs_file.exists():
        return total
    with open(costs_file, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
                if not isinstance(d, dict) or not str(d.get("date", "")).startswith(today):
                    continue
                c = float(d.get("cost_usd") or 0)
                if math.isfinite(c) and c > 0:
                    total += c
            except Exception:
                continue
    return total


def log_session(costs_file, mode, status, cost=0.0, turns=None, seconds=0.0, last_text=""):
    with open(costs_file, "a", encoding="utf-8") as f:
        f.write(json.dumps({"date": datetime.datetime.now().isoformat(timespec="seconds"), "mode": mode,
                            "status": status, "cost_usd": cost, "turns": turns, "seconds": seconds,
                            "summary": (last_text or "")[:300]}, ensure_ascii=False) + "\n")


def lock_is_fresh(lock_file, now=None):
    now = now or time.time()
    try:
        return now - lock_file.stat().st_mtime < LOCK_HOURS * 3600
    except FileNotFoundError:
        return False


def take_lock(lock_file):
    """Atomic: True if this process now holds the lock. A stale lock is replaced."""
    if lock_file.exists() and not lock_is_fresh(lock_file):
        try:
            lock_file.unlink()
        except FileNotFoundError:
            pass
    try:
        with open(lock_file, "x") as f:
            f.write(str(os.getpid()))
        return True
    except FileExistsError:
        return False


def touch(path):
    try:
        os.utime(path, None)
    except OSError:
        pass


def limit_for(cfg, mode):
    m = cfg["modes"][mode]
    return min(float(m.get("daily_limit_usd", cfg["daily_cap_usd"])), float(cfg["daily_cap_usd"]))


def unfilled_placeholders(root=None):
    p = (root or ROOT) / "CLAUDE.md"
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return ["CLAUDE.md missing"]
    return [t for t in PLACEHOLDERS if t in text]


def low_priority():
    """Below-normal priority (Windows: also half the cores). Silently ignored if unavailable."""
    if os.name != "nt":
        try:
            os.nice(10)
        except Exception:
            pass
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetCurrentProcess()
        k.SetPriorityClass(h, 0x00004000)  # BELOW_NORMAL_PRIORITY_CLASS
        n = os.cpu_count() or 8
        half = max(2, n // 2)
        k.SetProcessAffinityMask(h, ((1 << half) - 1) << (n - half))
    except Exception:
        pass


def busy_program_running(names):
    if not names:
        return False
    try:
        cmd = ["tasklist", "/FO", "CSV", "/NH"] if os.name == "nt" else ["ps", "-eo", "comm"]
        # bytes, then a tolerant decode: tasklist prints in the console code page, not UTF-8
        out = subprocess.run(cmd, capture_output=True, timeout=20).stdout.decode("utf-8", errors="replace").lower()
        return any(n.lower() in out for n in names)
    except Exception:
        return False


def build_prompt(cfg, mode, spent):
    rules = "\n".join("- " + r for r in cfg.get("session_rules", []))
    return (f"Date: {datetime.datetime.now():%Y-%m-%d %H:%M}. You were started by a scheduled task; no human is present.\n"
            f"Spent today: {spent:.2f} USD; daily cap: {cfg['daily_cap_usd']} USD.\n\n"
            f"SESSION RULES:\n{rules}\n\nTASK ({mode}):\n{cfg['modes'][mode]['task']}")


async def run_session(cfg, mode, spent, lock):
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, AssistantMessage, ResultMessage, TextBlock
    m = cfg["modes"][mode]
    opts = ClaudeAgentOptions(
        cwd=str(ROOT), system_prompt={"type": "preset", "preset": "claude_code"}, setting_sources=["project"],
        permission_mode=cfg.get("permission_mode", "acceptEdits"), allowed_tools=list(cfg.get("allowed_tools", [])),
        model=m.get("model"), max_turns=int(m.get("max_turns", 40)),
        env={"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    result, last = None, ""
    async with ClaudeSDKClient(options=opts) as client:
        await client.query(build_prompt(cfg, mode, spent))
        async for msg in client.receive_response():
            touch(lock)  # heartbeat: a long session keeps its lock
            if isinstance(msg, AssistantMessage):
                for b in msg.content:
                    if isinstance(b, TextBlock):
                        print(b.text)
                        last = b.text
            elif isinstance(msg, ResultMessage):
                result = msg
    return result, last


def blocked(costs, mode, cfg, ignore_budget):
    """Reason to refuse a session now, or None."""
    if (ROOT / "STOP").exists():
        return "skipped:STOP"
    spent, limit = spent_today(costs), limit_for(cfg, mode)
    if spent >= limit and not ignore_budget:
        return f"skipped:budget {spent:.2f}/{limit}"
    return None


def main(argv):
    cfg = load_config()
    costs = ROOT / "COSTS.jsonl"
    if argv[:1] == ["--status"]:
        print(f"Spent today: {spent_today(costs):.3f} USD / cap {cfg['daily_cap_usd']} USD")
        return 0
    if not argv or argv[0] not in cfg["modes"]:
        print("usage: run_agent.py <" + "|".join(cfg["modes"]) + "> [--ignore-budget] | --status")
        return 2
    mode, ignore_budget = argv[0], "--ignore-budget" in argv
    missing = unfilled_placeholders()
    if missing:
        log_session(costs, mode, "skipped:template"); print("Fill CLAUDE.md first:", ", ".join(missing))
        return 2
    reason = blocked(costs, mode, cfg, ignore_budget)
    if reason:
        log_session(costs, mode, reason); print(reason)
        return 0
    lock = ROOT / "run.lock"
    if not take_lock(lock):
        log_session(costs, mode, "skipped:lock"); print("Another session holds the lock.")
        return 0
    result, last, t0, status = None, "", time.time(), None
    try:
        low_priority()
        while busy_program_running(cfg.get("wait_while_running", [])) and time.time() - t0 < WAIT_HOURS * 3600:
            touch(lock)
            time.sleep(120)
        status = blocked(costs, mode, cfg, ignore_budget)  # STOP or spend may have changed during the wait
        if status is None:
            import anyio
            result, last = anyio.run(run_session, cfg, mode, spent_today(costs), lock)
            status = "ok" if result else "failed"
        else:
            print(status)
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
        log_session(costs, mode, status or "failed", float(getattr(result, "total_cost_usd", 0) or 0),
                    getattr(result, "num_turns", None), round(time.time() - t0, 1), last)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
