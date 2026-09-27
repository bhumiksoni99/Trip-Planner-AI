import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AgentProgress, { applyProgress, emptyProgress, type ProgressState } from "./AgentProgress";

/** Folds a run's events in order, the way ChatApp does as they arrive. */
function replay(...events: Parameters<typeof applyProgress>[1][]): ProgressState {
  return events.reduce(applyProgress, emptyProgress);
}

const started = (agent: string) => ({ type: "agent_started", agent }) as const;
const finished = (agent: string, failed = false) => ({ type: "agent_finished", agent, failed }) as const;
const selected = (...agents: string[]) => ({ type: "agents_selected", agents }) as const;

describe("applyProgress", () => {
  it("lists the agents the supervisor picked, and the write-up that always ends a run", () => {
    expect(replay(selected("flight_agent", "itinerary_agent")).agents).toEqual([
      "flight_agent",
      "itinerary_agent",
      "final_response_agent",
    ]);
  });

  it("keeps the order the agents were announced in", () => {
    const { agents } = replay(selected("itinerary_agent", "hotel_agent", "budget_agent"));
    expect(agents).toEqual(["itinerary_agent", "hotel_agent", "budget_agent", "final_response_agent"]);
  });

  it("leaves out the steps the traveller didn't ask for", () => {
    // intake and the approval gate get a card of their own; the photo only fetches the header image
    const { agents } = replay(selected("intake_agent", "hil_agent", "photo_agent", "weather_agent"));
    expect(agents).toEqual(["weather_agent", "final_response_agent"]);
  });

  it("ignores start and finish events for those steps too", () => {
    const state = replay(selected("weather_agent"), started("photo_agent"), finished("photo_agent"));
    expect(state.agents).not.toContain("photo_agent");
    expect(state.status).not.toHaveProperty("photo_agent");
  });

  it("marks an agent running, then done", () => {
    const running = replay(selected("weather_agent"), started("weather_agent"));
    expect(running.status.weather_agent).toBe("running");

    const done = applyProgress(running, finished("weather_agent"));
    expect(done.status.weather_agent).toBe("done");
  });

  it("marks an agent that errored as failed, not done", () => {
    const state = replay(selected("flight_agent"), started("flight_agent"), finished("flight_agent", true));
    expect(state.status.flight_agent).toBe("failed");
  });

  it("gives a row to an agent that starts without having been announced", () => {
    // A refinement goes straight to the agents it re-runs, so the checklist learns them as they start
    const state = replay(started("hotel_agent"));
    expect(state.agents).toEqual(["hotel_agent"]);
    expect(state.status.hotel_agent).toBe("running");
  });

  it("doesn't list an agent twice when it is announced and then starts", () => {
    const state = replay(selected("hotel_agent"), started("hotel_agent"), finished("hotel_agent"));
    expect(state.agents.filter((agent) => agent === "hotel_agent")).toHaveLength(1);
  });

  it("doesn't change the state it was given", () => {
    const before = replay(selected("weather_agent"));
    const snapshot = structuredClone(before);
    applyProgress(before, started("weather_agent"));
    expect(before).toEqual(snapshot);
  });
});

describe("<AgentProgress />", () => {
  it("shows a readable label for each agent rather than its name", () => {
    render(<AgentProgress progress={replay(selected("flight_agent", "hotel_agent"))} />);

    expect(screen.getByText("Finding flights")).toBeInTheDocument();
    expect(screen.getByText("Searching hotels")).toBeInTheDocument();
    expect(screen.getByText("Putting your plan together")).toBeInTheDocument();
    expect(screen.queryByText(/flight_agent/)).not.toBeInTheDocument();
  });

  it("falls back to a tidied-up name for an agent it has no label for", () => {
    render(<AgentProgress progress={replay(started("mystery_agent"))} />);
    expect(screen.getByText("mystery")).toBeInTheDocument();
  });

  it("renders nothing to read before any agent is known", () => {
    render(<AgentProgress progress={emptyProgress} />);
    expect(screen.getByRole("list", { name: "Planning progress" })).toBeEmptyDOMElement();
  });
});
