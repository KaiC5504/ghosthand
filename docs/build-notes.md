# ghosthand build notes

What happened while building ghosthand (2026-10-13), what is left to do, and the decisions
made along the way. The spec (`docs/superpowers/specs/2026-10-12-ghosthand-design.md`) says what
ghosthand must do; this file says where the build ended up and why.

## Status

- Merged to `main` (no remote). Installed as plugin `ghosthand@ghosthand` version 0.1.1.
- Tests: 73 unit tests, 13 live-desktop tests, 2 cookie-export tests, 4 browser smoke checks — all
  passing on the final code.
- Benchmark (measured just before the final review fixes): 14/14 runs, fastest tool on every task,
  zero mouse input. See the README.
- A fresh reviewer checked the whole branch; its one critical and seven important findings are
  fixed. Smaller ones are listed under "Open items" below.

## Still to do (KaiC)

1. **Load the cookie exporter**: `chrome://extensions` in your real Chrome → Developer mode →
   Load unpacked → `D:\Repos\Tools\ghosthand\cookie-export`. The first export asks for site
   permission; click Allow. Until then the cookie import is tested only with a fake cookie.
2. **Try it yourself**: start a new session in the desktop app and ask Claude to open Kazumi, open
   药屋少女的呢喃 and go back, while you keep using your mouse.
3. **Optional**: re-run the benchmark on the final code when you are away from the PC (it opens
   Kazumi and Chrome windows):
   `cd bench && node bench.mjs calc 5 gh` (then `kazumi 3`, `ext 3`, `bili 3`), and
   `node summarize.mjs results/2026-10-12 out`.
4. **Optional**: delete old plugin copies in `~/.claude/plugins/cache/ghosthand/ghosthand/` (0.1.0
   now, older versions later) once no Claude session is using them.
5. Done 2026-10-13: the global CLAUDE.md now says "ghosthand first" (old version backed up at
   `~/.claude/CLAUDE.md.bak-2026-10-13-orca`).

## How to ship a change

The terminal `claude` runs the plugin straight from this folder, but the desktop app runs the
copy made at install time in `~/.claude/plugins/cache/ghosthand/ghosthand/<version>`. So:

1. Change the code, run `cd desktop && uv run pytest` (add `-m real` for the live checks).
2. Bump `version` in `.claude-plugin/plugin.json` and commit.
3. `claude plugin install ghosthand@ghosthand`, then start a new session.

Reinstalling the *same* version fails while any open session still runs the old copy, which is
why the version goes up. If `uv run` says it cannot remove `ghosthand.exe`, another session's
server is using this folder's venv; run tests with `uv run --no-sync pytest` instead.

Do not add `--no-dev` to the server command (this folder's venv would lose pytest), and keep the
MCP servers inside `plugin.json` (a root `.mcp.json` is also loaded as a project config here).

## Things learned the hard way

- **Windows' `CompareElements` is useless for Flutter.** It calls two different elements without a
  runtime id "equal" when their properties match. Kazumi nests identical wrapper groups, so a loop
  check based on it deleted most of the page. Loops through id-less elements now end at the
  depth/element caps instead.
- **comtypes sets up COM in whichever thread first imports it.** The server's UI Automation thread
  must set `sys.coinit_flags` before importing comtypes, or every tool call fails. The unit tests
  hid this because pytest imported comtypes earlier; a test now starts a fresh process.
- **Kazumi's page animation re-wraps elements and slides the back button in.** A ref read
  mid-animation goes stale a moment later. `wait_for` now returns only once the page stops moving
  (up to 1.5 s), and a stale ref may move to an identical element in the same spot (see rulings).
- **Windows drops zero-distance mouse events before hooks see them**, so "did software touch the
  mouse" can only be checked by counting injected events while real ones happen. Tests and the
  benchmark count injected input, so KaiC moving his own mouse never fails a run.
- **Classic windows (forms, dialogs, installers) ignore keys posted to the frame.** Keys now go to
  the window's focused control.
- **After Kazumi restores itself from minimised, Windows may name its inner `FLUTTERVIEW` as the
  foreground window**, and once refused to hand focus back. ghosthand reports this when it happens.
- **Playwright MCP writes logs and snapshots into the session's working directory** unless given
  `--output-dir`; it now writes to `%LOCALAPPDATA%\ghosthand\playwright-out`.

## Decisions made during the build

Each with what it costs if it turns out wrong.

1. Python 3.14 instead of the spec's 3.13 (latest stable). Fix: change `.python-version`.
2. No loop detection for elements without a runtime id; they end at the caps. A real loop there
   gives a long, truncated read instead of stopping early.
3. Server start is 1.3 s against the 1 s target; 1 s is the MCP Python SDK loading. Claude waits
   0.3 s longer once per session.
4. A stale ref moves to another element only if that element is new since the old one was seen,
   has the same type/name/id, the same size and position (within 8 px), is the only match, and
   the old ref was in the window's previous read. An identical unnamed button replacing the old
   one in exactly that spot could be pressed instead of a "stale" refusal.
5. `wait_for` waits until the usable elements stop moving, at most 1.5 s more. Slower on pages that
   never stop animating.
6. Focus is handed back only when the controlled app (same process) took it; if KaiC switched to
   another app himself, he stays there.
7. An action whose window closes during the call is a success even if the app reports an error
   as it goes.
8. `keys` cannot detect an app ignoring background keys; the fresh read it returns is the proof.
9. Live tests open their own windows (Calculator, a throwaway form, test Chrome windows) instead of
   relying on whatever is in front.
10. The cookie exporter was not installed for KaiC: granting site permission in his real Chrome is
    his call.

## Open items (small, deferred)

- Empty text boxes with no other actions are folded out of reads, and nothing marks which fields
  accept `set_text` (idea: a `[text]` marker).
- If a button's pattern vanishes between read and act, the error says "internal error" instead of
  "stale".
- `PrintWindow` and `BringWindowToTop` can block on a hung app (no timeout).
- Screenshots include the invisible window border strip (use `DWMWA_EXTENDED_FRAME_BOUNDS`).
- The cut-off note does not say whether the element or the depth limit was hit.
- The cookie popup breaks on a pasted full URL (`https://bilibili.com/`); type the bare domain.
- Reading with another window's ref says "stale" instead of naming that ref's window.
- Window titles in `windows` are not cleaned; an empty window name matches every window.
- After a rebind, the superseded ref stays registered and the two can alternate.
