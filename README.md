# ghosthand

**Let Claude Code use your Windows apps without touching your mouse.**

ghosthand reads apps through Windows UI Automation and presses buttons through accessibility
actions, not by moving the cursor. You keep using your PC while Claude works.

It is a Claude Code plugin with two MCP servers:

- **ghosthand**: native Windows apps (Win32, WinUI, Flutter) and Chrome's own pages
  such as `chrome://extensions`.
- **ghosthand-browser**: a separate test Chrome with console, network and JavaScript access,
  through Microsoft's [Playwright MCP](https://github.com/microsoft/playwright-mcp).

## Why it's better

Same scripted tasks, run against three popular Windows automation tools:
[Windows-MCP](https://github.com/CursorTouch/Windows-MCP),
[Terminator](https://github.com/mediar-ai/terminator) and
[Orca](https://github.com/stablyai/orca)'s computer use.

| | ghosthand | Orca | Windows-MCP | Terminator |
|---|---|---|---|---|
| Tasks finished | **14/14** | 10/14 | 9/14 | 11/14 |
| Fastest | **on all 4 tasks** | | | |
| Moves your mouse | **never** | never | on every click | briefly, then puts it back |

Per task (runs finished, median time):

| Task | ghosthand | Orca | Windows-MCP | Terminator |
|---|---|---|---|---|
| Calculator: 7 × 6 = | **5/5 · 1.1 s** | 5/5 · 5.3 s | 5/5 · 3.1 s ¹ | 5/5 · 5.6 s |
| Kazumi (a Flutter app): open a show, go back | **3/3 · 2.9 s** | 0/3 | 3/3 · 3.3 s | 3/3 · 10.0 s |
| Chrome: reload an extension on `chrome://extensions` | **3/3 · 1.0 s** | 3/3 · 8.6 s | 0/3 | 0/3 |
| Chrome: open an extension's panel on bilibili.com | **3/3 · 2.7 s** | 2/3 · 7.6 s | 1/3 · 8.1 s | 3/3 · 8.7 s |

¹ Windows-MCP pressed the buttons but could not read the result back.

What makes the difference:

- **It never touches your mouse or keyboard.** Every action is an accessibility action (press,
  toggle, select, expand). If an element has none, ghosthand says "needs a real click" instead
  of grabbing the mouse. The tests count software mouse input during every run: always zero.
- **It doesn't steal your focus.** Keys go to the app in the background. If an app pulls itself
  to the front, ghosthand hands focus back to the window you were using.
- **It sees inside Flutter apps.** Orca saw nothing inside Kazumi. ghosthand uses the COM UI
  Automation client, which can, and keeps stable refs for elements that have no runtime id.
- **It doesn't hang on Chrome.** A Chrome tooltip makes the UI tree point back at itself.
  Windows-MCP recursed until it crashed and Terminator walked 200 levels deep. ghosthand caps
  every read at 64 levels and 2000 elements.
- **Every action proves itself.** Each action returns the window's fresh state, so Claude sees
  whether it worked without another call.
- **Refs stay put.** An element keeps its ref (`e12`) when the page changes. Orca's indexes
  shift after every change, and Windows-MCP clicks screen coordinates, which miss when a page
  moves while loading.

To be fair: the benchmark is small (4 tasks, 3 to 5 runs each, one PC) and was written
alongside ghosthand, which was designed after seeing where the other tools failed on these
same tasks. Its runs were measured just before its final review fixes; the live tests pass on
the final code. Versions tested: Windows-MCP 0.7.2, Terminator 0.24.28, Orca 1.4.221. The
scripts and raw results are in [`bench/`](bench) so you can run it yourself.

## What Claude sees

```
window 8849636 "Kazumi" (kazumi)
  e9 button "历史记录" [press]
  e21 image "药屋少女的呢喃 第三季" [default]
  e50 button @1416,809 [press]
```

One line per element. Claude calls `act` on `e21` and gets the window's new state back.

## Install

You need Windows 10 or 11, [Claude Code](https://github.com/anthropics/claude-code),
[uv](https://docs.astral.sh/uv/), [Node.js](https://nodejs.org/) and Google Chrome.

```bash
claude plugin marketplace add KaiC5504/ghosthand
```

```bash
claude plugin install ghosthand@ghosthand
```

Start a new Claude Code session, then check that both servers show `✔ Connected`:

```bash
claude mcp list
```

The first start downloads ghosthand's Python packages. If it shows as failed, wait a moment
and check again.

## Tools

**ghosthand** (desktop)

| Tool | What it does |
|---|---|
| `windows` | List open windows and which one is in front |
| `launch` | Start an app and read its window |
| `read` | Read one window, one line per element |
| `act` | Use an element: press, toggle, select, expand |
| `set_text` | Put text straight into a field |
| `keys` | Send keys in the background (`enter`, `tab`, `f5`) |
| `wait_for` | Wait until text appears or disappears |
| `screenshot` | A picture of one window, even when it is covered |
| `report_issue` | Log a problem no error caught |

**ghosthand-browser**: Playwright MCP on a test Chrome with its own permanent profile in
`%LOCALAPPDATA%\ghosthand\chrome-profile`. Log in once and it stays logged in. To copy a
site's logins from your real Chrome, load [`cookie-export/`](cookie-export) as an unpacked
extension.

The plugin also installs a skill that teaches Claude which server to use and the rules
(never the mouse; ask before bringing a window to the front).

## Limits

- An element with no accessibility action can't be used. ghosthand says so and never falls back
  to the mouse.
- Key combinations like `ctrl+s` need the window in front, so Claude asks you first.
- If an app ignores background keys, ghosthand can't tell from outside. The fresh read after
  `keys` shows whether they landed.
- A read stops at 2000 elements or 64 levels. Reading again with a ref walks that part with its
  own budget.

## Development

```bash
cd desktop
uv run pytest            # unit tests, no real apps
uv run pytest -m real    # live tests: opens Calculator, Kazumi and test Chrome windows
```

[`docs/build-notes.md`](docs/build-notes.md) has the build status, how to ship a change, and
the reasons behind the non-obvious code. The design spec is in
[`docs/superpowers/specs`](docs/superpowers/specs).

## License

[MIT](LICENSE)
