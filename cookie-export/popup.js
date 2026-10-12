import { toPlaywrightCookies } from "./cookies.js";

const sites = document.getElementById("sites");
const status = document.getElementById("status");

document.getElementById("export").addEventListener("click", async () => {
  const domains = sites.value.split(/[\s,]+/).map((d) => d.trim().replace(/^\.+/, "")).filter(Boolean);
  if (!domains.length) {
    status.textContent = "Type at least one site.";
    return;
  }
  // Must be the first await: Chrome only shows the permission prompt during the click.
  const origins = domains.flatMap((d) => [`https://${d}/*`, `https://*.${d}/*`, `http://${d}/*`, `http://*.${d}/*`]);
  if (!(await chrome.permissions.request({ origins }))) {
    status.textContent = "Permission refused; nothing exported.";
    return;
  }
  const cookies = (await Promise.all(domains.map((domain) => chrome.cookies.getAll({ domain })))).flat();
  const json = JSON.stringify(toPlaywrightCookies(cookies));
  const binary = Array.from(new TextEncoder().encode(json), (byte) => String.fromCharCode(byte)).join("");
  const url = "data:application/json;base64," + btoa(binary);
  await chrome.downloads.download({ url, filename: "ghosthand/cookies.json", conflictAction: "overwrite", saveAs: false });
  status.textContent = `Exported ${cookies.length} cookies from ${domains.join(", ")} to Downloads\\ghosthand\\cookies.json.\nAsk Claude to import them; the file is deleted after.`;
});
