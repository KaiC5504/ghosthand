import { execFile } from "node:child_process";

// Runs one `orca computer` command; returns { ms, ok, result, error, bytes, text }.
export function orca(args, timeout = 120000) {
  return new Promise((resolve) => {
    const t0 = performance.now();
    execFile("orca", ["computer", ...args, "--json"], { shell: true, timeout, maxBuffer: 64 * 1024 * 1024, windowsHide: true }, (error, stdout) => {
      const ms = performance.now() - t0;
      let json = null;
      try { json = JSON.parse(stdout); } catch (_e) {}
      const text = json?.result?.snapshot?.treeText || "";
      resolve({ ms, ok: Boolean(json?.ok), result: json?.result, error: json?.error || (json ? null : String(error?.message || stdout).slice(0, 500)), bytes: stdout.length, text });
    });
  });
}

// "12 button Reload" lines -> [{ index, line }]
export function findOrca(text, re) {
  return text.split("\n").filter((l) => re.test(l)).map((l) => ({ index: Number(l.trim().split(" ")[0]), line: l.trim() }));
}
