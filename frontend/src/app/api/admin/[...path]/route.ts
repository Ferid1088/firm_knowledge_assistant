/**
 * Transparent proxy for /api/admin/* → FastAPI backend.
 * Forwards cookies so the session is verified server-side.
 */
import { NextRequest, NextResponse } from "next/server";
import { BACKEND_ORIGIN } from "@/lib/backend";

async function proxy(req: NextRequest, params: { path: string[] }) {
  const path = params.path.join("/");
  const url = `${BACKEND_ORIGIN}/api/admin/${path}`;

  const headers: Record<string, string> = {
    "Content-Type": req.headers.get("content-type") ?? "application/json",
  };
  const cookie = req.headers.get("cookie");
  if (cookie) headers["Cookie"] = cookie;

  const body = req.method !== "GET" && req.method !== "HEAD"
    ? await req.text()
    : undefined;

  const backendRes = await fetch(url, {
    method: req.method,
    headers,
    body,
  });

  const resHeaders = new Headers();
  resHeaders.set("Content-Type", backendRes.headers.get("content-type") ?? "application/json");
  const setCookie = backendRes.headers.get("set-cookie");
  if (setCookie) resHeaders.set("Set-Cookie", setCookie);

  const text = await backendRes.text();
  return new NextResponse(text, { status: backendRes.status, headers: resHeaders });
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await params);
}
export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await params);
}
export async function PUT(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await params);
}
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await params);
}
export async function DELETE(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, await params);
}
