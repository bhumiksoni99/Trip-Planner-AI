export type ApprovalRequest = {
  question: string;
  itinerary: string;
  budget: string;
};

export type PlanResponse = {
  thread_id: string;
  final_response: string;
  llm_calls: number;
  // Set when the backend paused for approval; the plan arrives after resumePlan()
  awaiting_approval: boolean;
  approval_request: ApprovalRequest | null;
};

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

export async function resumePlan(threadId: string, approved: boolean, feedback = ""): Promise<PlanResponse> {
  const response = await fetch("/api/approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, approved, feedback }),
  });

  return readPlan(response);
}
