// node bench.mjs <task> <runs>   tasks: calc | kazumi | ext | bili
// Appends one JSON line per run to out/results.jsonl.
import { appendFileSync, mkdirSync } from "node:fs";
import { execFile, spawn } from "node:child_process";
import { connect, call } from "./servers.mjs";
import { orca, findOrca } from "./orca.mjs";
import { newChromeWindow, sleep, win, startWatcher } from "./util.mjs";
mkdirSync("out", { recursive: true });

const [task, runsArg, onlyTool] = process.argv.slice(2);
const RUNS = Number(runsArg || 3);
const TOOLS = onlyTool ? [onlyTool] : ["orca", "wmcp", "term", "gh"];
const EXT_URL = "chrome://extensions/?id=jcfakgmhohdhbmbcifhlfmiakenjlpcm";
const BILI_URL = "https://www.bilibili.com/";
// Kazumi's popular list changes; set BENCH_KAZUMI_CARD to a card that is on screen today.
const KAZUMI_CARD = process.env.BENCH_KAZUMI_CARD || "药屋少女的呢喃 第三季";

let wmcp = null, term = null, gh = null;
async function ensure(which) {
  if (which === "wmcp" && !wmcp) wmcp = await connect("wmcp");
  if (which === "term" && !term) term = await connect("term");
  if (which === "gh" && !gh) gh = await connect("gh");
}

class Fail extends Error {}
function rec(tool, run) { return { task, tool, run, ok: false, ms: 0, calls: 0, outBytes: 0, mouseMoved: false, note: "" }; }

