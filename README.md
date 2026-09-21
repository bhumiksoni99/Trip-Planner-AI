# TripMate AI

A multi-agent travel planner. You describe a trip in one sentence; a graph of specialist agents
asks for whatever you left out, searches live flights, weather and hotels, writes a day-by-day
itinerary, costs it against your budget, and returns a plan you can keep refining in the chat.

Built with [LangGraph](https://langchain-ai.github.io/langgraph/), Google Gemini, FastAPI and Next.js.

```
"Plan a 5 day Dubai trip from Delhi under 2 lakhs"
   ↓
   asks for the dates and vibe you didn't mention
   ↓
   flights → weather → itinerary → hotels → budget
   ↓
   a plan, rendered as cards
   ↓
   "make the hotels cheaper, 2 or 3 star"  → re-runs only what has to change
```

---

## Contents

- [What it does](#what-it-does)
- [How the agents fit together](#how-the-agents-fit-together)
- [Design decisions worth knowing](#design-decisions-worth-knowing)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [API](#api)
- [Project layout](#project-layout)
- [Limitations](#limitations)

---

## What it does

**Asks before it plans.** "Plan a trip to London" is missing almost everything that matters, so
`intake_agent` pauses the graph and asks — one question per card, each with preset options, a free
text box and a skip. It only asks for what your message didn't already say, and it never
interrupts a follow-up.

**Shows what it assumed.** Anything you skipped is filled with a default and marked in amber at the
top of the plan, so you can see that "5 days" was the planner's guess rather than your decision.
Those resolved terms are what the agents actually plan against, so the strip and the plan can't
drift apart.

**Renders data as data.** The itinerary, hotel shortlist and cost breakdown come back as structured
JSON, not prose, and the UI lays them out as cards. The write-up drops `[[HOTELS]]`, `[[ITINERARY]]`
and `[[COSTS]]` markers where each belongs, and the frontend splices the components in.

**Refines instead of replanning.** A follow-up message is classified as a refinement or a new trip.
A refinement goes to `feedback_agent`, which decides which specialists have to run again — "make it
cheaper" re-runs hotels and the budget, "reword day 2" just rewrites the plan. Every round of
feedback is kept, so a later request can't silently undo an earlier one.

**Keeps its links honest.** Places in the itinerary link to a Google search; hotels link to the
hotel's own page. Both open in an in-app sheet rather than sending you off the site.

---

## How the agents fit together

A LangGraph `StateGraph` with a Postgres checkpointer. Every node reads and writes one shared
`TravelState`, and the checkpoint is what lets a thread pause mid-run and resume later.

```
                    START
                      │
              supervisor_agent ─────────────► END          (not about travel)
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
   intake_agent                feedback_agent              (a follow-up that changes the plan)
   (pauses to ask)                  │
        │                           │
        └─────────────┬─────────────┘
                      ▼
   flight_agent → weather_agent → itinerary_agent → hotel_agent → budget_agent
                      │
                      ▼
            final_response_agent ──► END
```

| Agent | What it does |
|---|---|
| `supervisor_agent` | Guardrails non-travel requests, and decides whether a message starts a new trip or refines the current one |
| `intake_agent` | Extracts the trip's terms from your message, then `interrupt()`s to ask for what's missing |
| `flight_agent` | Live flight schedules for the route, via AviationStack |
| `weather_agent` | Current conditions and a 5-day forecast, via a local MCP server |
| `itinerary_agent` | Writes the day-by-day plan as structured days and activities |
| `hotel_agent` | Finds two hotels per city the itinerary stays in, and resolves each to its own page |
| `budget_agent` | Costs the trip line by line and judges it against your budget |
| `feedback_agent` | Reads your feedback and picks which specialists must run again |
| `final_response_agent` | Combines everything into the written plan, plus a one-line summary |
| `hil_agent` | An optional approve/request-changes gate, off by default (see below) |

Only the specialists the supervisor selected actually run — `route_next` walks a fixed order and
skips the rest, so a weather-only question doesn't search for hotels.

---

## Design decisions worth knowing

**No approval gate by default.** The graph has a human-in-the-loop node that pauses for approval
before the write-up. It's off, because intake now collects the trip's terms up front and a chat
follow-up already refines the plan through the same `feedback_agent` — the gate had become an extra
click on every revision. Set `REQUIRE_APPROVAL=true` to turn it back on.

**Structured output where the model authors, raw data where it doesn't.** The itinerary, cost lines
and hotel picks use `with_structured_output`, so the UI gets typed fields instead of parsing prose.
But the model never re-types flight or hotel data it was handed: a picked hotel whose URL wasn't in
the search results is dropped rather than shown.

**Percentages are computed, not generated.** The budget agent returns two plain numbers; the
"71% of budget" figure is divided in Python. Asking a model for a percentage gets you arithmetic
that looks authoritative and is sometimes wrong.

**Tavily over both MCP and REST.** The general search runs through Tavily's MCP server. Hotel search
and the link preview use its REST API instead, because the MCP adapter flattens results into one
block of text — which loses the per-result URLs the hotel cards need — and opens a fresh session per
call, costing about 6 seconds against roughly 1 second for REST.

**Search results are filtered before they're shown.** Hotel searches return round-up articles as
often as hotels, so a title like "The 10 best hotels in Zurich" never becomes a hotel card.

---

## Getting started

**You will need:** Python 3.14, Node 20+, a Postgres database, and API keys for
[Gemini](https://aistudio.google.com/apikey), [Tavily](https://tavily.com),
[AviationStack](https://aviationstack.com) and [OpenWeather](https://openweathermap.org/api)
(all have free tiers).

### 1. Backend

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

cp .env.example .env      # then fill in your keys
cd backend && uvicorn app:app --reload --port 8000
```

The checkpointer creates its own tables on first run, so an empty database is fine.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>. The Next.js route handlers under `src/app/api/` proxy to the backend,
so the browser never holds an API key.

> Use `localhost`, not `127.0.0.1` — Next dev blocks its own assets on other origins, which leaves
> the page looking loaded but dead.

### Docker

```bash
docker build -t tripmate-backend backend/
docker run --env-file .env -p 8000:8000 tripmate-backend
```

---

## Configuration

All of it comes from a `.env` at the repo root.

| Variable | Required | What it's for |
|---|---|---|
| `GEMINI_API_KEY` | yes | Every LLM call, via `gemini-2.5-flash-lite` |
| `TAVILY_API_KEY` | yes | Web search: hotels, places and link previews |
| `AVIATIONSTACK_API_KEY` | yes | Live flight schedules |
| `OPENWEATHER_API_KEY` | yes | The weather MCP server |
| `POSTGRES_DB` | yes | Connection string for the LangGraph checkpointer |
| `DEFAULT_ORIGIN` | no | Fallback departure airport, default `DEL` |
| `DEFAULT_ORIGIN_CITY` | no | Fallback departure city, shown in intake options |
| `REQUIRE_APPROVAL` | no | `true` re-enables the approval pause, default `false` |
| `MAX_REVISIONS` | no | Revision cap when approval is on, default `3` |
| `LOG_LEVEL` | no | `DEBUG` for per-agent detail, default `INFO` |
| `BACKEND_URL` | no | Where the frontend proxies to, default `http://localhost:8000` |

`LANGSMITH_*` variables are picked up by LangSmith for tracing if you set them.

---

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/travel` | Plan a trip. Returns the plan, or the question it paused on |
| `POST /api/travel/stream` | The same, as server-sent events reporting each agent as it runs |
| `POST /api/travel/resume` | Answer whatever the run paused on |
| `POST /api/travel/resume/stream` | The same, streamed |
| `GET /api/place?q=` | Photos and links for a place, for the in-app preview sheet |
| `GET /health` | Liveness check |

Every request carries a `thread_id`; that's the LangGraph thread, so the whole conversation's state
lives in the checkpoint rather than in the browser.

```bash
curl -X POST localhost:8000/api/travel \
  -H 'Content-Type: application/json' \
  -d '{"message": "Plan a 5 day Dubai trip from Delhi", "thread_id": "demo-1"}'
```

A finished response carries `final_response` (Markdown) alongside `brief`, `header`, `days`,
`hotels` and `costs` — the structured pieces the UI renders as cards.

---

## Project layout

```
backend/
  agent.py              the graph: state, agents, routing, structured output
  app.py                FastAPI endpoints, including the SSE streams
  mcp_client.py         MCP clients for Tavily, AviationStack and weather
  custom_weather_mcp.py a FastMCP server wrapping OpenWeather
  place_preview.py      cached Tavily REST search for previews and hotels
  tools/flight_tool.py  AviationStack flight lookup
frontend/src/
  components/           chat UI: the plan cards, composer, sidebar, link sheet
  lib/api.ts            typed client for the backend, and the SSE reader
  lib/threads.ts        threads in localStorage, via useSyncExternalStore
  app/api/              route handlers proxying to FastAPI
```

---

## Limitations

Worth being clear about, since a travel planner that looks confident is easy to over-trust.

- **No fares.** AviationStack's free tier returns live flight *status and schedules*, not ticket
  prices, and no dated search. The plan shows which flights operate the route, not what they cost.
- **Every figure is an estimate.** The cost breakdown is the model's reasoning about typical prices,
  not quotes. It's labelled as such throughout, and nothing here is booked or held.
- **Hotel data comes from web search**, so there are no live rates, availability or cancellation
  terms — just the hotel, its page, and why it suits the trip.
- **Threads live in your browser.** `localStorage` holds the conversation list; the backend keeps
  the graph state per `thread_id` but has no endpoint to list them, so clearing site data loses the
  index.
- **Forecasts only reach a few days out**, so a trip planned months ahead is planned without them.

---

## License

No license file yet, so default copyright applies — add a `LICENSE` if you want others to reuse it.
