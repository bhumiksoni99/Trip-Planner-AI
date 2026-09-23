import { callBackend, relayJson, unreachable } from "@/lib/server/backend";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const query = new URL(request.url).searchParams.get("q") ?? "";

  try {
    return relayJson(await callBackend(`/api/place?q=${encodeURIComponent(query)}`));
  } catch {
    return unreachable();
  }
}
