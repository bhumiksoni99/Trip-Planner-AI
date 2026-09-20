export type PlanResponse = {
  thread_id: string;
  final_response: string;
  llm_calls: number;
};

export async function requestPlan(query: string, threadId: string | null): Promise<PlanResponse> {
  const response = await fetch("/api/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: query, thread_id: threadId }),
  });

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
