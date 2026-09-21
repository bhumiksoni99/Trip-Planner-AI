"use client";

import type { AgentProgressEvent } from "@/lib/api";
import { CheckIcon } from "./icons";

export type AgentStatus = "running" | "done" | "failed";

export type ProgressState = {
  agents: string[]; // the rows, in the order the agents run
  status: Record<string, AgentStatus>; // an agent missing from here hasn't started yet
};

export const emptyProgress: ProgressState = { agents: [], status: {} };

// These pause the run and get a card of their own, so they don't belong in the checklist
const HIDDEN = new Set(["intake_agent", "hil_agent"]);

const LABELS: Record<string, string> = {
  supervisor_agent: "Reading your request",
  feedback_agent: "Working out what to change",
  flight_agent: "Finding flights",
  weather_agent: "Checking the weather",
  itinerary_agent: "Writing the itinerary",
  hotel_agent: "Searching hotels",
  budget_agent: "Working out the budget",
  final_response_agent: "Putting your plan together",
};

function labelOf(agent: string) {
  return LABELS[agent] ?? agent.replace(/_agent$/, "").replace(/_/g, " ");
}

/** Folds one progress event into the checklist: which agents will run, and how far each one got. */
export function applyProgress(current: ProgressState, event: AgentProgressEvent): ProgressState {
  if (event.type === "agents_selected") {
    // The agents the supervisor picked, plus the write-up that always ends a run
    const upcoming = [...event.agents, "final_response_agent"].filter((agent) => !HIDDEN.has(agent));
    const agents = [...current.agents];
    for (const agent of upcoming) if (!agents.includes(agent)) agents.push(agent);
    return { ...current, agents };
  }

  if (HIDDEN.has(event.agent)) return current;

  // An agent that starts without having been announced still gets a row
  const agents = current.agents.includes(event.agent) ? current.agents : [...current.agents, event.agent];
  const status: AgentStatus = event.type === "agent_started" ? "running" : event.failed ? "failed" : "done";

  return { agents, status: { ...current.status, [event.agent]: status } };
}

export default function AgentProgress({ progress }: { progress: ProgressState }) {
  return (
    <ul className="mt-4 space-y-2.5" aria-label="Planning progress">
      {progress.agents.map((agent) => {
        const status = progress.status[agent];
        return (
          <li key={agent} className="flex items-center gap-2.5 text-sm">
            <StatusIcon status={status} />
            <span
              className={
                status === "running"
                  ? "font-medium text-ink"
                  : status === "done" || status === "failed"
                    ? "text-muted"
                    : "text-muted/60"
              }
            >
              {labelOf(agent)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function StatusIcon({ status }: { status?: AgentStatus }) {
  if (status === "done") return <CheckIcon className="size-4 shrink-0 text-teal" />;

  if (status === "failed") {
    return (
      <span aria-hidden className="size-4 shrink-0 text-center text-xs leading-4 font-bold text-red-500">
        !
      </span>
    );
  }

  if (status === "running") {
    return (
      <span aria-hidden className="size-4 shrink-0 animate-spin rounded-full border-2 border-line border-t-accent" />
    );
  }

  return <span aria-hidden className="size-4 shrink-0 rounded-sharp border-2 border-line" />;
}
