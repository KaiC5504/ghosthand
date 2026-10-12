# ghosthand

Mouse-free control of Windows apps and a DevTools test Chrome, as one Claude Code plugin.
It reads one window at a time through Windows UI Automation, gives every element a short
ref, and uses apps only through accessibility actions — it never moves your mouse, so you
can keep working while Claude drives.

## Install

```bash
claude plugin marketplace add D:/Repos/Tools/ghosthand
claude plugin install ghosthand@ghosthand
uv --directory D:/Repos/Tools/ghosthand/desktop sync --frozen
claude mcp list
```

`plugin:ghosthand:ghosthand` and `plugin:ghosthand:ghosthand-browser` should both show
`✔ Connected`. The test Chrome keeps its profile in `%LOCALAPPDATA%\ghosthand\chrome-profile`
and its logs, snapshots and downloads in `%LOCALAPPDATA%\ghosthand\playwright-out`.

### After changing the code

The terminal `claude` runs the plugin straight from this repo, but the desktop app runs the
copy made at install time in `~/.claude/plugins/cache/ghosthand/ghosthand/<version>`. To ship a
change to both, bump `version` in `.claude-plugin/plugin.json`, commit, then:

```bash
claude plugin install ghosthand@ghosthand
```

and start a new session. (Reinstalling the same version fails while any open session is still
running the old copy, which is why the version goes up.)

## What Claude gets

- **ghosthand** (desktop): `windows`, `launch`, `read`, `act`, `set_text`, `keys`, `wait_for`,
  `screenshot`. Works on native apps (Win32, WinUI, Flutter such as Kazumi) and on the real
  Chrome's own pages such as `chrome://extensions`.
- **ghosthand-browser**: Playwright MCP 0.0.83 on a separate Chrome with its own permanent
  profile: console messages, network requests, JavaScript and page snapshots.
- **skills/ghosthand**: tells Claude which one to use, the read → act → wait_for loop, and the
  hard rules (never the mouse; ask before bringing a window to the front).
- **cookie-export/**: load it unpacked in your real Chrome to copy a site's logins into the
  test Chrome. Claude imports the file without ever seeing a cookie value, then deletes it.

A read looks like this:

```
window 8849636 "Kazumi" (kazumi)
  e9 button "历史记录" [press]
  e21 image "药屋少女的呢喃 第三季" [default]
  e50 button @1416,809 [press]
```

## Tests

```bash
cd desktop
uv run pytest            # unit tests, no real apps
uv run pytest -m real    # live desktop: Calculator, Kazumi, two test Chrome windows
cd ../cookie-export && node --test
cd ../scripts && npm install && node browser-smoke.mjs
```

The live tests open Calculator and their own Chrome windows, open a Kazumi card and come
back, and reload BTR on `chrome://extensions`. Keep using your PC while they run: the mouse
check counts only input injected by software, not your own hand.

## Benchmark

`bench/` is the 2026-10-12 comparison of Orca, Windows-MCP and Terminator with ghosthand
(`gh`) added: same scripted tasks, tool calls only, no model thinking time.

```bash
cd bench && npm install
node bench.mjs <calc|kazumi|ext|bili> <runs> [tool]
node summarize.mjs results/2026-10-12 results/2026-10-13
```

Results (`results/2026-10-13` is ghosthand, run on 2026-10-13):

```
== calc
orca  done 5/5 self-verified 5/5 median 5.3s  cursor-moved 0/5
wmcp  done 5/5 self-verified 0/5 median 3.1s  cursor-moved 5/5
term  done 5/5 self-verified 5/5 median 5.6s  cursor-moved 0/5
gh    done 5/5 self-verified 5/5 median 1.1s  cursor-moved 0/5 injected 0/5

== kazumi
orca  done 0/3 self-verified 0/3 median 0.4s  cursor-moved 0/3
wmcp  done 3/3 self-verified 3/3 median 3.3s  cursor-moved 3/3
term  done 3/3 self-verified 3/3 median 10.0s cursor-moved 0/3
gh    done 3/3 self-verified 3/3 median 2.9s  cursor-moved 0/3 injected 0/3

== ext (reload BTR on chrome://extensions)
orca  done 3/3 self-verified 3/3 median 8.6s  cursor-moved 0/3
wmcp  done 0/3 self-verified 0/3 median 34.2s cursor-moved 3/3
term  done 0/3 self-verified 0/3 median 31.6s cursor-moved 0/3
gh    done 3/3 self-verified 3/3 median 1.0s  cursor-moved 0/3 injected 0/3

== bili (open BTR's panel on bilibili.com)
orca  done 2/3 self-verified 2/3 median 7.6s  cursor-moved 0/3
wmcp  done 1/3 self-verified 1/3 median 8.1s  cursor-moved 3/3
term  done 3/3 self-verified 3/3 median 8.7s  cursor-moved 0/3
gh    done 3/3 self-verified 3/3 median 2.7s  cursor-moved 0/3 injected 0/3
```

ghosthand: 14/14, fastest on every task, never touched the mouse. "injected" counts mouse
input sent by software during a run (the 2026-10-12 runs predate that counter). Kazumi pulls
itself to the front when used; ghosthand hands focus back each time, which is why its Kazumi
rows show focus changes.

## Known limits

- Apps that offer no accessibility action for an element get "needs a real click";
  ghosthand never falls back to the mouse.
- Key combinations (ctrl+s) need the window in front: Claude asks before doing that.
- Some apps pull themselves to the front when used; ghosthand hands focus back, and says so
  when Windows refuses (seen once, right after Kazumi restored itself from minimised). If you
  switched to another app yourself during an action, it leaves you there.
- Background keys go to the window's focused control. An app that ignores them cannot be
  detected from outside; the fresh read after `keys` shows whether they landed.
- `wait_for` waits until the page stops moving, up to 1.5 s more on a page that never does
  (an always-running animation).
- Elements without a runtime id (Flutter) are known by a fingerprint. When only their
  wrappers change, a ref moves to an identical element of the same size at the same spot that
  was never on screen with it, and only from the window's previous read; anything less certain
  is refused as stale.
- A read stops at 2000 elements or 64 levels; reading again with a ref walks that part with its
  own 2000-element budget.
- The server takes about 1.3 s to start; 1 s of that is the MCP Python SDK loading.
- The installed copy includes this folder's venv and `node_modules` (about 110 MB per version);
  old version folders in the plugin cache can be deleted once no session uses them.
- The benchmark table above was measured before the final review fixes (focus, keys, subtree
  reads, rebinding); the live tests passed on the final code.
