---
name: ghosthand
description: Use when operating or testing anything on KaiC's Windows PC — native apps (Win32, WinUI, Flutter like Kazumi, Tauri), the real Chrome's own pages such as chrome://extensions, or web pages under development in the ghosthand test Chrome. Covers which tool to use, the read-act loop, never using the mouse, asking before focus, and importing cookies into the test Chrome.
---

# ghosthand

Two MCP servers come with this plugin:

- **ghosthand** (desktop): `windows`, `launch`, `read`, `act`, `set_text`, `keys`, `wait_for`, `screenshot`. Works on any Windows app and on the real Chrome's own UI.
- **ghosthand-browser** (Playwright MCP 0.0.83): a separate test Chrome with its own permanent profile, with console messages, network requests, JavaScript and page snapshots.

## Which one

- A web page you are building or debugging, or anything needing console/network/JS → **ghosthand-browser**.
- Native apps, the real Chrome's own pages (chrome://extensions, settings), Kazumi, Calculator, installers → **ghosthand**.

## The desktop loop

1. `read` the window (a number from `windows`, an app name like `kazumi`, or part of a title). Lines look like `e12 button "Save" [press]`; unnamed controls show their position, e.g. `e8 button @219,27 [press]`.
2. `act` on a ref (or `set_text` for fields). Each action returns the window's fresh state — read that instead of calling `read` again.
3. Use `wait_for` for anything that loads or animates. Never sleep.
   `keys` cannot tell whether the app took them: check the fresh read it returns.
4. Confirm the outcome from the tool's own output before saying something worked.

Refs stay valid while their element exists. `stale: … Read the window again` means the element changed or went away: read again and pick the new ref.

## Hard rules

- ghosthand never moves the mouse. On `needs a real click`, take a `screenshot`, show KaiC, and say what needs clicking.
- `keys` with `allow_focus=true` brings a window to the front. Ask KaiC before every use.
- In Kazumi, `关闭` and `退出` in the title bar close the whole app. The way back from a detail page is the unlabeled button at the top left.

## Test Chrome

- The profile lives in `%LOCALAPPDATA%\ghosthand\chrome-profile` and keeps logins between sessions.
- To test BTR there, KaiC loads `Downloads\BTR` once on the test Chrome's `chrome://extensions` (Load unpacked); the profile keeps it.

## Importing cookies from KaiC's real Chrome

1. KaiC clicks the "ghosthand cookie export" extension in his real Chrome and exports the sites he wants. The file lands at `Downloads\ghosthand\cookies.json`.
2. Find the Downloads folder: `(New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path`.
3. Import with `browser_run_code_unsafe`, using this code with the real path in forward slashes:

```js
async (page) => {
  const tmp = await page.context().newPage();
  await tmp.goto("file:///C:/Users/KaiChuan/Downloads/ghosthand/cookies.json");
  const cookies = JSON.parse(await tmp.locator("body").innerText());
  await tmp.close();
  await page.context().addCookies(cookies);
  return `imported ${cookies.length} cookies`;
}
```

4. Delete the file at once: `Remove-Item "<Downloads>\ghosthand\cookies.json"` and confirm it is gone.

Never open, read, print or return the cookie file's contents or any cookie value. The code above returns only a count, and Playwright echoes only the code, which holds no cookies.
