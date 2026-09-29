"""How often one caller may do something, so a login can't be guessed at and a plan can't be farmed.

A sliding window kept in this process's memory. That is the right size for how this runs — one uvicorn
process, no Redis — and its limits are worth being honest about: the counts reset when the process
restarts, and a second instance would keep its own. Moving them to Redis or a Postgres table is a
change to `hits()` alone; nothing that calls this would need to know.

Every limit is set in seconds and attempts through the environment, so a load test or a demo can raise
them without a code change.
"""
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

# attempts, window in seconds
LOGIN_PER_IP = (int(os.getenv("RATE_LOGIN_PER_IP", "10")), 900)
LOGIN_PER_EMAIL = (int(os.getenv("RATE_LOGIN_PER_EMAIL", "5")), 900)
PLANS = (int(os.getenv("RATE_PLANS", "30")), 3600)
PREVIEWS = (int(os.getenv("RATE_PREVIEWS", "60")), 60)

# Every timestamp older than the longest window is dead weight, so the whole table is swept
# occasionally rather than scanned on every call
SWEEP_EVERY = 300

_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()
_last_sweep = time.monotonic()


def _sweep(now: float) -> None:
    """Drops keys nobody has touched for a while. Called with the lock held."""
    global _last_sweep
    if now - _last_sweep < SWEEP_EVERY:
        return

    for key in [key for key, times in _hits.items() if not times or now - times[-1] > 3600]:
        del _hits[key]
    _last_sweep = now


def hits(key: str, allowed: int, window: int) -> float | None:
    """Records one attempt. None when it is within the limit, or the seconds to wait when it isn't.

    A refused attempt is not recorded: otherwise someone hammering the door would keep pushing their
    own unlock further away, and a caller who backs off as asked would never get back in.
    """
    now = time.monotonic()

    with _lock:
        _sweep(now)
        times = _hits[key]

        while times and now - times[0] >= window:
            times.popleft()

        if len(times) >= allowed:
            return window - (now - times[0])

        times.append(now)
        return None


def client_ip(request: Request) -> str:
    """The caller's address as the nearest trusted proxy saw it.

    Cloudflare sits in front of the deployed backend and sets cf-connecting-ip, replacing any copy the
    caller sent, so that one is trusted first. Failing that, the last entry of X-Forwarded-For is the
    one our own proxy appended; the earlier entries are whatever the caller claimed and can be
    anything, which is why the first is not used.
    """
    cloudflare = request.headers.get("cf-connecting-ip")
    if cloudflare:
        return cloudflare.strip()

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()

    return request.client.host if request.client else "unknown"


def caller(request: Request, user: dict | None) -> str:
    """Who to count against: the account when there is one, since an id can't be spoofed or shared
    the way an address behind a mobile network can."""
    return f"user:{user['id']}" if user else f"ip:{client_ip(request)}"


def enforce(key: str, limit: tuple[int, int], message: str) -> None:
    """Raises 429 with a Retry-After the caller can act on, or returns quietly."""
    allowed, window = limit
    wait = hits(key, allowed, window)
    if wait is None:
        return

    raise HTTPException(
        status_code=429,
        detail=message,
        headers={"Retry-After": str(max(1, int(wait)))},
    )
