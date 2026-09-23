import { callBackend, relayJson, unreachable } from "@/lib/server/backend";

export const dynamic = "force-dynamic";

// Next 16 hands route params over as a promise
type Params = { params: Promise<{ id: string }> };

export async function GET(_request: Request, { params }: Params) {
  const { id } = await params;
  try {
    return relayJson(await callBackend(`/api/chats/${encodeURIComponent(id)}`));
  } catch {
    return unreachable();
  }
}

export async function DELETE(_request: Request, { params }: Params) {
  const { id } = await params;
  try {
    return relayJson(await callBackend(`/api/chats/${encodeURIComponent(id)}`, { method: "DELETE" }));
  } catch {
    return unreachable();
  }
}
