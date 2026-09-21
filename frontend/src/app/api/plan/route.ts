// Forwards plan requests to the FastAPI backend, so the browser never calls it directly (no CORS setup needed)
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// The backend answers with a progress stream, so this route must not buffer or parse it
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await request.text();

  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}/api/travel/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
  } catch {
    return Response.json(
      { detail: `Couldn't reach the backend at ${BACKEND_URL}. Is the FastAPI server running?` },
      { status: 502 },
    );
  }

  if (!response.ok || !response.body) {
    const data = await response.json().catch(() => null);
    return Response.json(data ?? { detail: "The backend returned an invalid response." }, {
      status: response.ok ? 502 : response.status,
    });
  }

  // Hand the events straight through to the browser as they arrive
  return new Response(response.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
    },
  });
}
