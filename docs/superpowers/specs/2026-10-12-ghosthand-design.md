# ghosthand — design

Date: 2026-10-12
Status: draft for KaiC's review

## 1. Goal

One Claude Code plugin that lets Claude operate and test anything on KaiC's Windows PC —
native apps (Win32, WinUI/UWP, Flutter, Tauri/WebView2) and Chrome — **without ever touching
his mouse or keyboard**, so he can keep working while it runs. It replaces Orca computer-use,
Windows-MCP and Terminator by keeping what each did best and fixing what each got wrong.

Main use is development: clicking through apps KaiC builds, checking what is on screen,
reading browser console and network output, and reporting bugs.

### Decisions made during brainstorming

| Question | Decision |
|---|---|
| Main use | Development first, across apps and browsers (general purpose) |
| Mouse/keyboard | Never touch them. Accessibility actions only; when only a real click would work, say so or ask |
| Browser | Separate test Chrome with DevTools access (console, network, JS) |
| Test Chrome logins | Permanent profile, log in once; plus an import of cookies from the real Chrome |
| Approach | Hybrid plugin: build the desktop part ourselves, reuse Microsoft's Playwright MCP for the test Chrome |
| Name / location | `ghosthand`, `D:\Repos\Tools\ghosthand` |
| Audience | KaiC only; not published |

## 2. Background: the 2026-10-12 benchmark

Same scripted tasks, run against each tool (calls only, no model thinking time).

| Task | Orca | Windows-MCP | Terminator |
|---|---|---|---|
| Calculator 7×6= (5 runs) | 5/5, 5.3 s | 5/5 but cannot read the result, 3.1 s | 5/5, 5.6 s |
| Kazumi (Flutter): open a card, go back (3) | 0/3, sees nothing inside Flutter | 3/3, 3.3 s | 3/3, 10.0 s |
| Real Chrome: reload BTR on chrome://extensions (3) | 3/3, 8.6 s | 0/3, hangs then crashes | 0/3, 25 s reads, misses the confirmation |
| Real Chrome: open BTR panel on bilibili.com (3) | 2/3, 7.6 s | 1/3, 4.8 s | 3/3, 8.7 s |
| Total | 10/14 | 9/14 | 11/14 |
| Moves the real mouse | never | every click | briefly, restores |

Root causes found, each of which this design answers:

- **Chrome tooltip loop.** A Chrome tooltip makes the UIA tree point back at its own window.
  Windows-MCP recursed until Python crashed; Terminator walked 200 levels (25 s, 1.5 MB).
  Orca survived because it tracks visited elements by runtime id and stops at depth 64.
- **Flutter elements have empty runtime ids** (48 of 49 in Kazumi). Runtime-id-only loop
  detection treats them all as one element. Orca also uses the managed
  `System.Windows.Automation` client, which never sees inside the Flutter view at all; the COM
  `IUIAutomation` client does.
- **Mouse-free actions work in Flutter.** Kazumi's buttons support Invoke; its cards support
  `LegacyIAccessible.DoDefaultAction`. A probe opened a card and came back in ~0.5 s per step
  with zero cursor movement. Kazumi did bring itself to the foreground.
