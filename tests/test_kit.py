"""Tests that need neither the Claude SDK nor network. Run: uv run --with pytest python -m pytest -q tests"""
import json, os, sys, time, pathlib, datetime, importlib

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(KIT / "runner"), str(KIT / "tools")]
import run_agent, scan_private, new_agent  # noqa: E402


def write_costs(p, lines):
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_spent_today_sums_only_today_and_skips_bad_lines(tmp_path):
    c = tmp_path / "COSTS.jsonl"
    write_costs(c, [json.dumps({"date": "2026-01-02T09:30:00", "cost_usd": 1.25}),
                    json.dumps({"date": "2026-01-02T20:30:00", "cost_usd": 0.5}),
                    json.dumps({"date": "2026-01-01T09:30:00", "cost_usd": 9}),
                    "not json", json.dumps({"date": "2026-01-02T21:00:00", "cost_usd": None})])
    assert run_agent.spent_today(c, "2026-01-02") == 1.75
    assert run_agent.spent_today(tmp_path / "missing.jsonl", "2026-01-02") == 0.0


def test_limit_never_exceeds_global_cap():
    cfg = {"daily_cap_usd": 10, "modes": {"a": {"daily_limit_usd": 50}, "b": {"daily_limit_usd": 4}, "c": {}}}
    assert run_agent.limit_for(cfg, "a") == 10
    assert run_agent.limit_for(cfg, "b") == 4
    assert run_agent.limit_for(cfg, "c") == 10


def test_lock_freshness(tmp_path):
    lock = tmp_path / "run.lock"
    assert not run_agent.lock_is_fresh(lock)
    lock.write_text("1")
    assert run_agent.lock_is_fresh(lock)
    old = time.time() - (run_agent.LOCK_HOURS * 3600 + 5)
    os.utime(lock, (old, old))
    assert not run_agent.lock_is_fresh(lock)


