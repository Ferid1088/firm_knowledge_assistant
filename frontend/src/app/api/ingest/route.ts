import { NextRequest, NextResponse } from "next/server";
import { BACKEND_ORIGIN } from "@/lib/backend";

export const maxDuration = 300;

export async function POST(req: NextRequest) {
  const search = req.nextUrl.search ?? "";
  const cookie = req.headers.get("cookie") ?? "";
  const contentType = req.headers.get("content-type") ?? "";

  const res = await fetch(`${BACKEND_ORIGIN}/api/ingest${search}`, {
    method: "POST",
    body: req.body,
    headers: {
      Cookie: cookie,
      "Content-Type": contentType,
    },
    // @ts-expect-error duplex required for streaming body in Node
    duplex: "half",
  });

  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