- **Orca's indexes shift** after any UI change; Terminator's refs survive changes; Windows-MCP
  clicks screen coordinates (missed when bilibili's homepage shifted while loading).
- **Terminator's default window management hid Kazumi's window** (2/2), and its by-name
  matching is a substring match ("Clear" clicked "Clear all memory").
- **Windows-MCP's snapshot lists only interactive elements** (cannot read results or toasts)
  and includes the taskbar and every open window's title.
- **Orca's key presses call SetForegroundWindow** before sending, so keys are not background.
  Its text typing posts `WM_CHAR` to the window, which is.

## 3. Architecture

```
ghosthand plugin
├── desktop server (ours)     Python 3.13 + uv, MCP over stdio
│     window finder · reader · references · actions · keys · focus guard · screenshot
├── Playwright MCP (Microsoft, pinned 0.0.83)   test Chrome, permanent profile
├── cookie-export extension (ours)              runs in KaiC's real Chrome
├── skill "ghosthand"                           how Claude should use all of the above
└── bench/                                      acceptance benchmark (today's harness)
```

Plugin packaging: a Claude Code plugin (`.claude-plugin/plugin.json`) that declares both MCP
servers and the skill, installed from a local marketplace. The exact plugin file format is
checked against the current Claude Code docs while planning.

## 4. Desktop server

### 4.1 Commands

| Command | Input | Returns |
|---|---|---|
| `windows` | — | Top-level windows: handle, app, title, which is in front |
| `launch` | app path or name, args | The new window's handle and its first `read` |
| `read` | window, optional subtree ref, optional text filter | Compact view of that one window |
| `act` | ref, action (`auto` default, or press / toggle / select / expand / collapse / default) | Fresh `read` of the window after the action |
| `set_text` | ref, text, submit (bool) | Fresh `read` |
| `keys` | window, key sequence, allow_focus (default false) | Fresh `read` |
| `wait_for` | window, text or ref, appear/disappear, timeout | Fresh `read` once the condition holds, or a timeout error |
| `screenshot` | window | PNG of that window only, captured even when covered |

`read` output: one line per element, indented by depth, e.g.

```
w 3737990 "Kazumi"
  e4  button "历史记录" [press]
  e7  image "药屋少女的呢喃 第三季" [default]
  e19 text "Display is 42"
```

Plain text elements are included (results, toasts, labels). Unnamed elements with nothing to
do are folded away (their children move up), and so are unnamed groups, panes and custom
elements whose only action is `default`. An unnamed element that can be used shows its
top-left position instead of a name (`e8 button @219,27 [press]`) so it can still be told
apart, e.g. a back arrow. The available actions are listed in brackets.

### 4.2 References

- A reference (`e12`) names one element for as long as it exists, across reads, within a
  window. It does not shift when other parts of the UI change.
- Identity is the runtime id when the element has one; otherwise a fingerprint of control
  type, name, automation id, parent reference and sibling position.
- Before every action the server re-resolves the reference and checks the fingerprint. If the
  element is gone or has changed, the action is refused with `stale: read again` — it never
  falls through to a different element.
- One exception keeps a reference alive while only its ancestors change (found while building:
  Kazumi rebuilds the wrappers above a page as it animates in, which broke the back button's
  fingerprint a moment after it was read). The reference moves to an element only when that
  element is new in this read, has the same control type, name and automation id, sits within
  8 px of where the old one was, and is the only such element.

### 4.3 Reader

- COM `IUIAutomation` (via `comtypes` and the UIAutomationClient type library), not the managed
  .NET client — the managed one cannot see inside Flutter.
- Properties are fetched with a `CacheRequest` per subtree (name, control type, automation id,
  bounding rectangle, runtime id, supported patterns, value) to keep reads fast.
- Iterative walk, never recursive. Loop safety: an element is skipped when its runtime id was
  already visited. Elements without one (Flutter's) cannot be proven to repeat:
  `CompareElements` calls two different id-less elements equal when their properties match
  (found while building: Kazumi nests identical wrapper groups, and an ancestor check cut its
  whole page), so a loop through them ends at the caps. Hard caps: depth 64, 2000 nodes per
  read; the output says when a cap was hit.
- Scope is always one window. The taskbar and other windows never appear in a read.

### 4.4 Actions

`act` with `auto` tries, in order, the first pattern the element supports: Invoke, Toggle,
SelectionItem.Select, ExpandCollapse, `LegacyIAccessible.DoDefaultAction`. If none applies the
result is `needs a real click` together with the element's bounds and a suggestion to take a
`screenshot`; the server never moves the mouse.

`set_text` uses ValuePattern.SetValue. A field without it gets a clear error (characters
posted to the window would land wherever that window's keyboard focus is, which may not be
the field); Claude then asks KaiC before using `keys` with `allow_focus`. `submit` posts Enter
in the background.

### 4.5 Keys

Keys are posted to the window (`PostMessage` `WM_KEYDOWN`/`WM_KEYUP`/`WM_CHAR`) without
bringing it to the front. If the app ignores background keys, the result says so and Claude
must ask KaiC before calling again with `allow_focus: true`, which brings the window forward,
sends the keys with `SendInput`, and hands focus back.

### 4.6 Focus guard

Every action records the foreground window first. If the target app pulled itself to the
front (Kazumi does), the server restores the previous foreground window afterwards and reports
whether it managed to.

### 4.7 Screenshot

`PrintWindow` with `PW_RENDERFULLCONTENT` on the target window, so covered windows still
capture correctly. Only on request, only the target window, returned to Claude and not stored.

### 4.8 Errors

Every failure is a short plain-language message plus the next step: `stale: read again`,
`needs a real click`, `window closed: call windows`, `app ignores background keys: ask before
allow_focus`, `timed out waiting for "…"`, `read truncated at 2000 nodes: read a subtree`.

### 4.9 Speed targets

Typical window `read` under 0.5 s; `act` including its fresh read under 0.7 s; server start
under 1 s.

### 4.10 Testability

The reader, references and action selection work against a small element interface. The COM
backend implements it for real windows; a fake backend builds trees in tests, including a
tooltip-style loop, elements without runtime ids, huge trees and elements that disappear
between read and action.

## 5. Test Chrome

- Playwright MCP, pinned to 0.0.83, launched with the installed Google Chrome and
  `--user-data-dir %LOCALAPPDATA%\ghosthand\chrome-profile` (permanent, outside every repo;
  without this flag 0.0.83 uses a throwaway temporary profile). Visible by default; a hidden
  mode is available. Also `--allow-unrestricted-file-access`, which the cookie import needs
  (section 6), and `--caps devtools`.
- Gives console messages, network requests, page snapshots, JavaScript evaluation and
  screenshots. It drives Chrome through DevTools, so it never touches the mouse.
- BTR in the test Chrome: branded Chrome no longer accepts `--load-extension`, so KaiC loads
  `Downloads\BTR` once on the test profile's extensions page; the permanent profile keeps it,
  and the BTR self-reload works there too.
- KaiC's real Chrome stays reachable through the desktop server (accessibility), e.g. for
  reloading BTR on `chrome://extensions`.

## 6. Cookie import

1. `cookie-export` is a Manifest V3 extension KaiC loads in his real Chrome. It has no
   background script; it only runs while its popup is open.
2. The popup lists sites; KaiC ticks the ones he wants. The extension requests host access
   for just those sites (optional host permissions), reads them with `chrome.cookies.getAll`,
   and saves a Playwright storage-state file to `Downloads\ghosthand\`.
3. Claude imports the file with Playwright MCP's `browser_run_code_unsafe`: the code opens
   the file in a throwaway tab, adds its cookies to the test Chrome and returns only a count,
   then Claude deletes the file at once. (0.0.83 has no `browser_set_storage_state`, and it
   echoes the code it runs, so the cookies must never be inside the code — checked: the
   response contains the file path and the count, never a cookie value.)
4. Covers cookie-based logins such as bilibili's `SESSDATA`. Logins kept in a site's
   localStorage are not exported; KaiC signs into those once in the test Chrome.

Rules (also in the skill): cookie files and the profile never go inside a repo
(`.gitignore` covers `*.storage.json` and `chrome-profile/` defensively); Claude never prints
cookie values.

## 7. Skill: how Claude uses ghosthand

- Choose: Chrome web content under development → test Chrome (Playwright MCP); native apps,
  the real Chrome's own UI and anything outside a browser → desktop server.
- Loop: `read` → act by reference → use the returned state → `wait_for` instead of sleeping →
  confirm the outcome from the tool's own output.
- Never ask for the mouse. On `needs a real click`, take a screenshot and tell KaiC.
- Never call `keys` with `allow_focus` without asking KaiC first.
- Cookie handling rules from section 6.

## 8. Testing and acceptance

1. Unit tests (pytest, fake backend, no real apps): loop safety, missing runtime ids, folding,
   caps, reference staleness, action order, error messages.
2. Real-app checks on KaiC's PC: Calculator, Kazumi, real Chrome `chrome://extensions`, test
   Chrome on bilibili including reading the console.
3. Acceptance benchmark: today's harness moves to `bench/` with ghosthand as a fourth
   contender, same four tasks.

Done when:

- **Reliability:** at least 13/14 runs succeed; Kazumi 3/3, extensions page 3/3, Calculator
  5/5 confirmed by ghosthand's own read, bilibili 3/3.
- **Never touches KaiC:** zero cursor movement in every run, zero hidden windows, focus handed
  back after every run.
- **Speed (target, not blocking):** each task at least as fast as the fastest tool that passed
  it on 2026-10-12 — Calculator 3.1 s, Kazumi 3.3 s, extensions page 8.6 s, bilibili 4.8 s.
- Every failure message names the problem and the next step.
- Installs as one plugin; the unit tests and the benchmark each run with one command.

How KaiC checks it himself: run the two commands; then, in a new session, ask Claude to open
Kazumi, open 药屋少女的呢喃 and go back, while he keeps using his mouse.

## 9. Risks

Settled while planning (2026-10-13):

- **Background Enter in Chrome's address bar works**: ValuePattern.SetValue plus a posted
  `WM_KEYDOWN`/`WM_KEYUP` Enter navigated a test window. The real-app checks confirm it also
  works while another window is in front.
- **Playwright MCP 0.0.83 has no `browser_set_storage_state`**: the cookie import uses
  `browser_run_code_unsafe` instead (section 6).
- **Flutter cards report an empty LegacyIAccessible default action** yet DoDefaultAction opens
  them, so `default` is offered for focusable elements with no other mouse-free action.
- **Speed**: the COM walker read Kazumi (55 elements) in 0.1 s and bilibili's homepage (295
  elements as Chrome exposes it) in 0.14 s.

Still open:
- **Apps that ignore `DoDefaultAction` or posted keys.** Measured per app in the real-app
  checks; the `needs a real click` path covers them honestly.
- **Restoring focus.** Windows limits which processes may set the foreground window; the focus
  guard reports when it cannot.

## 10. Out of scope

macOS/Linux; OCR or vision-based clicking; any mouse fallback; recording workflows; exporting
localStorage; DevTools access inside the real Chrome (Playwright's extension mode could add it
later); publishing the plugin.

## 11. Hard floors

- Never commit secrets: cookie files and the Chrome profile live outside repos and are
  git-ignored defensively.
- No surveillance: screenshots only when Claude asks for one, only of the target window,
  never stored or sent anywhere else.
