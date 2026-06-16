import { NextRequest, NextResponse } from "next/server";
import { BACKEND_ORIGIN } from "@/lib/backend";

function cookieHeader(req: NextRequest): Record<string, string> {
  const cookie = req.headers.get("cookie");
  return cookie ? { Cookie: cookie } : {};
}

export async function GET(req: NextRequest) {
  const res = await fetch(`${BACKEND_ORIGIN}/api/conversations`, {
    headers: { ...cookieHeader(req) },
  });
  const text = await res.text();
  return new NextResponse(text, { status: res.status, headers: { "Content-Type": "application/json" } });
}

export async function POST(req: NextRequest) {
  const body = await req.text();
  const res = await fetch(`${BACKEND_ORIGIN}/api/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...cookieHeader(req) },
    body,
  });
  const text = await res.text();
  return new NextResponse(text, { status: res.status, headers: { "Content-Type": "application/json" } });
}
