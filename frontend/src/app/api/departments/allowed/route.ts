import { NextRequest, NextResponse } from "next/server";
import { BACKEND_ORIGIN } from "@/lib/backend";

export async function GET(req: NextRequest) {
  const cookie = req.headers.get("cookie") ?? "";
  const res = await fetch(`${BACKEND_ORIGIN}/api/departments/allowed`, {
    headers: { Cookie: cookie },
  });
  const body = await res.text();
  return new NextResponse(body, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
