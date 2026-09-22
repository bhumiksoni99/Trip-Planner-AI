"""How each eval is scored: plain code, no model judging, so the same outputs always get the same score.

Each scorer compares a target's outputs with the dataset row's `expect` block and returns
(metric, passed, comment) for every check that row asks for. A row that doesn't mention a
metric isn't scored on it.
"""
import re
import unicodedata

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
}
EMPTY = {"", "null", "none", "n/a", "not specified", "unknown"}


def norm(text) -> str:
    """Lower case, accents dropped and spaces collapsed, so 'Buñol ' matches 'bunol'"""
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


def present(value) -> bool:
    return norm(value) not in EMPTY


def text_check(got, expected):
    """expected: None = must be empty (never guess), "*" = must be there, [..] = must contain one of these"""
    if expected is None:
        return not present(got), f"expected nothing, got {got!r}"
    if expected == "*":
        return present(got), f"expected something, got {got!r}"
    return present(got) and any(norm(option) in norm(got) for option in expected), f"expected one of {expected}, got {got!r}"


def duration_days(text) -> set:
    """Every day count a duration could mean: '5 days' -> {5}, '2 weeks' -> {2, 14}, 'weekend' -> {2, 3}"""
    lowered = norm(text)
    days = {int(n) for n in re.findall(r"\d+", lowered)}
    days |= {n for word, n in WORD_NUMBERS.items() if re.search(rf"\b{word}\b", lowered)}
    if "weekend" in lowered:
        days |= {2, 3}
    elif re.search(r"\b(week|weeks|fortnight)\b", lowered):
        days |= {n * 7 for n in days} or {7}
        if "fortnight" in lowered:
            days.add(14)
    return days


def agents_check(got: list, expected: dict):
    """Every 'must' agent picked and no 'must_not' one; 'may' agents are fine either way"""
    got = set(got or [])
    missing = set(expected.get("must", [])) - got
    unwanted = set(expected.get("must_not", [])) & got
    detail = []
    if missing:
        detail.append(f"missing {sorted(missing)}")
    if unwanted:
        detail.append(f"shouldn't run {sorted(unwanted)}")
    return not missing and not unwanted, "; ".join(detail) or f"ran {sorted(got)}"


def score_guardrail(out: dict, expect: dict):
    results = [("allowed", out["allowed"] == expect["allowed"], f"expected {expect['allowed']}, got {out['allowed']}")]

    if "off_topic" in expect and out["allowed"]:
        flagged = present(out["off_topic"])
        results.append(("off_topic", flagged == expect["off_topic"], f"expected {expect['off_topic']}, got {out['off_topic']!r}"))

    if "agents" in expect and out["allowed"]:
        results.append(("agents", *agents_check(out["agents"], expect["agents"])))

    if "trip_request_excludes" in expect and out["allowed"]:
        leaked = [term for term in expect["trip_request_excludes"] if term in norm(out["trip_request"])]
        results.append(("sanitised", not leaked, f"trip_request still mentions {leaked}: {out['trip_request']!r}"))

    return results


def score_extraction(out: dict, expect: dict):
    results = []

    for field in ("destination", "destination_city", "departure_city", "travel_dates", "budget", "vibe", "interests"):
        if field in expect:
            results.append((field, *text_check(out.get(field), expect[field])))

    for field in ("origin_iata", "destination_iata"):
        if field in expect:
            got = (out.get(field) or "").upper()
            results.append((field, got in expect[field], f"expected one of {expect[field]}, got {got!r}"))

    if "duration_days" in expect:
        wanted = expect["duration_days"]
        if wanted is None:
            results.append(("duration", not present(out.get("duration")), f"expected nothing, got {out.get('duration')!r}"))
        else:
            days = duration_days(out.get("duration"))
            results.append(("duration", bool(days & set(wanted)), f"expected {wanted} days, got {out.get('duration')!r}"))

    return results


def score_stays(out: dict, expect: dict):
    got = out["stays"]
    places = [norm(f"{stay.get('city', '')} {stay.get('area') or ''}") for stay in got]
    wanted = expect["stays"]

    # Walk both lists in trip order: every required stay found, in order, with nothing extra
    matched, position, missing = [], 0, []
    for expected_stay in wanted:
        found = next(
            (index for index in range(position, len(places))
             if any(norm(option) in places[index] for option in expected_stay["place"])),
            None,
        )
        if found is None:
            if not expected_stay["optional"]:
                missing.append(expected_stay["place"][0])
            continue
        matched.append((expected_stay, got[found]))
        position = found + 1

    extras = len(places) - len(matched)
    listed = [stay.get("city") for stay in got]
    results = [("stays", not missing and extras == 0, f"missing {missing}, {extras} extra; got {listed}")]

    wrong_nights = [
        f"{stay.get('city')}: {stay.get('nights')} not in {expected_stay['nights']}"
        for expected_stay, stay in matched
        if expected_stay["nights"] is not None and stay.get("nights") not in expected_stay["nights"]
    ]
    if matched:
        results.append(("nights", not wrong_nights, "; ".join(wrong_nights) or "all right"))

    if expect.get("exclude"):
        day_trips = [term for term in expect["exclude"] if any(term in place for place in places)]
        results.append(("no_day_trips", not day_trips, f"listed day trips as stays: {day_trips}"))

    return results


def score_replan(out: dict, expect: dict):
    results = [("is_travel", out["is_travel"] == expect["is_travel"], f"expected {expect['is_travel']}, got {out['is_travel']}")]
    if not out["is_travel"]:
        return results

    if "is_refinement" in expect:
        results.append(("is_refinement", out["is_refinement"] == expect["is_refinement"],
                        f"expected {expect['is_refinement']}, got {out['is_refinement']}"))

    if "off_topic" in expect:
        results.append(("off_topic", present(out["off_topic"]) == expect["off_topic"], f"got {out['off_topic']!r}"))

    if "trip_request_contains" in expect and not out["is_refinement"]:
        # The new trip has to be written out, not the message repeated: intake plans from this text
        names_place = any(term in norm(out["trip_request"]) for term in expect["trip_request_contains"])
        written_out = norm(out["trip_request"]) != norm(out.get("message"))
        results.append(("new_trip", names_place and written_out, f"trip_request {out['trip_request']!r}"))

    # Only scored when it was treated as a change; a misread new trip already fails is_refinement
    if "rerun" in expect and out["is_refinement"]:
        results.append(("rerun", *agents_check(out["rerun"], expect["rerun"])))

    return results


SCORERS = {"guardrail": score_guardrail, "extraction": score_extraction, "stays": score_stays, "replan": score_replan}
