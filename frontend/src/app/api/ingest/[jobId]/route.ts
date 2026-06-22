import { NextRequest, NextResponse } from "next/server";
import { BACKEND_ORIGIN } from "@/lib/backend";

export async function GET(req: NextRequest, { params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  const cookie = req.headers.get("cookie") ?? "";
  const res = await fetch(`${BACKEND_ORIGIN}/api/ingest/${encodeURIComponent(jobId)}`, {
    headers: { Cookie: cookie },
  });
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
