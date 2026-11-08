' Starts run_agent.py hidden (no console window). Argument: the mode name from agent.json.
' tools/new_agent.py fills AGENT_DIR; check it if you moved the folder. uv must be on the PATH of the task's user.
Const AGENT_DIR = "__AGENT_DIR__"
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = AGENT_DIR & "\runner"
mode = WScript.Arguments(0)
sh.Run "cmd /c uv run --with claude-agent-sdk --with anyio python run_agent.py """ & mode & """ >> ""..\logs\" & mode & ".log"" 2>&1", 0, False
