import assert from "node:assert/strict";
import { test } from "node:test";
import { toPlaywrightCookies } from "./cookies.js";

test("session and persistent cookies keep their meaning", () => {
  const out = toPlaywrightCookies([
    { name: "SESSDATA", value: "v1", domain: ".bilibili.com", path: "/", session: false, expirationDate: 1790000000.5, httpOnly: true, secure: true, sameSite: "no_restriction" },
    { name: "buvid3", value: "v2", domain: "www.bilibili.com", path: "/", session: true, httpOnly: false, secure: false, sameSite: "unspecified" },
  ]);
  assert.deepEqual(out, [
    { name: "SESSDATA", value: "v1", domain: ".bilibili.com", path: "/", expires: 1790000000, httpOnly: true, secure: true, sameSite: "None" },
    { name: "buvid3", value: "v2", domain: "www.bilibili.com", path: "/", expires: -1, httpOnly: false, secure: false, sameSite: "Lax" },
  ]);
});

test("strict and lax map straight across", () => {
  const out = toPlaywrightCookies([
    { name: "a", value: "", domain: "x.com", path: "/", session: true, httpOnly: false, secure: true, sameSite: "strict" },
    { name: "b", value: "", domain: "x.com", path: "/", session: true, httpOnly: false, secure: true, sameSite: "lax" },
  ]);
  assert.deepEqual(out.map((c) => c.sameSite), ["Strict", "Lax"]);
});
