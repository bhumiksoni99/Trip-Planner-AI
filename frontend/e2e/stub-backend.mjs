/**
 * Stands in for FastAPI while the end-to-end tests run.
 *
 * The tests drive the real Next.js server, so its route handlers, the httpOnly login cookie and the
 * SSE pass-through all behave exactly as they do in production — only the Python service behind them
 * is replaced. That keeps the tests free, offline and deterministic: no model calls, no Tavily, no
 * Postgres, and a plan that takes 25 seconds for real finishes here in a few hundred milliseconds.
 *
 * State lives in memory and is reset between tests through POST /__reset.
 *
 *     node e2e/stub-backend.mjs [port]
 */
import { createServer } from "node:http";

const PORT = Number(process.argv[2] ?? 8099);

/** email -> { id, email, password, token } */
let users = new Map();
/** threadId -> { userId, title, messages, pause } — userId null means an unclaimed guest chat */
let chats = new Map();
let nextId = 1;

function reset() {
  users = new Map();
  chats = new Map();
  nextId = 1;
}

const json = (response, status, body) => {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
};

const ok = (response, data) => json(response, 200, { success: true, data });
const notFound = (response) => json(response, 404, { detail: "Chat not found" });

function readBody(request) {
  return new Promise((resolve) => {
    let body = "";
    request.on("data", (chunk) => (body += chunk));
    request.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch {
        resolve({});
      }
    });
  });
}

/** The account a Bearer token belongs to, or null for a guest. */
function accountFor(request) {
  const header = request.headers.authorization ?? "";
  if (!header.startsWith("Bearer ")) return null;
  const token = header.slice(7);
  return [...users.values()].find((user) => user.token === token) ?? null;
}

/** Someone else's chat answers 404, never 403, exactly as the real backend does. */
function readable(threadId, account) {
  const chat = chats.get(threadId);
  if (!chat) return true; // unknown ids are a guest's to plan on
  return chat.userId === null || chat.userId === account?.id;
}

const title = (text) => (text.length > 60 ? `${text.slice(0, 57).trimEnd()}…` : text);

// ── What a faked run answers with ────────────────────────────────────────────────────────────────

const INTAKE = {
  type: "intake",
  intro: "A couple of things first.",
  questions: [
    { key: "travel_dates", question: "When are you going?", placeholder: "e.g. mid-May", options: ["Next month"], value: "" },
    { key: "duration", question: "How long for?", placeholder: "e.g. 5 days", options: ["5 days"], value: "" },
  ],
};

const HOTELS = [
  { name: "Hotel Gracery", url: "https://example.com/gracery", city: "Tokyo", area: "Shinjuku", nights: 2, why: "Central" },
  { name: "Park Hotel", url: "https://example.com/park", city: "Tokyo", area: "Shiodome", nights: 2, why: "Quiet" },
];

const DAYS = [
  { label: "Day 1", heading: "Arrive in Tokyo", items: [{ time: "Evening", text: "Walk Shibuya" }] },
  { label: "Day 2", heading: "Temples", items: [{ time: "Morning", text: "Senso-ji" }] },
];

const HEADER = {
  destination: "Tokyo", summary: "Five days in Tokyo", dates: "mid-May",
  duration: "5 days", origin: "Delhi", total: "Rs 1,20,000", image: "",
};

const COSTS = {
  lines: [{ label: "Flights", amount: "Rs 40,000", note: "Return" }],
  total: "Rs 1,20,000", ceiling: "Rs 2,00,000", percent: 60,
};

const BRIEF = [{ label: "Duration", value: "5 days", assumed: false }];

