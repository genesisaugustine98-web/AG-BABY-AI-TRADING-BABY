import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { authConfigured, cockpitCookie, digestAccessToken } from "@/lib/auth";

export const runtime = "nodejs";

export async function POST(request: Request) {
  if (!authConfigured()) {
    return NextResponse.json({ error: "cockpit authentication is not configured" }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }

  const form = await request.formData();
  const token = String(form.get("token") || "");
  const expected = process.env.COCKPIT_ACCESS_TOKEN || "";
  const response = token && token === expected
    ? NextResponse.redirect(new URL("/", request.url), { status: 303 })
    : NextResponse.redirect(new URL("/login?error=1", request.url), { status: 303 });

  if (token && token === expected) {
    const jar = await cookies();
    jar.set(cockpitCookie, digestAccessToken(token), {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "strict",
      path: "/",
      maxAge: 60 * 60 * 8,
    });
  }
  response.headers.set("Cache-Control", "no-store");
  return response;
}
