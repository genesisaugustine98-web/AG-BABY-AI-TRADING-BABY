import "server-only";

import { createHash, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

const COOKIE_NAME = "ag_cockpit_access";

export function digestAccessToken(value: string) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

export function verifyAccessToken(expected: string, provided: string) {
  const a = Buffer.from(digestAccessToken(expected), "utf8");
  const b = Buffer.from(digestAccessToken(provided), "utf8");
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
  const expectedHash = digestAccessToken(expected);
  const actual = Buffer.from(tokenHash, "utf8");
  const wanted = Buffer.from(expectedHash, "utf8");
  return actual.length === wanted.length && timingSafeEqual(actual, wanted);
}

export const cockpitCookie = COOKIE_NAME;