/** A finished plan, as the write-up and cards the UI renders. */
function fullPlan(threadId) {
  return {
    thread_id: threadId, pause_type: null, pause_payload: null,
    // Deliberately doesn't repeat the header's summary, so a test can tell the card from the prose
    final_response: "## Trip Overview\n\nA relaxed pace, planned end to end.\n\n## Hotels\n\nTwo nights each.\n\n[[HOTELS]]\n\n[[ITINERARY]]\n\n## Estimated Budget\n\nWithin budget.\n\n[[COSTS]]",
    days: DAYS, hotels: HOTELS, brief: BRIEF, costs: COSTS, header: HEADER, llm_calls: 6,
  };
}

/** A hotels-only answer: hotel cards, and no day-by-day plan the traveller never asked for. */
function hotelsOnly(threadId) {
  return {
    thread_id: threadId, pause_type: null, pause_payload: null,
    final_response: "## Hotels\n\nCheaper places in Tokyo.\n\n[[HOTELS]]",
    days: [], hotels: HOTELS, brief: BRIEF, costs: null, header: HEADER, llm_calls: 3,
  };
}

function paused(threadId) {
  return {
    thread_id: threadId, pause_type: "intake", pause_payload: INTAKE,
    final_response: "", days: [], hotels: [], brief: [], costs: null, header: null, llm_calls: 2,
  };
}

/** Writes the progress events a real run sends, then the finished plan. */
async function sendStream(response, agents, done) {
  response.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
  });

  const send = (name, data) => response.write(`event: ${name}\ndata: ${JSON.stringify(data)}\n\n`);
  const pause = () => new Promise((resolve) => setTimeout(resolve, 40));

  send("agents_selected", { agents });
  for (const agent of ["supervisor_agent", ...agents, "final_response_agent"]) {
    send("agent_started", { agent });
    await pause();
    send("agent_finished", { agent, failed: false });
  }

  send("done", done);
  response.end();
}

// ── Routes ───────────────────────────────────────────────────────────────────────────────────────

