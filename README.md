# Itinera AI

A multi-agent travel planner. You describe a trip in one sentence; a graph of specialist agents
asks for whatever you left out, searches live flights, weather and hotels, writes a day-by-day
itinerary, costs it against your budget, and returns a plan you can keep refining in the chat.

Built with [LangGraph](https://langchain-ai.github.io/langgraph/), Google Gemini, FastAPI and Next.js.

```
"Plan a 5 day Dubai trip from Delhi under 2 lakhs"
   ↓
   asks for the dates and vibe you didn't mention
   ↓
   flights + weather + photo at once → itinerary → hotels → budget
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
- [Evals](#evals)
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

**Shows its work while it works.** A plan takes half a minute, so the run streams over server-sent
events and the UI ticks off each agent as it starts and finishes — you can see it searching flights
rather than watching a spinner.

**Keeps its links honest.** Places in the itinerary link to a Google search; hotels link to the
hotel's own page. Both open in an in-app sheet rather than sending you off the site.

**Saves your trips, if you want it to.** Planning works without an account. Log in with an email and
password and your trips follow you to any browser — including the ones you planned before logging in,
which are handed over on the way in.

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
   flight_agent  ─┐
   weather_agent ─┼─► itinerary_agent → hotel_agent → budget_agent
   photo_agent   ─┘
                      │
                      ▼
            final_response_agent ──► END
```

| Agent | What it does |
|---|---|
| `supervisor_agent` | Guardrails non-travel requests, and decides whether a message starts a new trip or refines the current one |
| `intake_agent` | Extracts the trip's terms from your message, then `interrupt()`s to ask for what's missing |
| `flight_agent` | Live flight schedules for the route, via AviationStack |
| `weather_agent` | Current conditions and a 5-day forecast from OpenWeather, both fetched at once |
| `photo_agent` | Finds a photo of the destination for the plan's header card |
| `itinerary_agent` | Writes the day-by-day plan as structured days and activities |
| `hotel_agent` | Finds two hotels per city the itinerary stays in, and resolves each to its own page |
| `budget_agent` | Costs the trip line by line and judges it against your budget |
| `feedback_agent` | Reads your feedback and picks which specialists must run again |
| `final_response_agent` | Combines everything into the written plan, plus a one-line summary |
| `hil_agent` | An optional approve/request-changes gate, off by default (see below) |

Flights, weather and the photo need only the trip's details, so `start_planning` sends them out
together and LangGraph runs the itinerary once all of them have finished. The itinerary, hotels and
budget then run in turn, because each needs the one before: hotels are searched for the cities the
itinerary stays in. Only the specialists the supervisor selected run at all, so a weather-only
question doesn't search for hotels.

The join is a conditional edge from each parallel agent to the same next node, not
`add_edge([...], target)`: that form waits for every listed node, so it would hang on a trip where
the supervisor skipped flights.

---

## Design decisions worth knowing

**Chats are stored once, by LangGraph.** Every run is checkpointed in Postgres under a `thread_id`, and
that checkpoint already holds the conversation. So accounts don't copy any of it: a `chats` row records
who owns a `thread_id`, its title and when it was last used, and a user has many of those rows. Opening
a chat rebuilds it from the checkpoint.

Two details make that work. The replies a traveller should see are tagged `name="reply"` and carry their
own cards, because the state itself only ever holds the newest plan's cards, so a second plan in the same
chat would otherwise take the first one's. And the agents' own notes to each other ("Weather Fetched")
are filtered out.

**Guests don't need an account.** A guest's chats sit in the database with no owner; their browser only
remembers the ids. Logging in claims those ids, which skips over any that already belong to someone else,
so a stray id can't take another person's chat. Someone else's chat answers 404, never 403, so the reply
doesn't reveal that it exists.

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

**One model call per decision, not one per question.** A plan used to make ten model calls; it now
makes six. The guardrail and the agent selection were one decision read twice, so they became a single
`SupervisorDecision`, and the same merge happened for the follow-up classifier. The itinerary writer
now returns the cities it has you sleeping in as part of its own output, which removed a call that
re-read the itinerary to work them out — and removed the mistakes it made, since sightseeing stops
were being counted as stays. With the parallel fan-out above, a five-day plan that took 45–75 s
finishes in under 30 s.

**MCP is available, but not on the hot path.** The repo has a FastMCP weather server
(`custom_weather_mcp.py`) and an MCP client for it and for Tavily (`mcp_client.py`), but the agents
call the underlying tools directly. The MCP adapter opens a fresh session for every call, which for a
stdio server means starting a new Python subprocess: a weather lookup measured 3.4 s that way against
0.2 s calling the same function in-process. The server wraps the same functions the agent uses
(`tools/weather_tool.py`), so both stay in step. Tavily goes over REST for a second reason too: its MCP
tool flattens results into one block of text, which loses the per-result URLs the hotel cards need.

**Search results are filtered before they're shown.** Hotel searches return round-up articles as
often as hotels, so a title like "The 10 best hotels in Zurich" never becomes a hotel card.

---

## Evals

Making the graph faster means merging and deleting model calls, and a prompt that answers well with
its own call doesn't always answer as well once it's doing two jobs. So the graph's decisions are
measured before and after each change, and `backend/evals/` is what does the measuring.

Each eval calls **the production agent**, not a copy of its prompt, and scoring is **plain Python** —
no model grading a model — so the same output always gets the same score.

| Set | Rows | The decision it pins down |
|---|---|---|
| `guardrail` | 25 | Is this travel, and which specialists should run |
| `extraction` | 20 | Destination, dates, budget, vibe, and the city and airport codes the agents use |
| `replan` | 22 | Is a follow-up a refinement or a new trip, and what has to run again |
| `stays` | 15 | Which cities the itinerary sleeps in, and for how many nights |
| `itinerary` | 6 | The day plan's shape: right number of days, no empty ones |

The rows come from real traces, including the requests that went wrong, and the expectations were
settled by hand.

```bash
cd backend
python -m evals.run guardrail                # one set
python -m evals.run all --reps 2 --label baseline
python -m evals.wiring                       # the whole graph, every API faked
```

`--reps` runs a set several times as separate experiments, because a model doesn't answer identically
twice: the spread between reps is the noise a change has to beat before it means anything. Runs land in
LangSmith when it's configured and in `evals/results/` either way. `evals/wiring.py` is the other half —
it runs the real graph end to end with every external call faked, so it checks routing, fan-out and
resume in about a second without spending an API call.

Where it stands, at the latest run of each set, over two repetitions:

```
guardrail    is it travel 25/25    which agents run 14/15    the non-travel part 16–17/17
extraction   destination 20/20   dates 19/19   budget 19/19   vibe 14/14   airports 20/20
replan       refinement or new trip 19/20      what has to re-run 18/18
stays        cities 14/15   nights 13–14/14    day trips not counted 5/5
itinerary    stays listed 6/6   real places 6/6   nights add up 5–6/6
```

A row is only scored on the checks it declares, which is why the denominators differ, and a range is
where the two repetitions disagreed — that spread is the noise, not a result.

These found real defects rather than confirming the code was fine: the selector was dropping flights
and hotels from plans that needed them, the weather city came back empty on some requests, day trips
were being counted as places you sleep, and a hotel change was forcing a full itinerary rewrite.

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

cp .env.example .env                              # then fill in your keys
echo "JWT_SECRET=$(openssl rand -base64 48)" >> .env

cd backend && uvicorn app:app --reload --port 8000
```

An empty database is fine: the checkpointer creates its own tables on first run, and `db.py` creates
the `users` and `chats` tables at startup.

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
docker build -t itinera-backend backend/
docker run --env-file .env -p 8000:8000 itinera-backend
```

---

## Configuration

All of it comes from a `.env` at the repo root.

| Variable | Required | What it's for |
|---|---|---|
| `GEMINI_API_KEY` | yes | Every LLM call, via `gemini-2.5-flash-lite` |
| `TAVILY_API_KEY` | yes | Web search: hotels, places and link previews |
| `AVIATIONSTACK_API_KEY` | yes | Live flight schedules |
| `OPENWEATHER_API_KEY` | yes | Current weather and the forecast, for the agent and the weather MCP server |
| `POSTGRES_DB` | yes | Connection string for the checkpoints, and for the accounts and chats tables |
| `JWT_SECRET` | yes | Signs login tokens; at least 32 characters |
| `DB_POOL_SIZE` | no | Database connections to keep, default `4` |
| `GEMINI_TIMEOUT_SECONDS` | no | How long a model call may hang before it errors, default `60` |
| `DEFAULT_ORIGIN` | no | Fallback departure airport, default `DEL` |
| `DEFAULT_ORIGIN_CITY` | no | Fallback departure city, shown in intake options |
| `REQUIRE_APPROVAL` | no | `true` re-enables the approval pause, default `false` |
| `MAX_REVISIONS` | no | Revision cap when approval is on, default `3` |
| `LOG_LEVEL` | no | `DEBUG` for per-agent detail, default `INFO` |
| `BACKEND_URL` | no | Where the frontend proxies to, default `http://localhost:8000` |

`LANGSMITH_*` variables turn on tracing if you set them, and are what the eval runner reports its
experiments to.

---

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/travel` | Plan a trip. Returns the plan, or the question it paused on |
| `POST /api/travel/stream` | The same, as server-sent events reporting each agent as it runs |
| `POST /api/travel/resume` | Answer whatever the run paused on |
| `POST /api/travel/resume/stream` | The same, streamed |
| `GET /api/place?q=` | Photos and links for a place, for the in-app preview sheet |
| `POST /api/auth/signup` | Create an account; returns a login token |
| `POST /api/auth/login` | Log in; returns a login token |
| `GET /api/auth/me` | The account a token belongs to |
| `GET /api/chats` | The logged-in traveller's chats, newest first |
| `GET /api/chats/{thread_id}` | One chat, rebuilt from its checkpoint, with any question it's paused on |
| `DELETE /api/chats/{thread_id}` | Delete a chat and its checkpoints |
| `POST /api/chats/claim` | Hand the chats planned as a guest to the account just logged into |
| `GET /health` | Liveness check |

Every request carries a `thread_id`; that's the LangGraph thread, so the whole conversation's state
lives in the checkpoint rather than in the browser.

**Authentication** is an `Authorization: Bearer <token>` header. Listing, deleting and claiming chats
require one. The planning routes take one optionally — with a token the chat is saved to that account,
without one it's a guest chat — and every route that touches a `thread_id` answers 404 if that chat
belongs to someone else. The browser never sees a token: Next's route handlers keep it in an httpOnly
cookie and forward it.

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
  mcp_client.py         MCP clients for Tavily and the weather server (not on the request path)
  custom_weather_mcp.py a FastMCP server exposing the weather tool
  auth.py               password hashing and the login token
  chats.py              who owns which chat
  db.py                 the Postgres pool, and the users and chats tables
  place_preview.py      cached Tavily REST search for previews and hotels
  tools/flight_tool.py  AviationStack flight lookup
  tools/weather_tool.py OpenWeather current conditions and forecast
  evals/                datasets, scorers and the runner; wiring.py fakes every API
frontend/src/
  components/           chat UI: the plan cards, composer, sidebar, login dialog, link sheet
  lib/api.ts            typed client for the backend, and the SSE reader
  lib/threads.ts        the chat list, from the server, via useSyncExternalStore
  lib/activeThread.ts   which chat is open, kept in the URL as ?thread=
  lib/server/           server-only: the login cookie, and forwarding it as a Bearer token
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
- **A guest's trips are only as durable as their browser.** The chats are in the database either way,
  but a guest's browser is the only thing holding their ids, so clearing site data loses the way back
  to them. Logging in fixes that, and claims whatever ids that browser still has.
- **Forecasts only reach a few days out**, so a trip planned months ahead is planned without them.
- **Accounts are deliberately minimal.** No email verification, no password reset, no refresh tokens —
  a login lasts seven days and then expires — and no rate limit on the login route.

---

## License

No license file yet, so default copyright applies — add a `LICENSE` if you want others to reuse it.
