import { NextRequest, NextResponse } from "next/server";
import { BACKEND_ORIGIN } from "@/lib/backend";

function cookieHeader(req: NextRequest): Record<string, string> {
  const cookie = req.headers.get("cookie");
  return cookie ? { Cookie: cookie } : {};
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string; userId: string }> }) {
  const { id, userId: targetUserId } = await params;
  
  const res = await fetch(
    `${BACKEND_ORIGIN}/api/conversations/${encodeURIComponent(id)}/share/${encodeURIComponent(targetUserId)}`,
    { method: "DELETE", headers: { ...cookieHeader(req) } },
  );
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
