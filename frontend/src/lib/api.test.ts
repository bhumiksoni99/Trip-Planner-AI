import { afterEach, describe, expect, it, vi } from "vitest";

import { requestPlan, type AgentProgressEvent } from "./api";

/** A fetch that streams back the given text in the chunks given, as the backend's SSE route does. */
function streamingFetch(chunks: string[], init: ResponseInit = {}) {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });

  return vi.fn().mockResolvedValue(new Response(body, { status: 200, ...init }));
}

const event = (name: string, data: unknown) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;

const DONE = {
  thread_id: "t1",
  pause_type: null,
  pause_payload: null,
  final_response: "## Weather\n\nOvercast.",
  days: [],
  hotels: [],
  brief: [],
  costs: null,
  header: null,
};

afterEach(() => vi.unstubAllGlobals());

function useFetch(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("requestPlan", () => {
  it("resolves with the plan the stream ends on", async () => {
    useFetch(streamingFetch([event("done", DONE)]));

    await expect(requestPlan("weather in Kyoto", "t1")).resolves.toMatchObject({
      thread_id: "t1",
      final_response: "## Weather\n\nOvercast.",
    });
  });

  it("reports each agent as it starts and finishes", async () => {
    useFetch(
      streamingFetch([
        event("agents_selected", { agents: ["weather_agent"] }),
        event("agent_started", { agent: "weather_agent" }),
        event("agent_finished", { agent: "weather_agent", failed: false }),
        event("done", DONE),
      ]),
    );

    const seen: AgentProgressEvent[] = [];
    await requestPlan("weather in Kyoto", "t1", (progress) => seen.push(progress));

    expect(seen).toEqual([
      { type: "agents_selected", agents: ["weather_agent"] },
      { type: "agent_started", agent: "weather_agent" },
      { type: "agent_finished", agent: "weather_agent", failed: false },
    ]);
  });

  it("reads an event that arrives split across chunks", async () => {
    // A network read can end anywhere, including the middle of a JSON payload
    const whole = event("agent_started", { agent: "hotel_agent" }) + event("done", DONE);
    const cut = Math.floor(whole.length / 3);
    useFetch(streamingFetch([whole.slice(0, cut), whole.slice(cut, cut * 2), whole.slice(cut * 2)]));

    const seen: AgentProgressEvent[] = [];
    const plan = await requestPlan("a trip", "t1", (progress) => seen.push(progress));

    expect(seen).toEqual([{ type: "agent_started", agent: "hotel_agent" }]);
    expect(plan.thread_id).toBe("t1");
  });

  it("reads several events arriving in one chunk", async () => {
    useFetch(streamingFetch([event("agent_started", { agent: "flight_agent" }) + event("done", DONE)]));

    const seen: AgentProgressEvent[] = [];
    await requestPlan("a trip", "t1", (progress) => seen.push(progress));
    expect(seen).toHaveLength(1);
  });

  it("ignores the keep-alives the backend sends while nothing has finished", async () => {
    useFetch(streamingFetch([": keep-alive\n\n", ": keep-alive\n\n", event("done", DONE)]));

    const seen: AgentProgressEvent[] = [];
    await expect(requestPlan("a trip", "t1", (progress) => seen.push(progress))).resolves.toBeTruthy();
    expect(seen).toEqual([]);
  });

  it("marks a failed agent as failed", async () => {
    useFetch(
      streamingFetch([event("agent_finished", { agent: "flight_agent", failed: true }), event("done", DONE)]),
    );

    const seen: AgentProgressEvent[] = [];
    await requestPlan("a trip", "t1", (progress) => seen.push(progress));
    expect(seen).toEqual([{ type: "agent_finished", agent: "flight_agent", failed: true }]);
  });

  it("throws the backend's message when the stream carries an error", async () => {
    useFetch(streamingFetch([event("error", { error: "Something went wrong while planning your trip." })]));

    await expect(requestPlan("a trip", "t1")).rejects.toThrow("Something went wrong while planning your trip.");
  });

  it("throws when the connection closes before the plan is finished", async () => {
    useFetch(streamingFetch([event("agent_started", { agent: "flight_agent" })]));

    await expect(requestPlan("a trip", "t1")).rejects.toThrow(/connection closed/i);
  });

  it("surfaces an HTTP failure before reading any stream", async () => {
    const failed = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: "Chat not found" }), { status: 404 }),
    );
    useFetch(failed);

    await expect(requestPlan("a trip", "someone-elses-thread")).rejects.toThrow("Chat not found");
  });

  it("falls back to the status when a failure has no message", async () => {
    useFetch(vi.fn().mockResolvedValue(new Response("not json", { status: 500 })));
    await expect(requestPlan("a trip", "t1")).rejects.toThrow("Request failed with status 500.");
  });

  it("posts the message and thread to the plan route", async () => {
    const fetchMock = useFetch(streamingFetch([event("done", DONE)]));
    await requestPlan("weather in Kyoto", "t1");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/plan");
    expect(JSON.parse(String(init.body))).toEqual({ message: "weather in Kyoto", thread_id: "t1" });
  });
});
