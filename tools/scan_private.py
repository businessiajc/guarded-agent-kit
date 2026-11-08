"""Scan a folder for private data before you publish it (an agent's files leak a lot).

    uv run python tools/scan_private.py <folder> [--terms private-terms.txt]

Flags: e-mail addresses, user-profile paths (C:/Users/<name>, /home/<name>), API-key-like strings,
IBAN-like strings, French phone numbers, and every term listed in the terms file (one per line,
case-insensitive; keep that file OUT of the repository). Exit code 1 if anything is found.
Every file that decodes as UTF-8 is scanned, whatever its extension; binary files are not.
Limits: it does not read git history. Publish from a fresh `git init`, never from a repo that held private files.
Its own test fixtures and regex line are reported too; that is expected.
"""
import re, sys, pathlib

PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "user path": re.compile(r"(?i)(?:[A-Z]:[\\/]+Users[\\/]+|/home/|/Users/)(?!<)[^\\/\s\"'<>]+"),
    "api key": re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|AIza[0-9A-Za-z_-]{30,}|AKIA[0-9A-Z]{16})\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}\b"),
    "phone FR": re.compile(r"(?<!\d)(?:\+33 ?|0)[1-9](?:[ .-]?\d{2}){4}(?!\d)"),
}
ALLOWED_EMAILS = {"noreply@anthropic.com"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}
MAX_BYTES = 2_000_000  # larger files are reported as skipped, not scanned


def scan(folder, terms=()):
    hits = []
    terms = [t.strip().lower() for t in terms if t.strip()]
    for p in sorted(pathlib.Path(folder).rglob("*")):
        if p.is_dir() or SKIP_DIRS & set(p.parts):
            continue
        for t in terms:
            if t in p.name.lower():
                hits.append((str(p), 0, "term in file name", t))
        try:
            if p.stat().st_size > MAX_BYTES:
                hits.append((str(p), 0, "skipped (too large)", p.name))
                continue
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: not scanned
        for n, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            for kind, rx in PATTERNS.items():
                for m in rx.finditer(line):
                    if kind == "email" and m.group(0).lower() in ALLOWED_EMAILS:
                        continue
                    hits.append((str(p), n, kind, m.group(0)))
            for t in terms:
                if t in low:
                    hits.append((str(p), n, "term", t))
    return hits


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    terms = []
    if "--terms" in a:
        i = a.index("--terms")
        if i + 1 >= len(a):
            raise SystemExit("--terms needs a file path")
        terms = pathlib.Path(a[i + 1]).read_text(encoding="utf-8").splitlines()
        a = a[:i] + a[i + 2:]
    found = scan(a[0], terms)
    for f, n, kind, val in found:
        print(f"{f}:{n}: [{kind}] {val}")
    print(f"{len(found)} finding(s).")
    sys.exit(1 if found else 0)
