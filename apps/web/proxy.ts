import { type NextRequest, NextResponse } from "next/server";

// The browser talks to same-origin /api/*, so the session cookie stays
// first-party, and this forwards it to FastAPI. The address is read on every
// request rather than baked in at build time, because the Windows app starts
// its backend on whatever port is free.
export function proxy(request: NextRequest) {
  const origin = process.env.API_ORIGIN ?? "http://localhost:8000";
  return NextResponse.rewrite(new URL(`${request.nextUrl.pathname}${request.nextUrl.search}`, origin));
}

export const config = { matcher: "/api/:path*" };
