import { cookies } from "next/headers";

import { TOKEN_COOKIE } from "@/lib/server/backend";

export const dynamic = "force-dynamic";

export async function POST() {
  // Forgetting the token is the whole logout: nothing else identifies the browser
  (await cookies()).delete(TOKEN_COOKIE);
  return Response.json({ success: true, data: null });
}
