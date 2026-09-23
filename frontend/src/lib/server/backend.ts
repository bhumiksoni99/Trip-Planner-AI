import "server-only";
import { cookies } from "next/headers";

// The browser never calls FastAPI directly: these route handlers do, which is why no CORS setup is needed
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// Holds the login token. httpOnly, so page scripts can't read it; only this server code can
export const TOKEN_COOKIE = "itinera_token";
export const TOKEN_DAYS = 7;

export async function loginToken(): Promise<string | undefined> {
  return (await cookies()).get(TOKEN_COOKIE)?.value;
}

/** Calls FastAPI as whoever is logged in, or as a guest when nobody is. */
export async function callBackend(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await loginToken();
  return fetch(`${BACKEND_URL}${path}`, {
    ...init,
    headers: {
      ...(init.headers as Record<string, string> | undefined),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    cache: "no-store",
  });
}

export function unreachable(): Response {
  return Response.json(
    { detail: `Couldn't reach the backend at ${BACKEND_URL}. Is the FastAPI server running?` },
    { status: 502 },
  );
}

/** Hands a JSON answer back with its status. */
export async function relayJson(response: Response): Promise<Response> {
  const data = await response.json().catch(() => null);
  if (data === null) return Response.json({ detail: "The backend returned an invalid response." }, { status: 502 });
  return Response.json(data, { status: response.status });
}

/** Passes the progress stream straight through, without reading or buffering it. */
export function relayStream(response: Response): Response {
  return new Response(response.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
    },
  });
}
