import { callBackend, relayJson, unreachable } from "@/lib/server/backend";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return relayJson(await callBackend("/api/chats"));
  } catch {
    return unreachable();
  }
}
