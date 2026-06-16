import { NextResponse } from "next/server";
import { BACKEND_ORIGIN } from "@/lib/backend";

export async function GET() {
  const res = await fetch(`${BACKEND_ORIGIN}/api/users`);
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
