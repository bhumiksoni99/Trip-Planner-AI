// Photos and links for a place, so the traveller can look it up without leaving the app
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(request: Request) {
  const query = new URL(request.url).searchParams.get("q") ?? "";

  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}/api/place?q=${encodeURIComponent(query)}`);
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
