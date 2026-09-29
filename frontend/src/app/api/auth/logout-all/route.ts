import { cookies } from "next/headers";

import { callBackend, TOKEN_COOKIE, TOKEN_DAYS, unreachable } from "@/lib/server/backend";

export const dynamic = "force-dynamic";

/** Ends every session on this account, then re-cookies this one with the token it was handed back. */
export async function POST() {
  let response: Response;
  try {
    response = await callBackend("/api/auth/logout-all", { method: "POST" });
  } catch {
    return unreachable();
  }

  const data = await response.json().catch(() => null);
  if (!response.ok || !data?.data?.token) {
    return Response.json(data ?? { detail: "Couldn't sign out your other devices." },
      { status: response.ok ? 502 : response.status });
  }

  // The old token is no longer accepted anywhere, including here, so this browser needs the new one
  // or the traveller would sign themselves out along with everybody else
  (await cookies()).set(TOKEN_COOKIE, data.data.token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: TOKEN_DAYS * 24 * 60 * 60,
  });

  return Response.json({ success: true, data: data.data.user });
}
