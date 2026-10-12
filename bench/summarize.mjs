// node summarize.mjs <results dir>...   e.g. node summarize.mjs results/2026-10-12 out
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const med = (a) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor((s.length - 1) / 2)] : NaN; };
const rows = process.argv.slice(2).flatMap((dir) => readdirSync(dir).filter((f) => f.endsWith(".jsonl"))
  .flatMap((f) => readFileSync(join(dir, f), "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l))));
// Runs from before the injected-input counter existed only know whether the cursor moved.
const injected = (r) => r.every((x) => x.mouseInjected !== undefined) ? `${r.filter((x) => x.mouseInjected > 0).length}/${r.length}` : "n/a";
for (const task of ["calc", "kazumi", "ext", "bili"]) {
  const forTask = rows.filter((r) => r.task === task);
  if (!forTask.length) continue;
  console.log(`\n== ${task}`);
  for (const tool of [...new Set(forTask.map((r) => r.tool))]) {
    const r = forTask.filter((x) => x.tool === tool);
    const done = r.filter((x) => x.ok === true || (x.ok === null && x.neutralOk));
    console.log(tool.padEnd(5), `done ${done.length}/${r.length}`, `self-verified ${r.filter((x) => x.ok === true).length}/${r.length}`,
      `median ${(med(r.map((x) => x.ms)) / 1000).toFixed(1)}s`, `ok-median ${(med(done.map((x) => x.ms)) / 1000).toFixed(1)}s`,
      `calls ${med(r.map((x) => x.calls))}`, `out ${(med(r.map((x) => x.outBytes)) / 1024).toFixed(1)}KB`,
      `cursor-moved ${r.filter((x) => x.mouseMoved).length}/${r.length}`, `injected ${injected(r)}`,
      `focus ${r.filter((x) => x.focusChanges).length}/${r.length}`);
  }
}
