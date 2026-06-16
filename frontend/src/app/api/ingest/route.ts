import { NextRequest, NextResponse } from "next/server";
import { BACKEND_ORIGIN } from "@/lib/backend";

// Docling parsing + embedding of a large PDF can take several minutes.
export const maxDuration = 300;

export async function POST(req: NextRequest) {
  const formData = await req.formData();
  const search = req.nextUrl.search ?? "";
  const cookie = req.headers.get("cookie") ?? "";

  const res = await fetch(`${BACKEND_ORIGIN}/api/ingest${search}`, {
    method: "POST",
    body: formData,
    headers: { Cookie: cookie },
  });
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
