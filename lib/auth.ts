import "server-only";

import { createHash, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

const COOKIE_NAME = "ag_cockpit_access";

function digest(value: string) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function matches(expected: string, provided: string) {
  const a = Buffer.from(digest(expected), "utf8");
  const b = Buffer.from(provided, "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}

export function authConfigured() {
  return Boolean(process.env.COCKPIT_ACCESS_TOKEN);
}

export async function isCockpitAuthorized() {
  const expected = process.env.COCKPIT_ACCESS_TOKEN;
  if (!expected) return false;
  const jar = await cookies();
  const tokenHash = jar.get(COOKIE_NAME)?.value || "";
  return matches(expected, tokenHash);
}

export const cockpitCookie = COOKIE_NAME;
export const digestAccessToken = digest;
