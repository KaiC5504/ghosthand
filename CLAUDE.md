# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

ghosthand is a Claude Code plugin with two MCP servers: **ghosthand** (Python, mouse-free
Windows UI Automation) and **ghosthand-browser** (Playwright MCP 0.0.83, pinned, on a test Chrome
with its own profile). Both are declared in `.claude-plugin/plugin.json`. Read
`docs/build-notes.md` before changing behaviour: it records the status, open items, hard-won
lessons and the rulings behind non-obvious code. The spec is
`docs/superpowers/specs/2026-10-12-ghosthand-design.md`.

## Commands

Python lives in `desktop/` (uv, Python 3.14, pytest).

```bash
cd desktop
uv run pytest                                   # unit tests on fakes; "real" tests are excluded by addopts
uv run pytest -m real                           # live desktop: opens Calculator, Kazumi, test Chrome windows
uv run pytest tests/test_desktop.py::test_windows_lists_and_marks_the_front_one
uv run --no-sync pytest                         # when uv can't remove ghosthand.exe (another session's server holds the venv)
cd ../cookie-export && node --test
cd ../scripts && npm install && node browser-smoke.mjs    # ghosthand-browser smoke checks
cd ../bench && npm install && node bench.mjs <calc|kazumi|ext|bili> <runs> [orca|wmcp|term|gh]
node summarize.mjs results/2026-10-12 results/2026-10-13
```

There is no linter or formatter configured.

## Shipping a change

The terminal `claude` runs the plugin from this folder; the desktop app runs a copy in
`~/.claude/plugins/cache/ghosthand/ghosthand/<version>`. To ship: run the tests, bump `version` in
`.claude-plugin/plugin.json`, commit, run `claude plugin install ghosthand@ghosthand`, start a new
session. Reinstalling the same version fails while a session still runs the old copy.

- Don't add `--no-dev` to the server command (the venv would lose pytest).
- Keep the MCP servers in `plugin.json`; a root `.mcp.json` would also load as project config.

## Architecture (desktop server)

`server.py` → `Desktop` (`desktop.py`) → a `Backend` (`uia.py`) and a `Win32` (`win32.py`).

- **Threading/COM:** every UI Automation call runs on one dedicated executor thread
  (`_uia_thread`), whose initializer sets `sys.coinit_flags` to multithreaded *before* importing
  comtypes. Don't import comtypes earlier or call UIA from another thread. `Desktop` is created
  lazily on that thread.
- **Errors:** `GhostError` (`model.py`) is the user-facing failure; its message must tell Claude
  what happened and what to do next. `server._call` turns it into a `ToolError`; any other
  exception becomes "internal error".
- **Reading:** `reader.walk` does a capped walk (64 levels, 2000 elements) into `Node`s in reading
  order; `reader.render` prints lines like `e12 button "Save" [press]`. A `read` with `ref` walks
  that subtree with its own budget, keeping refs stable.
- **Refs (`refs.py`):** `RefTable` keys elements by runtime id, or for Flutter (no runtime id) by a
  fingerprint of parent key, role, name, automation id and sibling index. `rebind` moves a stale
  ref to an identical element only under the strict rules in build-notes decision 4; otherwise
  the error is "stale". Don't use UIA `CompareElements` for identity (it is wrong for Flutter).
- **Actions:** `actions.choose` maps `auto` to the first supported UIA pattern
  (press → toggle → select → expand → default). With none, it raises "needs a real click". Never
  add a mouse fallback.
- **Every mutating call** goes through `Desktop._guarded` (a window closing mid-call counts as
  success), then `_hand_back` (return focus to the user's window if the controlled app stole it,
  but never if the user switched apps themselves), then `_after`, which returns the fresh read. `wait_for`
  also waits until actionable elements stop moving (`_settled`, at most 1.5 s).
- **Keys:** without `allow_focus` they are posted to the window's focused control and modifier
  combos are refused. `allow_focus=true` brings the window to the front.

Unit tests use `tests/fakes.py` (`FakeBackend`, `FakeElement`, `FakeWin`) and inject `sleep`/`clock`
into `Desktop`. Live tests (`-m real`) count *injected* mouse input with a low-level hook to prove
the mouse was never used. The user's own mouse movement doesn't count.

## Other parts

- `skills/ghosthand/SKILL.md`: the skill that tells Claude which server to use and the hard
  rules. Keep it in step with tool behaviour.
- `cookie-export/`: an unpacked Chrome extension that exports a site's cookies to
  `Downloads\ghosthand\cookies.json` for import into the test Chrome. Never read, print or commit
  cookie values (`.gitignore` covers `cookies.json`, `*.storage.json`, `chrome-profile/`).
- `bench/`: Node scripts that compare Orca, Windows-MCP, Terminator and ghosthand (`gh`). Results
  are JSONL per date under `bench/results/`.

## Conventions

- Tool output and error text speak to Claude and call the person at the PC "the user".
- Comments are sparse and explain why (often Windows/Flutter quirks). Keep that style.
- Dependencies are pinned exactly (`pyproject.toml`, `@playwright/mcp@0.0.83`), and the server runs
  with `uv run --frozen`, so update `uv.lock` together with any dependency change.
