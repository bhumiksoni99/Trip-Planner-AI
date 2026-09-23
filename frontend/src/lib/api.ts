// Type-only, so it doesn't create a real import cycle with threads.ts
import type { Message } from "./threads";

export type ApprovalPause = {
  type: "approval";
  question: string;
  itinerary: string;
  budget: string;
};

export type IntakeQuestion = {
  key: string;
  question: string;
  placeholder: string;
  options: string[];
  value: string;
};

export type IntakePause = {
  type: "intake";
  intro: string;
  questions: IntakeQuestion[];
};

export type PlanDayItem = {
  time: string;
  text: string;
};

// The day-by-day plan, sent as data so the UI can lay it out rather than print it as prose
export type PlanDay = {
  label: string;
  heading: string;
  items: PlanDayItem[];
};

// One term the plan was made against. `assumed` means the traveller never said, so we filled it in
export type BriefTerm = {
  label: string;
  value: string;
  assumed: boolean;
};

// A shortlisted hotel for one of the itinerary's stays
export type PlanHotel = {
  name: string;
  url: string;
  why: string;
  city: string;
  area: string;
  nights: number;
};

export type CostLine = {
  label: string;
  amount: string;
  note: string;
};

// The cost breakdown, shown as a table in the budget section
export type PlanCosts = {
  lines: CostLine[];
  total: string;
  ceiling: string;
  // Share of the budget the traveller stated; null when they gave none
  percent: number | null;
};

// The plan's title card: where the trip goes, on what terms, and its estimated cost
export type PlanHeader = {
  destination: string;
  summary: string;
  dates: string;
  duration: string;
  origin: string;
  total: string;
  image: string;
};

export type PlanResponse = {
  thread_id: string;
  final_response: string;
  header: PlanHeader | null;
  costs: PlanCosts | null;
  days: PlanDay[];
  hotels: PlanHotel[];
  brief: BriefTerm[];
  llm_calls: number;
  // Set when the backend paused, either for trip details or for approval; answer it with resumePlan()
  pause_type: "intake" | "approval" | null;
  pause_payload: IntakePause | ApprovalPause | null;
};

export type ResumeAnswer =
  | { approved: boolean; feedback?: string }
  | { answers: Record<string, string> }
  | { skipped: true };

// Sent by the backend while the graph runs, so the UI can show which agent is working
export type AgentProgressEvent =
  | { type: "agents_selected"; agents: string[] }
  | { type: "agent_started"; agent: string }
  | { type: "agent_finished"; agent: string; failed: boolean };

export type OnProgress = (event: AgentProgressEvent) => void;

async function failureOf(response: Response): Promise<string> {
  const data = await response.json().catch(() => null);

  // Our backend puts error messages in `error`; FastAPI's own errors and the proxy use `detail`
  if (typeof data?.error === "string") return data.error;
  if (typeof data?.detail === "string") return data.detail;
  return `Request failed with status ${response.status}.`;
}

/** Splits one server-sent event into its name and its JSON payload, or null for a keep-alive. */
function parseEvent(block: string): { name: string; data: Record<string, unknown> } | null {
  let name = "message";
  const dataLines: string[] = [];

  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }

  if (!dataLines.length) return null;

  try {
    return { name, data: JSON.parse(dataLines.join("\n")) as Record<string, unknown> };
  } catch {
    return null;
  }
}

/** Reads the progress stream, reporting each agent as it goes, and resolves with the finished plan. */
async function readPlanStream(response: Response, onProgress?: OnProgress): Promise<PlanResponse> {
  if (!response.ok || !response.body) throw new Error(await failureOf(response));

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let plan: PlanResponse | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Events are separated by a blank line; whatever follows the last one is still arriving
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const event = parseEvent(block);
      if (!event) continue;

      if (event.name === "error") {
        throw new Error(
          typeof event.data.error === "string" ? event.data.error : "Something went wrong. Please try again.",
        );
      }

      if (event.name === "done") {
        plan = event.data as unknown as PlanResponse;
      } else if (event.name === "agents_selected") {
        const agents = Array.isArray(event.data.agents) ? (event.data.agents as string[]) : [];
        onProgress?.({ type: "agents_selected", agents });
      } else if (event.name === "agent_started" || event.name === "agent_finished") {
        const agent = String(event.data.agent ?? "");
        if (!agent) continue;
        onProgress?.(
          event.name === "agent_started"
            ? { type: "agent_started", agent }
            : { type: "agent_finished", agent, failed: Boolean(event.data.failed) },
        );
      }
    }
  }

  if (!plan) throw new Error("The connection closed before the plan was finished.");

  return plan;
}

export async function requestPlan(
  query: string,
  threadId: string | null,
  onProgress?: OnProgress,
): Promise<PlanResponse> {
  const response = await fetch("/api/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: query, thread_id: threadId }),
  });

  return readPlanStream(response, onProgress);
}

export type PlacePreview = {
  images: { url: string; description?: string }[];
  results: { title: string; url: string; content: string }[];
};

export async function fetchPlacePreview(query: string): Promise<PlacePreview> {
  const response = await fetch(`/api/place?q=${encodeURIComponent(query)}`);
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const error =
      typeof data?.error === "string" ? data.error : typeof data?.detail === "string" ? data.detail : null;
    throw new Error(error ?? `Couldn't load this place (${response.status}).`);
  }

  return data.data as PlacePreview;
}

export async function resumePlan(
  threadId: string,
  answer: ResumeAnswer,
  onProgress?: OnProgress,
): Promise<PlanResponse> {
  const response = await fetch("/api/approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, ...answer }),
  });

  return readPlanStream(response, onProgress);
}

// ---------------------------------------------------------------- accounts and saved chats

export type Account = { id: string; email: string };
export type ChatSummary = { id: string; title: string; updatedAt: number };
export type ChatDetail = ChatSummary & {
  messages: Message[];
  // The question the chat is paused on, so a refresh mid-intake brings the card back
  pause: IntakePause | ApprovalPause | null;
};

async function send<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json", ...init?.headers } : init?.headers,
  });

  if (!response.ok) throw new Error(await failureOf(response));

  // The backend wraps everything as { success, data }
  const body = await response.json();
  return body.data as T;
}

export function signup(email: string, password: string): Promise<Account> {
  return send<Account>("/api/auth/signup", { method: "POST", body: JSON.stringify({ email, password }) });
}

export function login(email: string, password: string): Promise<Account> {
  return send<Account>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
}

export function logout(): Promise<void> {
  return send<void>("/api/auth/logout", { method: "POST" });
}

export function listChats(): Promise<ChatSummary[]> {
  return send<ChatSummary[]>("/api/chats");
}

/** One chat, rebuilt from its checkpoint, or null when it isn't there (or isn't yours). */
export async function loadChat(id: string): Promise<ChatDetail | null> {
  const response = await fetch(`/api/chats/${id}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(await failureOf(response));
  return (await response.json()).data as ChatDetail;
}

export function deleteChat(id: string): Promise<{ id: string }> {
  return send<{ id: string }>(`/api/chats/${id}`, { method: "DELETE" });
}

/** Hands the chats planned as a guest to the account just logged into. */
export function claimChats(threadIds: string[]): Promise<{ claimed: string[] }> {
  return send<{ claimed: string[] }>("/api/chats/claim", { method: "POST", body: JSON.stringify({ thread_ids: threadIds }) });
}
