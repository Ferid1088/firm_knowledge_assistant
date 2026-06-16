import { NextRequest, NextResponse } from "next/server";
import { BACKEND_ORIGIN } from "@/lib/backend";

function cookieHeader(req: NextRequest): Record<string, string> {
  const cookie = req.headers.get("cookie");
  return cookie ? { Cookie: cookie } : {};
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  
  const body = await req.text();
  const res = await fetch(`${BACKEND_ORIGIN}/api/conversations/${encodeURIComponent(id)}/share`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...cookieHeader(req) },
    body,
  });
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
