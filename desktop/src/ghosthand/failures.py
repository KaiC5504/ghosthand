from __future__ import annotations

import json
import os
import sys
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]


def plugin_version() -> str:
    try:
        return json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        return "unknown"


def log_dir() -> Path:
    if override := os.environ.get("GHOSTHAND_LOG_DIR"):
        return Path(override)
    # Not under PLUGIN_ROOT: each installed version is its own copy in the plugin cache.
    local = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    return Path(local) / "ghosthand" / "logs"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _redact(tool: str, args: dict) -> dict:
    # set_text may be filling in a password.
    if tool == "set_text" and isinstance(args.get("text"), str):
        return {**args, "text": f"<{len(args['text'])} chars>"}
    return args


class FailureLog:
    """Appends failed calls and Claude's own reports to failures.jsonl, each with the calls before it."""

    def __init__(self, directory: Path, version: str, max_bytes: int = 1_000_000, keep: int = 10):
        self.path = directory / "failures.jsonl"
        self.version = version
        self.max_bytes = max_bytes
        self.session = uuid.uuid4().hex[:8]
        self.recent: deque[dict] = deque(maxlen=keep)

    def call(self, tool: str, args: dict, seconds: float, error: str | None = None, trace: str | None = None) -> None:
        args = _redact(tool, args)
        if error is not None:
            entry = {"source": "ghosthand", "tool": tool, "args": args, "error": error}
            if trace:
                entry["traceback"] = trace
            try:
                self._write(entry)
            except OSError as problem:
                # stderr lands in Claude Code's MCP log; the tool call itself must still go through.
                print(f"ghosthand: could not write {self.path}: {problem}", file=sys.stderr)
        self.recent.append({"time": _now(), "tool": tool, "args": args, "ok": error is None, "ms": round(seconds * 1000)})

    def report(self, what_happened: str, expected: str, tool: str) -> Path:
        self._write({"source": "ai", "tool": tool, "what_happened": what_happened, "expected": expected})
        return self.path

    def _write(self, entry: dict) -> None:
        record = {"time": _now(), "version": self.version, "session": self.session, **entry, "recent": list(self.recent)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._roll()
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def _roll(self) -> None:
        try:
            if self.path.stat().st_size >= self.max_bytes:
                self.path.replace(self.path.with_name("failures.1.jsonl"))
        except OSError:
            # Missing file, or another session has it open: keep appending and try again next time.
            pass
