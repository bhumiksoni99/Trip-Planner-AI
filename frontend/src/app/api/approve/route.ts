import { callBackend, relayJson, relayStream, unreachable } from "@/lib/server/backend";

// The backend answers with a progress stream, so this route must not buffer or parse it
export const dynamic = "force-dynamic";
// Long enough for a whole plan when deployed on Vercel
export const maxDuration = 300;

export async function POST(request: Request) {
  let response: Response;
  try {
    response = await callBackend("/api/travel/resume/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
    });
  } catch {
    return unreachable();
  }

  if (!response.ok || !response.body) return relayJson(response);

  return relayStream(response);
}
