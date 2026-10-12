const SAME_SITE = { no_restriction: "None", lax: "Lax", strict: "Strict", unspecified: "Lax" };

export function toPlaywrightCookies(cookies) {
  return cookies.map((c) => ({
    name: c.name,
    value: c.value,
    domain: c.domain,
    path: c.path,
    expires: c.session ? -1 : Math.floor(c.expirationDate),
    httpOnly: c.httpOnly,
    secure: c.secure,
    sameSite: SAME_SITE[c.sameSite] ?? "Lax",
  }));
}
