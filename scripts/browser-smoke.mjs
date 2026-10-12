// Checks the Playwright MCP side of the plugin without touching the real profile: console
// messages, and the cookie import path the skill documents (a value never leaves the browser).
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const dir = mkdtempSync(join(tmpdir(), "ghosthand-smoke-"));
const file = join(dir, "cookies.json");
writeFileSync(file, JSON.stringify([{ name: "ghosthand_smoke", value: "SMOKE-SECRET-VALUE", domain: "example.com", path: "/", expires: -1, httpOnly: false, secure: false, sameSite: "Lax" }]));

const client = new Client({ name: "ghosthand-smoke", version: "1" });
await client.connect(new StdioClientTransport({
  command: "node",
  args: ["node_modules/@playwright/mcp/cli.js", "--browser", "chrome", "--isolated", "--headless", "--allow-unrestricted-file-access", "--caps", "devtools"],
}));
const text = (result) => result.content.map((part) => part.text ?? "").join("\n");
let failed = false;
const check = (label, ok) => { console.log(`${ok ? "ok  " : "FAIL"} ${label}`); failed ||= !ok; };

await client.callTool({ name: "browser_navigate", arguments: { url: "https://example.com/" } });
await client.callTool({ name: "browser_evaluate", arguments: { function: "() => console.error('ghosthand smoke console')" } });
check("console messages are readable", text(await client.callTool({ name: "browser_console_messages", arguments: { level: "error" } })).includes("ghosthand smoke console"));

const url = "file:///" + file.replace(/\\/g, "/");
const code = `async (page) => { const tmp = await page.context().newPage(); await tmp.goto(${JSON.stringify(url)}); const cookies = JSON.parse(await tmp.locator("body").innerText()); await tmp.close(); await page.context().addCookies(cookies); return "imported " + cookies.length + " cookies"; }`;
const imported = text(await client.callTool({ name: "browser_run_code_unsafe", arguments: { code } }));
check("cookie import reports a count", imported.includes("imported 1 cookies"));
check("cookie value never appears in the response", !imported.includes("SMOKE-SECRET-VALUE"));
const names = text(await client.callTool({ name: "browser_run_code_unsafe", arguments: { code: "async (page) => (await page.context().cookies('https://example.com')).map((c) => c.name).join(',')" } }));
check("cookie is in the browser", names.includes("ghosthand_smoke"));

await client.close();
rmSync(dir, { recursive: true, force: true });
process.exit(failed ? 1 : 0);