def _setup_root(tmp_path, monkeypatch, cap=10):
    (tmp_path / "agent.json").write_text(json.dumps({"daily_cap_usd": cap, "modes": {"daily": {"task": "x"}}}), encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Charter for TestAgent", encoding="utf-8")
    monkeypatch.setattr(run_agent, "ROOT", tmp_path)
    monkeypatch.setattr(run_agent, "low_priority", lambda: None)
    called = []

    async def fake_session(*a):
        called.append(a)
        return None, "fake"
    monkeypatch.setattr(run_agent, "run_session", fake_session)
    return called


def last_status(tmp_path):
    return json.loads((tmp_path / "COSTS.jsonl").read_text(encoding="utf-8").splitlines()[-1])["status"]


def test_stop_file_blocks_session(tmp_path, monkeypatch):
    called = _setup_root(tmp_path, monkeypatch)
    (tmp_path / "STOP").write_text("")
    assert run_agent.main(["daily"]) == 0
    assert last_status(tmp_path) == "skipped:STOP" and not called


def test_budget_blocks_session(tmp_path, monkeypatch):
    called = _setup_root(tmp_path, monkeypatch, cap=2)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    write_costs(tmp_path / "COSTS.jsonl", [json.dumps({"date": now, "cost_usd": 2.0})])
    assert run_agent.main(["daily"]) == 0
    assert last_status(tmp_path).startswith("skipped:budget") and not called


def test_fresh_lock_blocks_session(tmp_path, monkeypatch):
    called = _setup_root(tmp_path, monkeypatch)
    (tmp_path / "run.lock").write_text("1")
    assert run_agent.main(["daily"]) == 0
    assert last_status(tmp_path) == "skipped:lock" and not called


def test_stop_cannot_be_bypassed(tmp_path, monkeypatch):
    called = _setup_root(tmp_path, monkeypatch)
    (tmp_path / "STOP").write_text("")
    run_agent.main(["daily", "--ignore-budget", "--force"])
    assert last_status(tmp_path) == "skipped:STOP" and not called


def test_ignore_budget_runs_and_releases_lock(tmp_path, monkeypatch):
    called = _setup_root(tmp_path, monkeypatch, cap=1)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    write_costs(tmp_path / "COSTS.jsonl", [json.dumps({"date": now, "cost_usd": 5})])
    assert run_agent.main(["daily", "--ignore-budget"]) == 0
    assert len(called) == 1 and not (tmp_path / "run.lock").exists()


def test_stop_created_during_wait_is_honoured(tmp_path, monkeypatch):
    called = _setup_root(tmp_path, monkeypatch)
    state = {"n": 0}

    def busy(names):
        state["n"] += 1
        if state["n"] == 1:
            (tmp_path / "STOP").write_text("")
            return True
        return False
    monkeypatch.setattr(run_agent, "busy_program_running", busy)
    monkeypatch.setattr(run_agent.time, "sleep", lambda s: None)
    run_agent.main(["daily"])
    assert last_status(tmp_path) == "skipped:STOP" and not called and not (tmp_path / "run.lock").exists()


def test_take_lock_is_exclusive_and_replaces_stale(tmp_path):
    lock = tmp_path / "run.lock"
    assert run_agent.take_lock(lock) and not run_agent.take_lock(lock)
    old = time.time() - (run_agent.LOCK_HOURS * 3600 + 5)
    os.utime(lock, (old, old))
    assert run_agent.take_lock(lock)


def test_unfilled_template_is_refused(tmp_path, monkeypatch):
    called = _setup_root(tmp_path, monkeypatch)
    (tmp_path / "CLAUDE.md").write_text("You are <AGENT_NAME>", encoding="utf-8")
    assert run_agent.main(["daily"]) == 2 and not called


def test_bad_cost_lines_never_crash(tmp_path):
    c = tmp_path / "COSTS.jsonl"
    write_costs(c, ["123", "[1]", json.dumps({"date": "2026-01-02", "cost_usd": "nan"}),
                    json.dumps({"date": "2026-01-02", "cost_usd": 0.5})])
    assert run_agent.spent_today(c, "2026-01-02") == 0.5


def test_unknown_mode_is_rejected(tmp_path, monkeypatch):
    _setup_root(tmp_path, monkeypatch)
    assert run_agent.main(["nope"]) == 2


def test_prompt_contains_rules_and_task():
    cfg = {"daily_cap_usd": 10, "session_rules": ["Rule one"], "modes": {"daily": {"task": "Do the thing"}}}
    p = run_agent.build_prompt(cfg, "daily", 1.5)
    assert "- Rule one" in p and "Do the thing" in p and "1.50 USD" in p


def test_scanner_finds_private_data_and_terms(tmp_path):
    (tmp_path / "a.md").write_text("mail me: someone@example.org\npath " + "C:" + chr(92) + "Users" + chr(92) + "jdoe" +
                                   "\nkey ghp_" + "a" * 36 + "\ncall 06 12 34 56 78\nMy Secret Project\n", encoding="utf-8")
    (tmp_path / "ok.md").write_text("Co-Authored-By: x <noreply@anthropic.com>\nC:/Users/<you>/agents\n", encoding="utf-8")
    (tmp_path / "notes.log").write_text("my secret project again", encoding="utf-8")
    kinds = sorted(k for _, _, k, _ in scan_private.scan(tmp_path, ["my secret project"]))
    assert kinds == ["api key", "email", "phone FR", "term", "term", "user path"]


def test_new_agent_scaffold(tmp_path):
    t = new_agent.create(tmp_path / "agent")
    for name in ("CLAUDE.md", "STATE.md", "PERMISSIONS.md", "agent.json", "runner/run_agent.py", ".gitignore"):
        assert (t / name).exists(), name
    assert str(t) in (t / "runner" / "run_agent.vbs").read_text(encoding="utf-8")
    assert json.loads((t / "agent.json").read_text(encoding="utf-8"))["daily_cap_usd"] > 0
    try:
        new_agent.create(t)
        assert False, "should refuse a non-empty folder"
    except SystemExit:
        pass


def test_example_config_is_valid():
    cfg = json.loads((KIT / "agent.example.json").read_text(encoding="utf-8"))
    for name, m in cfg["modes"].items():
        assert m["task"] and run_agent.limit_for(cfg, name) <= cfg["daily_cap_usd"]
