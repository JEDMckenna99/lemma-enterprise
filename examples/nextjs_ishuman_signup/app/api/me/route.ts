import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SESSION_COOKIE, readSession } from "@/lib/session";

export async function GET() {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const ppid = readSession(token);
  if (!ppid) {
    return NextResponse.json({ success: false, error: "auth_required" }, { status: 401 });
  }
  return NextResponse.json({ success: true, ppid });
}
