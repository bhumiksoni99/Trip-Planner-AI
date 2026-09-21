// Answers the approval question a paused plan is waiting on, via the FastAPI backend
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  const body = await request.text();

  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}/api/travel/resume`, {
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

  const data = await response.json().catch(() => null);
  if (data === null) {
    return Response.json({ detail: "The backend returned an invalid response." }, { status: 502 });
  }

  return Response.json(data, { status: response.status });
}
