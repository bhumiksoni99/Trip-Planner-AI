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

export type PlanResponse = {
  thread_id: string;
  final_response: string;
  llm_calls: number;
  // Set when the backend paused, either for trip details or for approval; answer it with resumePlan()
  pause_type: "intake" | "approval" | null;
  pause_payload: IntakePause | ApprovalPause | null;
};

export type ResumeAnswer =
  | { approved: boolean; feedback?: string }
  | { answers: Record<string, string> }
  | { skipped: true };

async function readPlan(response: Response): Promise<PlanResponse> {
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    // Our backend puts error messages in `error`; FastAPI's own errors and the proxy use `detail`
    const error =
      typeof data?.error === "string" ? data.error : typeof data?.detail === "string" ? data.detail : null;
    throw new Error(error ?? `Request failed with status ${response.status}.`);
  }

  // The backend wraps the plan as { success, data }
  return data.data as PlanResponse;
}

export async function requestPlan(query: string, threadId: string | null): Promise<PlanResponse> {
  const response = await fetch("/api/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: query, thread_id: threadId }),
  });

  return readPlan(response);
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

export async function resumePlan(threadId: string, answer: ResumeAnswer): Promise<PlanResponse> {
  const response = await fetch("/api/approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, ...answer }),
  });

  return readPlan(response);
}
