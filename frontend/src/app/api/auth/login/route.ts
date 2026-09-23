import { startSession } from "@/lib/server/accounts";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  return startSession("/api/auth/login", await request.text());
}
