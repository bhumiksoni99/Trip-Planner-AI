import { callBackend, relayJson, unreachable } from "@/lib/server/backend";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    return relayJson(
      await callBackend("/api/chats/claim", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: await request.text(),
      }),
    );
  } catch {
    return unreachable();
  }
}
