"""Create a new agent folder from the template.

    uv run python tools/new_agent.py C:/agents/my-agent

Copies template/* and runner/ into the folder, writes agent.json from agent.example.json,
writes the folder path into runner/run_agent.vbs,
creates logs/, a .gitignore, and runs `git init` if git is available. Refuses to overwrite.
"""
import sys, shutil, subprocess, pathlib

KIT = pathlib.Path(__file__).resolve().parent.parent
GITIGNORE = "run.lock\nlogs/\nsecrets/\nSTOP\n__pycache__/\n"


def create(target):
    target = pathlib.Path(target).resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise SystemExit(f"{target} exists and is not an empty folder; nothing written.")
    target.mkdir(parents=True, exist_ok=True)
    for f in (KIT / "template").iterdir():
        shutil.copy2(f, target / f.name)
    shutil.copytree(KIT / "runner", target / "runner", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(KIT / "agent.example.json", target / "agent.json")
    vbs = target / "runner" / "run_agent.vbs"
    vbs.write_text(vbs.read_text(encoding="utf-8").replace("__AGENT_DIR__", str(target)), encoding="utf-8")
    (target / "logs").mkdir()
    (target / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    try:
        subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    except (OSError, subprocess.CalledProcessError):
        print("git not found or failed: run `git init` yourself.")
    return target


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    t = create(sys.argv[1])
    print(f"Agent folder ready: {t}\nNext: fill every <...> in CLAUDE.md (the runner refuses to start otherwise), then edit agent.json.")
