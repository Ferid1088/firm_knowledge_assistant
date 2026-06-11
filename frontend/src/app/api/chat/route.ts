import { NextRequest, NextResponse } from "next/server";
import { BACKEND_ORIGIN } from "@/lib/backend";

// On pilot hardware (M1, CPU-only reranker), a query that escalates through all
// retrieval attempts before abstaining can take up to ~8 minutes end-to-end.
export const maxDuration = 600;

export async function POST(req: NextRequest) {
  const body = await req.text();

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 590_000);

  try {
    const res = await fetch(`${BACKEND_ORIGIN}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      signal: controller.signal,
    });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } finally {
    clearTimeout(timeout);
  }
}
