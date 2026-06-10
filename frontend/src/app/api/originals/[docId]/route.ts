import { NextRequest, NextResponse } from "next/server";
import { BACKEND_ORIGIN } from "@/lib/backend";

export async function GET(_req: NextRequest, { params }: { params: Promise<{ docId: string }> }) {
  const { docId } = await params;
  const res = await fetch(`${BACKEND_ORIGIN}/api/originals/${encodeURIComponent(docId)}`);
  if (!res.ok) {
    return new NextResponse(await res.text(), { status: res.status });
  }
  const buf = await res.arrayBuffer();
  return new NextResponse(buf, {
    status: 200,
    headers: { "Content-Type": "application/pdf" },
  });
}