async function O(r, args) {
  const res = await orca(args);
  r.calls++; r.outBytes += res.bytes;
  if (!res.ok) throw new Fail(`orca ${args[0]}: ${JSON.stringify(res.error).slice(0, 160)}`);
  return res;
}
async function M(r, name, args = {}, timeout = 30000) {
  const res = await call(wmcp.client, name, args, timeout);
  r.calls++; r.outBytes += res.bytes;
  if (res.text.startsWith("THROW")) { wmcp = null; throw new Fail(`wmcp ${name}: ${res.text.slice(6, 120)}`); }
  if (res.isError) throw new Fail(`wmcp ${name} error: ${res.text.slice(0, 160)}`);
  return res;
}
const TERM_DEFAULTS = { verify_element_exists: "", verify_element_not_exists: "", highlight_before_action: false, ui_diff_before_after: false, include_tree_after_action: false, enable_window_management: false };
const TERM_FIELDS = {
  get_window_tree: ["include_tree_after_action", "enable_window_management"],
  click_element: ["verify_element_exists", "verify_element_not_exists", "highlight_before_action", "ui_diff_before_after", "enable_window_management"],
  type_into_element: ["highlight_before_action", "ui_diff_before_after", "enable_window_management"],
  validate_element: ["verify_element_exists", "verify_element_not_exists", "include_tree_after_action"]
};
async function T(r, name, args = {}, timeout = 30000) {
  const base = Object.fromEntries((TERM_FIELDS[name] || []).map((k) => [k, TERM_DEFAULTS[k]]));
  const res = await call(term.client, name, { ...base, ...args }, timeout);
  r.calls++; r.outBytes += res.bytes;
  if (res.text.startsWith("THROW")) {
    if (/Connection closed|Not connected/.test(res.text)) term = null;
    return { ...res, failed: true };
  }
  return res;
}
const termTree = (res) => { try { return JSON.parse(res.text).ui_tree || ""; } catch { return res.text; } };
// "#29 [Button] Seven (bounds…" -> 29. Selector clicks took ~5.8 s each on UWP, so clicks go
// by the index of the last tree read, the same way the other two tools click.
const termIndex = (tree, role, name, last = false) => {
  const hits = tree.split("\n").filter((l) => l.includes(`[${role}] ${name} (`)).map((l) => Number(l.match(/#(\d+)/)?.[1])).filter(Boolean);
  return last ? hits.pop() : hits[0];
};
async function termRead(r, args) {
  const res = await T(r, "get_window_tree", { include_tree_after_action: true, include_window_screenshot: false, include_detailed_attributes: false, ...args });
  if (res.failed) throw new Fail(`tree: ${res.text.slice(0, 150)}`);
  return termTree(res);
}
async function termClick(r, index) {
  const c = await T(r, "click_element", { index, vision_type: "ui_tree" });
  if (c.failed) throw new Fail(`click #${index}: ${c.text.slice(0, 150)}`);
}
async function G(r, name, args = {}, timeout = 30000) {
  const res = await call(gh.client, name, args, timeout);
  r.calls++; r.outBytes += res.bytes;
  if (res.text.startsWith("THROW")) { gh = null; throw new Fail(`gh ${name}: ${res.text.slice(6, 160)}`); }
  if (res.isError) throw new Fail(`gh ${name}: ${res.text.slice(0, 160)}`);
  return res.text;
}
const ghRef = (text, re) => (text.split("\n").map((l) => l.trim()).find((l) => re.test(l)) || "").split(" ")[0] || null;

// WMCP snapshot -> [{ id, window, type, name, x, y }]
function wmcpElements(res) {
  let text = res.text; try { text = JSON.parse(res.text).join("\n"); } catch {}
  const out = [];
  for (const line of text.split("\n")) {
    const m = line.match(/^(\d+)\|([^|]*)\|([^|]*)\|([^|]*)\|\((\d+),(\d+)\)/);
    if (m) out.push({ id: Number(m[1]), window: m[2], type: m[3], name: m[4], x: Number(m[5]), y: Number(m[6]) });
  }
  return { els: out, text };
}

async function poll(fn, tries, gap) {
  for (let i = 0; i < tries; i++) {
    const v = await fn();
    if (v) return v;
    await sleep(gap);
  }
  return null;
}

// ---------- tasks: each returns true when the tool itself verified the outcome ----------

const CALC_KEYS = ["Clear", "Seven", "Multiply by", "Six", "Equals"];
const calc = {
  async orca(r) {
    const W = ["--app", "Calculator", "--no-screenshot"];
    // Orca's indexes shift when the UI changes, so each click uses the state the previous
    // action returned.
    let s = await O(r, ["get-app-state", ...W]);
    for (const k of CALC_KEYS) {
      const el = findOrca(s.text, new RegExp(`button ${k}$`))[0];
      if (!el) throw new Fail(`no ${k}`);
      s = await O(r, ["click", ...W, "--element-index", String(el.index)]);
    }
    return /Display is 42\b/.test(s.text);
  },
  async wmcp(r) {
    await M(r, "App", { mode: "switch", name: "Calculator" });
    const { els } = wmcpElements(await M(r, "Snapshot", { use_vision: false }));
    for (const k of CALC_KEYS) {
      const el = els.find((e) => e.window === "Calculator" && e.type === "Button" && e.name === k);
      if (!el) throw new Fail(`no ${k}`);
      await M(r, "Click", { label: el.id });
    }
    // Its tree has only interactive elements, so the display text is not there; checked
    // afterwards by the neutral reader instead.
    r.note = "self-verify impossible (display text not in snapshot)";
    return null;
  },
  async term(r) {
    const tree = await termRead(r, { process: "ApplicationFrameHost" });
    for (const k of CALC_KEYS) {
      const i = termIndex(tree, "Button", k);
      if (!i) throw new Fail(`no ${k}`);
      await termClick(r, i);
    }
    return /Display is 42\b/.test(await termRead(r, { process: "ApplicationFrameHost" }));
  },
  async gh(r) {
    let text = await G(r, "read", { window: "Calculator" });
    for (const k of CALC_KEYS) {
      const ref = ghRef(text, new RegExp(`^e\\d+ button "${k}"`));
      if (!ref) throw new Fail(`no ${k}`);
      text = await G(r, "act", { ref });
    }
    return /Display is 42\b/.test(text);
  }
};
async function calcNeutralCheck() {
  const s = await orca(["get-app-state", "--app", "Calculator", "--no-screenshot"]);
  return /Display is 42\b/.test(s.text);
}

// Untimed: back to the home grid if a run left a detail page open.
async function kazumiReset() {
  if (!(await kazumiRunning())) { KAZ_H = await kazumiLaunch(); kazumiRelaunches++; }
  else await win("show", KAZ_H);
  await ensure("term");
  const scratch = rec("reset", 0);
  for (let i = 0; i < 3; i++) {
    const tree = await termRead(scratch, { process: "kazumi" });
    if (termIndex(tree, "Image", KAZUMI_CARD)) return;
    const back = termIndex(tree, "Button", "更多操作") && termBack(tree);
    if (!back) throw new Error("kazumi: neither home nor detail page");
    await termClick(scratch, back);
    await sleep(1200);
  }
}

const kazumi = {
  async orca(r) {
    const s = await O(r, ["get-app-state", "--app", "kazumi", "--no-screenshot"]);
    if (!findOrca(s.text, new RegExp(KAZUMI_CARD)).length) throw new Fail(`content not visible (tree: ${s.text.split("\n").length} lines, only the Flutter pane)`);
    return false;
  },
  // 关闭 and 退出 in Kazumi's own title bar close the app. The detail page's way back is the
  // unlabeled button in its top-left corner; 更多操作 shows the detail page is open.
  async wmcp(r) {
    await M(r, "App", { mode: "switch", name: "Kazumi" });
    const { els } = wmcpElements(await M(r, "Snapshot", { use_vision: false }));
    const card = els.find((e) => e.window === "Kazumi" && e.name === KAZUMI_CARD);
    if (!card) throw new Fail(`card not in snapshot (${els.filter((e) => e.window === "Kazumi").length} Kazumi elements)`);
    await M(r, "Click", { label: card.id });
    const detail = await poll(async () => wmcpElements(await M(r, "Snapshot", { use_vision: false })).els.some((e) => e.window === "Kazumi" && e.name === "更多操作"), 8, 400);
    if (!detail) throw new Fail("detail page not seen");
    await sleep(KAZUMI_SETTLE_MS);
    const back = wmcpElements(await M(r, "Snapshot", { use_vision: false })).els
      .filter((e) => e.window === "Kazumi" && e.type === "Button" && e.name === "")
      .sort((a, b) => a.x + a.y - (b.x + b.y))[0];
    if (!back) throw new Fail("no unlabeled back button");
    await M(r, "Click", { label: back.id });
    const home = await poll(async () => wmcpElements(await M(r, "Snapshot", { use_vision: false })).els.find((e) => e.window === "Kazumi" && e.name === KAZUMI_CARD), 8, 400);
    return Boolean(home);
  },
  async term(r) {
    const P = { process: "kazumi" };
    const card = termIndex(await termRead(r, P), "Image", KAZUMI_CARD);
    if (!card) throw new Fail("card not in tree");
    await termClick(r, card);
    const open = await poll(async () => termIndex(await termRead(r, P), "Button", "更多操作"), 8, 400);
    if (!open) throw new Fail("detail page not seen");
    await sleep(KAZUMI_SETTLE_MS);
    const back = termBack(await termRead(r, P));
    if (!back) throw new Fail("no unlabeled back button");
    await termClick(r, back);
    return Boolean(await poll(async () => termIndex(await termRead(r, P), "Image", KAZUMI_CARD), 8, 400));
  },
  async gh(r) {
    const text = await G(r, "read", { window: "kazumi" });
    const card = ghRef(text, new RegExp(`^e\\d+ image "${KAZUMI_CARD}"`));
    if (!card) throw new Fail("card not in read");
    await G(r, "act", { ref: card });
    const detail = await G(r, "wait_for", { window: "kazumi", text: "更多操作", timeout: 5 });
    const back = detail.split("\n").map((l) => l.trim().match(/^(e\d+) button @(-?\d+),(-?\d+)/)).filter(Boolean)
      .sort((a, b) => (+a[2] + +a[3]) - (+b[2] + +b[3]))[0];
    if (!back) throw new Fail("no unlabeled back button");
    await sleep(KAZUMI_SETTLE_MS);
    await G(r, "act", { ref: back[1] });
    await G(r, "wait_for", { window: "kazumi", text: KAZUMI_CARD, timeout: 5 });
    return true;
  }
};
// The unlabeled button nearest the top-left corner: "#8 [Button] (bounds: [219,27,57,57]".
function termBack(tree) {
  return tree.split("\n").map((l) => l.match(/#(\d+) \[Button\] \(bounds: \[(\d+),(\d+)/)).filter(Boolean)
    .map((m) => ({ i: Number(m[1]), d: Number(m[2]) + Number(m[3]) })).sort((a, b) => a.d - b.d)[0]?.i;
}
const KAZUMI_SETTLE_MS = 800;
const kazumiRunning = async () => Boolean((await win("list", 0, "kazumi")).trim()) || /kazumi\.exe/i.test(await new Promise((res) => execFile("tasklist", ["/fi", "imagename eq kazumi.exe"], (_e, o) => res(String(o)))));
async function kazumiLaunch() {
  spawn("D:/Tools/Kazumi/kazumi.exe", [], { detached: true, stdio: "ignore", cwd: "D:/Tools/Kazumi" }).unref();
  await sleep(9000);
  return Number((await win("list", 0, "kazumi")).split("\t")[0]);
}

// Chrome tasks share: open URL in the fresh window, wait for a marker, click it, verify.
function chromeTask({ url, orcaMarker, orcaVerify, wmcpMarker, wmcpVerify, termMarker, termTitle, termVerify, ghWait, ghMarker, ghVerify, pickLast }) {
  return {
    async orca(r, w) {
      const W = ["--app", "chrome", "--window-id", String(w.h), "--no-screenshot"];
      const s = await O(r, ["get-app-state", ...W]);
      const bar = findOrca(s.text, /edit Address and search bar/)[0];
      await O(r, ["set-value", ...W, "--element-index", String(bar.index), "--value", url]);
      await O(r, ["press-key", ...W, "--key", "Return"]);
      const target = await poll(async () => { const m = findOrca((await O(r, ["get-app-state", ...W])).text, orcaMarker); return pickLast ? (m.length > 1 && m.pop()) : m[0]; }, 20, 500);
      if (!target) throw new Fail("marker never appeared");
      // Every tool gets the same few tries to see the result: a panel can still be animating in.
      const v = await O(r, ["click", ...W, "--element-index", String(target.index)]);
      if (orcaVerify.test(v.text)) return true;
      return Boolean(await poll(async () => orcaVerify.test((await O(r, ["get-app-state", ...W])).text), VERIFY_TRIES, 500));
    },
    async wmcp(r, w) {
      await M(r, "App", { mode: "switch", name: w.title });
      const bar = await poll(async () => wmcpElements(await M(r, "Snapshot", { use_vision: false })).els.find((e) => e.type === "Edit" && e.name === "Address and search bar" && e.window === w.title), 3, 500);
      if (!bar) throw new Fail("no address bar");
      await M(r, "Type", { label: bar.id, text: url, clear: true, press_enter: true });
      const target = await poll(async () => { const m = wmcpElements(await M(r, "Snapshot", { use_vision: false })).els.filter((e) => wmcpMarker(e)); return pickLast ? (m.length > 1 && m.pop()) : m[0]; }, 20, 500);
      if (!target) throw new Fail("marker never appeared");
      await M(r, "Click", { label: target.id });
      return Boolean(await poll(async () => wmcpVerify(wmcpElements(await M(r, "Snapshot", { use_vision: false }))), VERIFY_TRIES, 500));
    },
    async term(r, w) {
      const P = { process: "chrome" };
      await termRead(r, { ...P, title: w.title });
      const t = await T(r, "type_into_element", { ...P, window_selector: `name:${w.title}`, selector: "role:Edit|name:Address and search bar", text_to_type: `${url}{Enter}`, clear_before_typing: true });
      if (t.failed) throw new Fail(`type url: ${t.text.slice(0, 150)}`);
      const target = await poll(async () => termIndex(await termRead(r, { ...P, title: termTitle }), "Button", termMarker, pickLast), 20, 500);
      if (!target) throw new Fail("marker never appeared");
      await termClick(r, target);
      return Boolean(await poll(async () => termVerify.test(await termRead(r, { ...P, title: termTitle })), VERIFY_TRIES, 500));
    },
    async gh(r, w) {
      const win = String(w.h);
      const bar = ghRef(await G(r, "read", { window: win }), /^e\d+ edit "Address and search bar"/);
      if (!bar) throw new Fail("no address bar");
      await G(r, "set_text", { ref: bar, text: url, submit: true });
      const page = await G(r, "wait_for", { window: win, text: ghWait, timeout: 10 });
      const hits = page.split("\n").map((l) => l.trim()).filter((l) => ghMarker.test(l));
      const target = pickLast ? (hits.length > 1 && hits.pop()) : hits[0];
      if (!target) throw new Fail("marker never appeared");
      const after = await G(r, "act", { ref: target.split(" ")[0] });
      if (ghVerify.test(after)) return true;
      try {
        await G(r, "wait_for", { window: win, text: ghVerify.source, timeout: 2 });
        return true;
      } catch {
        return false;
      }
    }
  };
}
const VERIFY_TRIES = 4;

const ext = chromeTask({
  url: EXT_URL,
  orcaMarker: /button Reload$/, orcaVerify: /text Reloaded/, pickLast: true,
  wmcpMarker: (e) => e.type === "Button" && e.name === "Reload", wmcpVerify: (v) => /Reloaded/.test(v.text),
  termMarker: "Reload", termTitle: "Extensions", termVerify: /Reloaded/,
  ghWait: "Inspect views", ghMarker: /^e\d+ button "Reload"/, ghVerify: /Reloaded/
});
const bili = chromeTask({
  url: BILI_URL,
  orcaMarker: /button 线程撕裂者设置$/, orcaVerify: /目前总线程/,
  wmcpMarker: (e) => e.type === "Button" && e.name === "线程撕裂者设置", wmcpVerify: (v) => v.els.some((e) => /Debug 模式/.test(e.name)),
  termMarker: "线程撕裂者设置", termTitle: "bilibili", termVerify: /目前总线程/,
  ghWait: "线程撕裂者设置", ghMarker: /^e\d+ button "线程撕裂者设置"/, ghVerify: /目前总线程/
});

const TASKS = { calc, kazumi, ext, bili };
const impl = TASKS[task];
if (!impl) { console.log("unknown task"); process.exit(1); }

let KAZ_H = task === "kazumi" ? Number((await win("list", 0, "kazumi")).split("\t")[0]) : 0;
let kazumiRelaunches = 0;
const watcher = startWatcher();
await sleep(1500);
for (let run = 1; run <= RUNS; run++) {
  const order = TOOLS.map((_, i) => TOOLS[(i + run - 1) % TOOLS.length]);
  for (const tool of order) {
    const r = rec(tool, run);
    let w = null;
    try {
      if (tool !== "orca") await ensure(tool);
      if (task === "ext" || task === "bili") { w = await newChromeWindow(); await sleep(800); }
      if (task === "kazumi") { await kazumiReset(); await sleep(500); }
      const t0 = performance.now();
      try {
        r.ok = await impl[tool](r, w);
      } catch (error) {
        r.ok = false; r.note = (r.note ? r.note + "; " : "") + (error instanceof Fail ? error.message : `crash: ${error.message}`);
      }
      const t1 = performance.now();
      r.ms = Math.round(t1 - t0);
      Object.assign(r, watcher.between(t0, t1));
      if (task === "calc") r.neutralOk = await calcNeutralCheck();
      if (task === "kazumi" && !(await kazumiRunning())) r.note = (r.note ? r.note + "; " : "") + "KAZUMI EXITED during run";
    } finally {
      if (w) { await win("close", w.h); await sleep(1500); }
    }
    console.log(JSON.stringify(r));
    appendFileSync("out/results.jsonl", JSON.stringify(r) + "\n");
  }
}
watcher.stop();
await wmcp?.client.close().catch(() => {});
await term?.client.close().catch(() => {});
await gh?.client.close().catch(() => {});
process.exit(0);
