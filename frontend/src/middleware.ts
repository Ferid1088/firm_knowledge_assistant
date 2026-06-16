import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/setup-required", "/change-password"];

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Allow public paths and Next.js internals
  if (
    PUBLIC_PATHS.some((p) => pathname.startsWith(p)) ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname.startsWith("/api/auth/")
  ) {
    return NextResponse.next();
  }

  // Check auth status via backend (include cookies from the incoming request)
  let status: { setup_required?: boolean; authenticated?: boolean; user?: { role_id?: string; must_change_password?: boolean } };
  try {
    const res = await fetch("http://127.0.0.1:8000/api/auth/status", {
      headers: { Cookie: req.headers.get("cookie") ?? "" },
      cache: "no-store",
    });
    status = await res.json();
  } catch {
    // Backend unreachable — let through so the error is visible
    return NextResponse.next();
  }

  if (status.setup_required) {
    return NextResponse.redirect(new URL("/setup-required", req.url));
  }
  if (!status.authenticated) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  if (status.user?.must_change_password) {
    return NextResponse.redirect(new URL("/change-password", req.url));
  }
  if (pathname.startsWith("/admin") && status.user?.role_id !== "superadmin") {
    return NextResponse.redirect(new URL("/", req.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
