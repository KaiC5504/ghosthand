# ghosthand build notes

What happened while building ghosthand (2026-10-13), what is left to do, and the decisions
made along the way. The spec (`docs/superpowers/specs/2026-10-12-ghosthand-design.md`) says what
ghosthand must do; this file says where the build ended up and why.

## Status

- Public at https://github.com/KaiC5504/ghosthand (`main`). Plugin version 0.1.6 (the server loads
  its UI Automation backend at start, so a server still running while this repo is updated keeps
  the code it started with).
- 0.1.6 (2026-10-20) fixes what the 2026-10-18/19 failure log showed on BiliFast: `set_text` types
  into Flutter fields, `act` can `scroll` / `scroll_up`, `keys` takes punctuation, and refusals
  say what they mean ("disabled right now" instead of `-0x7ffbfe00`). Plan:
  `docs/superpowers/plans/2026-10-19-ghosthand-0.1.6-fixes.md`.
- Tests: 107 unit tests, 15 live-desktop tests, 2 cookie-export tests, 4 browser smoke checks.
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

## Failure log

`%LOCALAPPDATA%\ghosthand\logs\failures.jsonl` is the first place to look when ghosthand misbehaved. One
JSON record per line, newest at the bottom:

- `"source": "ghosthand"`: a desktop tool call failed. `error` is what Claude was told;
  `traceback` is there for internal errors.
- `"source": "ai"`: Claude called `report_issue` for something no error caught (an action that
  said done but did nothing, a ghosthand-browser failure). `what_happened` and `expected` say what.
- Every record has `time`, `version`, `session` (one per server start) and `recent`: the last ten
  desktop calls before it, with their arguments, whether they worked, and how long they took.

`set_text` is logged as `<N chars>`, never the text. The file rolls over to `failures.1.jsonl` at
1 MB. It sits next to the test Chrome's profile, not in the plugin folder, because every installed
version is its own copy in the plugin cache (until 0.1.2 it was this repo's `logs/`, through a path
in `plugin.json` that only existed on KaiC's PC). Set `GHOSTHAND_LOG_DIR` to log somewhere else.
Playwright's own logs stay in `%LOCALAPPDATA%\ghosthand\playwright-out`.

A quick look in PowerShell:
`Get-Content $env:LOCALAPPDATA\ghosthand\logs\failures.jsonl -Tail 5 | ForEach-Object { $_ | ConvertFrom-Json } | Format-List time, source, tool, error, what_happened`

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
- **An action's fresh read can catch the page mid-animation** (2026-10-15 log: Kazumi's popup menu
  closing re-wrapped the page, so the 关闭 ref in `act`'s result was stale on the next call). `act`,
  `set_text`, `keys` and `launch` now settle like `wait_for` before returning.
- **Flutter's Windows accessibility bridge can break mid-session** ([flutter/flutter#175041](https://github.com/flutter/flutter/issues/175041)), after
  which reads come back frozen or nearly empty (2026-10-15: only the title bar, after a 9-minute
  super-resolution bake). The walk used to swallow the COM error silently; it now ends the read
  with "part of the window did not answer (<hresult>)". Restarting the app fixes the tree.
- **Flutter popup menus ignore a background `escape`**, even with a healthy tree. Pressing the
  menu's own button again closes it.
- **Playwright MCP writes logs and snapshots into the session's working directory** unless given
  `--output-dir`; it now writes to `%LOCALAPPDATA%\ghosthand\playwright-out`.
- **Flutter's Windows accessibility bridge only knows three actions** (2026-10-19, engine
  `flutter_platform_node_delegate.cc`): tap (`DoDefaultAction`), accessibility focus, and
  show-on-screen. So:
  - UIA `SetValue` on a Flutter text field always fails with `E_FAIL` ("Unspecified error"). A
    Flutter field offers ValuePattern only while it has focus. Once it is focused (a `default` tap),
    `WM_CHAR`s posted to the window's `FLUTTERVIEW` type into it with the window in the background,
    emoji included, and posted `end` + backspaces clear it. `set_text` does this when direct text is
    refused, then reads the field back.
  - Flutter exposes no ScrollPattern or ScrollItemPattern (none of 62 Kazumi elements), and its
    `ScrollIntoView` never sets the action type, so it could not scroll even if exposed. Posting
    `WM_MOUSEWHEEL` does scroll, but Flutter reads the position from `GetCursorPos`, so it scrolls
    whatever is under the user's real cursor. Flutter apps cannot be scrolled without the mouse.
- **Classic lists scroll through ScrollPattern**: a WinForms ListBox shows `[default, scroll]`, and
  items scrolled out of view report an empty rectangle (0,0,0,0), not a negative position.
- **The odd negative codes in the log are UIA errors**: `-0x7ffbfe00` is `0x80040200` (element
  disabled) and `-0x7feceaf7` is `0x80131509` (not possible in the current state).

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
11. Every action settles its fresh read (0.15 s more on a still page, up to 1.5 s while it moves).
    Cheaper than a stale ref costing Claude another read; if actions feel slow, this is why.
12. A failed child listing is reported as a note, not an error, since elements also vanish
    mid-animation; the note can therefore show up on a page that was only changing.
13. `keys` maps punctuation for a US keyboard layout. On another layout a posted `/` may arrive as a
    different character; `set_text` is the safe way to put text in.
14. `set_text` clears a field it types into with `end` and one backspace per UTF-16 unit of the old
    text. In a multi-line field `end` only reaches the end of the caret's line, so leftover text
    shows up as a "now holds … instead" error rather than a silent success.
15. A typed `set_text` counts as done only once the field reads back the same text (a password
    field: the same length). A field that cannot be read back is accepted, and the result says it
    was not checked.
16. Posted mouse-wheel messages were rejected for scrolling: Flutter scrolls under the real cursor,
    and a posted mouse message is still mouse input. `scroll` is never picked by `auto`.

## Open items (small, deferred)

- Empty text boxes with no other actions are folded out of reads, and nothing marks which fields
  accept `set_text` (idea: a `[text]` marker).
- `PrintWindow` and `BringWindowToTop` can block on a hung app (no timeout).
- Screenshots include the invisible window border strip (use `DWMWA_EXTENDED_FRAME_BOUNDS`).
- The cut-off note does not say whether the element or the depth limit was hit.
- The cookie popup breaks on a pasted full URL (`https://bilibili.com/`); type the bare domain.
- Reading with another window's ref says "stale" instead of naming that ref's window.
- Window titles in `windows` are not cleaned; an empty window name matches every window.
- After a rebind, the superseded ref stays registered and the two can alternate.
