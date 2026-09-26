"""The product read on the runs table: who got what they came for, and what it cost to serve.

    python -m stats            # the last 30 days
    python -m stats --days 7
    python -m stats --since-launch 2026-10-01

The evals answer whether the agents decide correctly. This answers whether people get a trip, which
is a different question and the one that decides what to build next.

A caveat worth keeping in mind: development traffic counts too. Clear the table before the numbers
are meant to mean anything (DELETE FROM runs).
"""
import argparse
from datetime import datetime

import db


def bar(fraction: float, width: int = 24) -> str:
    filled = round(fraction * width)
    return "█" * filled + "·" * (width - filled)


def line(label: str, value, of=None, note=""):
    if of:
        share = value / of if of else 0
        print(f"  {label:<34}{value:>6}  {bar(share)} {share:5.0%}  {note}")
    else:
        print(f"  {label:<34}{value:>6}  {note}")


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--days", type=int, default=30, help="how far back to look (default 30)")
parser.add_argument("--since-launch", help="an ISO date to count from instead, e.g. 2026-10-01")
args = parser.parse_args()

if args.since_launch:
    since, window = datetime.fromisoformat(args.since_launch), f"since {args.since_launch}"
else:
    since, window = None, f"the last {args.days} days"

where = "created_at >= %s" if since else "created_at >= now() - make_interval(days => %s)"
bound = (since or args.days,)

total = db.fetch(f"SELECT count(*) AS n FROM runs WHERE {where}", bound)[0]["n"]
if not total:
    print(f"\nNo runs in {window}. Plan a trip, then run this again.\n")
    raise SystemExit(0)

print(f"\nITINERA — {window}\n")

# ── Who turned up ────────────────────────────────────────────────────────────────────────────────
people = db.fetch(f"""
    SELECT count(DISTINCT thread_id) AS threads,
           count(DISTINCT user_id) FILTER (WHERE user_id IS NOT NULL) AS accounts,
           count(*) FILTER (WHERE user_id IS NULL) AS guest_runs
    FROM runs WHERE {where}
""", bound)[0]

print("REACH")
line("trips started", people["threads"])
line("runs in total", total, note="a trip is one run, plus one per refinement")
line("signed-in accounts", people["accounts"])
line("runs by guests", people["guest_runs"], total)

# ── The funnel: does a first message become a trip? ───────────────────────────────────────────────
# Only the first run of each thread, because that is the one someone can walk away from
funnel = db.fetch(f"""
    WITH first_runs AS (
        SELECT DISTINCT ON (thread_id) thread_id, outcome
        FROM runs WHERE {where}
        ORDER BY thread_id, created_at
    )
    SELECT outcome, count(*) AS n FROM first_runs GROUP BY outcome
""", bound)
first = {row["outcome"]: row["n"] for row in funnel}
starts = sum(first.values())

print("\nFIRST MESSAGE")
line("asked for trip details", first.get("asked", 0), starts, "← the step people can abandon")
line("planned straight away", first.get("delivered", 0), starts)
line("turned away (not travel)", first.get("refused", 0), starts)
line("failed", first.get("failed", 0), starts)

# Of the threads that were asked for details, how many came back with them?
answered = db.fetch(f"""
    WITH asked AS (
        SELECT DISTINCT ON (thread_id) thread_id, outcome
        FROM runs WHERE {where} ORDER BY thread_id, created_at
    )
    SELECT
      count(*) FILTER (WHERE r.source = 'answer') AS answered,
      count(*) FILTER (WHERE r.source = 'skip')   AS skipped,
      count(DISTINCT a.thread_id)                 AS asked
    FROM asked a
    LEFT JOIN runs r ON r.thread_id = a.thread_id AND r.source IN ('answer', 'skip')
    WHERE a.outcome = 'asked'
""", bound)[0]

if answered["asked"]:
    print("\nOF THOSE ASKED FOR DETAILS")
    line("answered the questions", answered["answered"], answered["asked"])
    line("skipped them", answered["skipped"], answered["asked"])
    line("never came back", answered["asked"] - answered["answered"] - answered["skipped"],
         answered["asked"], "← lost here")

# ── Did the trip land? ────────────────────────────────────────────────────────────────────────────
landed = db.fetch(f"""
    SELECT count(DISTINCT thread_id) FILTER (WHERE outcome = 'delivered') AS got_a_trip,
           count(DISTINCT thread_id) AS all_threads
    FROM runs WHERE {where}
""", bound)[0]

refinements = db.fetch(f"""
    WITH ranked AS (
        SELECT thread_id, row_number() OVER (PARTITION BY thread_id ORDER BY created_at) AS nth
        FROM runs WHERE {where} AND source = 'message'
    )
    SELECT count(*) FILTER (WHERE nth > 1) AS refinements,
           count(DISTINCT thread_id) FILTER (WHERE nth > 1) AS threads_refined
    FROM ranked
""", bound)[0]

print("\nDID IT LAND")
line("trips that produced a plan", landed["got_a_trip"], landed["all_threads"],
     "← the number that matters")
line("trips refined afterwards", refinements["threads_refined"], landed["got_a_trip"],
     "← a proxy for it being worth fixing")
line("refinements in total", refinements["refinements"])

# ── What it costs to serve ────────────────────────────────────────────────────────────────────────
cost = db.fetch(f"""
    SELECT outcome,
           count(*) AS n,
           round(avg(llm_calls)::numeric, 1) AS calls,
           round(avg(duration_ms)::numeric / 1000, 1) AS secs,
           -- percentile_cont returns double precision, which round(value, places) won't take
           round((percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms))::numeric / 1000, 1) AS p95
    FROM runs WHERE {where} GROUP BY outcome ORDER BY count(*) DESC
""", bound)

print("\nWHAT A RUN COSTS")
print(f"  {'outcome':<16}{'runs':>6}{'model calls':>14}{'avg':>8}{'p95':>8}")
for row in cost:
    print(f"  {row['outcome']:<16}{row['n']:>6}{row['calls']:>14}{row['secs']:>7}s{row['p95']:>7}s")

# ── Where people want to go ───────────────────────────────────────────────────────────────────────
places = db.fetch(f"""
    SELECT destination, count(DISTINCT thread_id) AS n
    FROM runs WHERE {where} AND destination IS NOT NULL
    GROUP BY destination ORDER BY n DESC, destination LIMIT 8
""", bound)

if places:
    print("\nWHERE THEY WANT TO GO")
    for row in places:
        line(row["destination"], row["n"])

print()
