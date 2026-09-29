import { cookies } from "next/headers";

import { callBackend, relayJson, TOKEN_COOKIE, unreachable } from "@/lib/server/backend";

export const dynamic = "force-dynamic";

/** Closes the account, then forgets the token: the cookie would otherwise name a user that's gone. */
export async function DELETE() {
  let response: Response;
  try {
    response = await callBackend("/api/auth/me", { method: "DELETE" });
  } catch {
    return unreachable();
  }

  // Only on success: a failed delete leaves the account there, so the traveller stays logged in
  if (response.ok) (await cookies()).delete(TOKEN_COOKIE);

  return relayJson(response);
}
