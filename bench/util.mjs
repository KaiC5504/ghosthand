import { execFile, spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// "show" runs without windowsHide: ShowWindow from a process started hidden turns into SW_HIDE.
export function win(op, h = 0, arg = "") {
  return new Promise((resolve) => {
    execFile("powershell", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", join(here, "win.ps1"), op, String(h), arg], { windowsHide: op !== "show" }, (_e, out) => resolve(String(out).trim()));
  });
}

export async function chromeWindows() {
  const out = await win("list", 0, "chrome");
  return out.split(/\r?\n/).filter(Boolean).map((l) => { const [h, ...t] = l.split("\t"); return { h: Number(h), title: t.join("\t") }; });
}

// Opens a fresh Chrome window at about:blank and returns its handle; the user's windows are untouched.
export async function newChromeWindow() {
  const before = new Set((await chromeWindows()).map((w) => w.h));
  spawn("C:/Program Files/Google/Chrome/Application/chrome.exe", ["--new-window", "about:blank"], { detached: true, stdio: "ignore" }).unref();
  for (let i = 0; i < 40; i++) {
    await sleep(250);
    const fresh = (await chromeWindows()).filter((w) => !before.has(w.h));
    if (fresh.length) return fresh[0];
  }
  throw new Error("no new chrome window");
}

export async function cursor() { return win("cursor"); }

// Samples the cursor, the foreground window and the injected-mouse count every 40 ms for the whole benchmark.
export function startWatcher() {
  const samples = [];
  const ps = spawn("powershell", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", join(here, "watch.ps1")], { windowsHide: true });
  let buf = "";
  ps.stdout.on("data", (d) => {
    buf += d;
    const lines = buf.split(/\r?\n/); buf = lines.pop();
    for (const l of lines) { const [x, y, fg, injected] = l.split(","); if (fg) samples.push({ t: performance.now(), pos: `${x},${y}`, fg, injected: Number(injected) || 0 }); }
  });
  return {
    between(t0, t1) {
      const s = samples.filter((x) => x.t >= t0 - 60 && x.t <= t1 + 60);
      return { mouseMoved: new Set(s.map((x) => x.pos)).size > 1, mouseInjected: s.length ? s[s.length - 1].injected - s[0].injected : 0, focusChanges: s.reduce((n, x, i) => n + (i && x.fg !== s[i - 1].fg ? 1 : 0), 0), samples: s.length };
    },
    stop() { ps.kill(); }
  };
}
