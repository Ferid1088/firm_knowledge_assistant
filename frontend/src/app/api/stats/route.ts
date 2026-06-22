import { NextResponse } from "next/server";
import { BACKEND_ORIGIN } from "@/lib/backend";

export async function GET() {
  const res = await fetch(`${BACKEND_ORIGIN}/api/stats`);
  const body = await res.text();
  return new NextResponse(body, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
