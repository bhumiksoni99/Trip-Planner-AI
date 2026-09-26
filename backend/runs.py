"""What each run of the graph did, recorded so the product questions can be answered with numbers.

The evals measure whether the agents decide correctly. This measures whether people get what they
came for: how many who start a trip end up with one, where they drop out, and what a plan costs to
serve. Nothing here is read on the request path; it is written once per run and read by stats.py.

Recording must never break a plan, so every write is wrapped and a failure is logged and dropped.
"""
import logging

import db

logger = logging.getLogger("travel.runs")

# What the traveller did to start this run
SOURCES = ("message", "answer", "skip")

# How it ended. "asked" is a run that stopped to ask for trip details and is waiting on an answer,
# which is the step most likely to lose someone
OUTCOMES = ("delivered", "asked", "refused", "failed")


def outcome_of(result: dict, agents: list[str] | None) -> str:
    """Reads the finished run's payload the same way the UI does, so this can't drift from it."""
    if result.get("pause_type"):
        return "asked"

    # The guardrail turns a non-travel message away before any specialist runs, so the supervisor is
    # the only agent that ever started
    if agents:
        specialists = [name for name in agents if name not in ("supervisor_agent", "__start__")]
        return "delivered" if specialists else "refused"

    # The non-streaming route reports no agents at all, and one model call with no trip to show for
    # it says the same thing
    if (result.get("llm_calls") or 0) <= 1 and not result.get("header"):
        return "refused"

    return "delivered"


def record(thread_id: str, user_id: str | None, source: str, outcome: str,
           agents: list[str], llm_calls: int, duration_ms: int, destination: str | None):
    """One row per run. Returns whether it was written, which only the tests care about."""
    try:
        db.execute(
            """
            INSERT INTO runs (thread_id, user_id, source, outcome, agents, llm_calls, duration_ms, destination)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (thread_id, user_id, source, outcome,
             [name for name in agents if name and not name.startswith("__")],
             int(llm_calls or 0), int(duration_ms or 0), (destination or None)),
        )
        return True
    except Exception:
        # A plan that worked must not fail because its bookkeeping didn't
        logger.warning("runs | couldn't record %s/%s for thread %s", source, outcome, thread_id, exc_info=True)
        return False


def from_result(thread_id: str, user_id: str | None, source: str, result: dict,
                agents: list[str], duration_ms: int):
    """Records a finished run straight from the payload the stream ends with."""
    header = result.get("header") or {}
    return record(
        thread_id=thread_id,
        user_id=user_id,
        source=source,
        outcome=outcome_of(result, agents),
        agents=agents,
        llm_calls=result.get("llm_calls") or 0,
        duration_ms=duration_ms,
        destination=header.get("destination"),
    )
