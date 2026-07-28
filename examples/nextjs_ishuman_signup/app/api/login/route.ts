import { NextResponse } from "next/server";
import { findOrCreateUser, getVerifier } from "@/lib/verifier";
import { SESSION_COOKIE, signSession } from "@/lib/session";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const presentation = body?.presentation;
  if (!presentation) {
    return NextResponse.json({ success: false, reason: "presentation_missing" }, { status: 400 });
  }

  const verifier = await getVerifier();
  const result = await verifier.verify(presentation);
  if (!result.ok) {
    return NextResponse.json({ success: false, reason: result.reason }, { status: 401 });
  }

  findOrCreateUser(result.ppid);
  const response = NextResponse.json({
    success: true,
    ppid: result.ppid,
    assurance: result.assurance,
  });
  response.cookies.set(SESSION_COOKIE, signSession(result.ppid), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 86400,
    path: "/",
  });
  return response;
}