const server = createServer(async (request, response) => {
  const url = new URL(request.url, `http://localhost:${PORT}`);
  const path = url.pathname;
  const account = accountFor(request);
  const body = request.method === "POST" || request.method === "DELETE" ? await readBody(request) : {};

  // Test control: wipe the world, or plant chats and accounts for a scenario
  if (path === "/__reset") {
    reset();
    return ok(response, { reset: true });
  }

  if (path === "/__seed") {
    for (const user of body.users ?? []) users.set(user.email, { ...user });
    for (const chat of body.chats ?? []) chats.set(chat.id, { ...chat });
    return ok(response, { users: users.size, chats: chats.size });
  }

  if (path === "/health") return ok(response, { status: "ok" });

  // ── accounts ──
  if (path === "/api/auth/signup" || path === "/api/auth/login") {
    const { email, password } = body;
    const existing = users.get(email);

    if (path === "/api/auth/signup") {
      if (existing) return json(response, 409, { detail: "That email already has an account." });
      const user = { id: `user-${nextId++}`, email, password, token: `token-${email}` };
      users.set(email, user);
      return ok(response, { token: user.token, user: { id: user.id, email: user.email } });
    }

    if (!existing || existing.password !== password) {
      return json(response, 401, { detail: "Wrong email or password." });
    }
    return ok(response, { token: existing.token, user: { id: existing.id, email: existing.email } });
  }

  if (path === "/api/auth/me") {
    if (!account) return json(response, 401, { detail: "Not signed in." });

    if (request.method === "DELETE") {
      // The real backend forgets each thread's checkpoints before dropping the account, since no
      // foreign key reaches them. Here that is just removing the chats this user owns
      let threads = 0;
      for (const [id, chat] of chats) {
        if (chat.userId === account.id) {
          chats.delete(id);
          threads += 1;
        }
      }
      users.delete(account.email);
      return ok(response, { deleted: true, threads });
    }

    return ok(response, { id: account.id, email: account.email });
  }

  // ── chats ──
  if (path === "/api/chats" && request.method === "GET") {
    if (!account) return json(response, 401, { detail: "Not signed in." });
    const mine = [...chats.entries()]
      .filter(([, chat]) => chat.userId === account.id)
      .map(([id, chat]) => ({ id, title: chat.title, updatedAt: chat.updatedAt ?? Date.now() }))
      .sort((a, b) => b.updatedAt - a.updatedAt);
    return ok(response, mine);
  }

  if (path === "/api/chats/claim") {
    if (!account) return json(response, 401, { detail: "Not signed in." });
    const claimed = [];
    for (const id of body.thread_ids ?? []) {
      const chat = chats.get(id);
      // An id that already belongs to someone else is skipped, so a stray id can't take their chat
      if (chat && chat.userId === null) {
        chat.userId = account.id;
        claimed.push(id);
      }
    }
    return ok(response, { claimed });
  }

  const chatMatch = path.match(/^\/api\/chats\/(.+)$/);
  if (chatMatch) {
    const id = decodeURIComponent(chatMatch[1]);
    if (!readable(id, account)) return notFound(response);

    if (request.method === "DELETE") {
      if (!account) return json(response, 401, { detail: "Not signed in." });
      chats.delete(id);
      return ok(response, { id });
    }

    const chat = chats.get(id);
    if (!chat || !chat.messages?.length) return notFound(response);
    return ok(response, { id, title: chat.title, messages: chat.messages, pause: chat.pause ?? null });
  }

  // ── planning ──
  if (path === "/api/travel/stream") {
    const threadId = body.thread_id || `thread-${nextId++}`;
    if (!readable(threadId, account)) return notFound(response);

    const message = String(body.message ?? "");
    const chat = chats.get(threadId) ?? { userId: account?.id ?? null, title: title(message), messages: [] };
    chat.userId = account?.id ?? chat.userId ?? null;
    chats.set(threadId, chat);
    chat.messages = [...(chat.messages ?? []), { id: `m${chat.messages?.length ?? 0}`, role: "user", content: message }];

    // "cheaper hotels" is a refinement: only the hotels change, so no day-by-day plan comes back
    const aboutHotels = /hotel/i.test(message);
    // A first message with no dates pauses to ask for them, the way intake really does
    const needsDetails = !aboutHotels && !/\d/.test(message);

    if (needsDetails) {
      chat.pause = INTAKE;
      const done = paused(threadId);
      chat.messages.push({ id: `a${chat.messages.length}`, role: "assistant", content: "" });
      chat.messages.pop();
      return sendStream(response, ["intake_agent"], done);
    }

    chat.pause = null;
    const done = aboutHotels ? hotelsOnly(threadId) : fullPlan(threadId);
    const agents = aboutHotels ? ["hotel_agent"] : ["flight_agent", "weather_agent", "itinerary_agent", "hotel_agent", "budget_agent"];
    chat.messages.push({
      id: `a${chat.messages.length}`, role: "assistant", content: done.final_response,
      days: done.days, hotels: done.hotels, brief: done.brief, costs: done.costs, header: done.header,
    });
    return sendStream(response, agents, done);
  }

  if (path === "/api/travel/resume/stream") {
    const threadId = body.thread_id;
    if (!readable(threadId, account)) return notFound(response);

    const chat = chats.get(threadId) ?? { userId: account?.id ?? null, title: "New trip", messages: [] };
    chat.pause = null;
    chats.set(threadId, chat);

    const done = fullPlan(threadId);
    chat.messages = [...(chat.messages ?? []), {
      id: `a${chat.messages?.length ?? 0}`, role: "assistant", content: done.final_response,
      days: done.days, hotels: done.hotels, brief: done.brief, costs: done.costs, header: done.header,
    }];
    return sendStream(response, ["flight_agent", "itinerary_agent", "hotel_agent", "budget_agent"], done);
  }

  if (path === "/api/place") return ok(response, { images: [], results: [] });

  json(response, 404, { detail: `No stub route for ${path}` });
});

server.listen(PORT, () => console.log(`stub backend on http://localhost:${PORT}`));
