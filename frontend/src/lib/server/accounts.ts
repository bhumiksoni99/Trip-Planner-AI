import "server-only";
import { cookies } from "next/headers";

import { callBackend, TOKEN_COOKIE, TOKEN_DAYS, unreachable } from "./backend";

/** Signs up or logs in, then keeps the token in an httpOnly cookie so the browser can't read it. */
export async function startSession(path: "/api/auth/login" | "/api/auth/signup", body: string): Promise<Response> {
  let response: Response;
  try {
    response = await callBackend(path, { method: "POST", headers: { "Content-Type": "application/json" }, body });
  } catch {
    return unreachable();
  }

  const data = await response.json().catch(() => null);
  if (!response.ok || !data?.data?.token) {
    return Response.json(data ?? { detail: "Couldn't sign you in." }, { status: response.ok ? 502 : response.status });
  }

  const store = await cookies();
  store.set(TOKEN_COOKIE, data.data.token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: TOKEN_DAYS * 24 * 60 * 60,
  });

  // The account, without the token: the browser has no use for it
  return Response.json({ success: true, data: data.data.user });
}

/** Who is logged in, by asking the backend to verify the cookie's token. Null for a guest. */
export async function currentAccount(): Promise<{ id: string; email: string } | null> {
  try {
    const response = await callBackend("/api/auth/me");
    if (!response.ok) return null;
    return (await response.json()).data;
  } catch {
    return null;
  }
}
