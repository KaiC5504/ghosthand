import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const here = dirname(fileURLToPath(import.meta.url)).replace(/\\/g, "/");
const WMCP = (process.env.APPDATA + "/Claude/Claude Extensions/ant.dir.cursortouch.windows-mcp").replace(/\\/g, "/");

export const SERVERS = {
  wmcp: { command: "uv", args: ["--directory", WMCP, "run", "windows-mcp"], env: { ...process.env, ANONYMIZED_TELEMETRY: "false" } },
  term: { command: `${here}/node_modules/terminator-mcp-win32-x64-msvc/terminator-mcp-agent.exe`, args: [], env: { ...process.env } },
  gh: { command: "uv", args: ["--directory", `${here}/../desktop`, "run", "--frozen", "ghosthand"], env: { ...process.env } }
};

export async function connect(which) {
  const t0 = performance.now();
  const transport = new StdioClientTransport({ ...SERVERS[which], stderr: "pipe" });
  let stderr = "";
  transport.stderr?.on("data", (d) => { stderr = (stderr + d).slice(-400000); });
  const client = new Client({ name: "bench", version: "1" });
  try {
    await client.connect(transport);
  } catch (error) {
    throw new Error(`${which} connect failed: ${error.message}\n${stderr}`);
  }
  return { client, connectMs: performance.now() - t0, stderr: () => stderr };
}

// Returns { ms, text, isError, bytes, images }
export async function call(client, name, args = {}, timeout = 120000) {
  const t0 = performance.now();
  let result;
  try {
    result = await client.callTool({ name, arguments: args }, undefined, { timeout });
  } catch (error) {
    return { ms: performance.now() - t0, text: `THROW ${error.message}`, isError: true, bytes: 0, images: 0 };
  }
  const ms = performance.now() - t0;
  const parts = result.content || [];
  const text = parts.filter((p) => p.type === "text").map((p) => p.text).join("\n");
  const images = parts.filter((p) => p.type === "image").length;
  const bytes = JSON.stringify(result).length;
  return { ms, text, isError: Boolean(result.isError), bytes, images, raw: result };
}
