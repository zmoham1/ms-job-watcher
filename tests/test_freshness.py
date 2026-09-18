"""Regression tests for the posted-date freshness gate.

Run: `python3 tests/test_freshness.py` (no pytest, no deps — same as watcher.py).

Why this file exists: a matched job whose `posted` string doesn't parse is invisible.
It isn't logged, isn't emailed, and looks identical to "nothing new was posted", so
Workday, Ashby, Amazon and Goldman Sachs silently emailed nothing for months while
`run_log.json` showed thousands of matches. Every format below is a real ATS shape —
if a parser change breaks one, that source goes dark again with no other symptom.
"""

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("watcher", os.path.join(_HERE, os.pardir, "watcher.py"))
watcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(watcher)

NOW = datetime.now(timezone.utc)
FAILURES = []


def check(label, got, expected):
    if got != expected:
        FAILURES.append(f"{label}: got {got!r}, expected {expected!r}")


def fresh(posted, hours=24, **kw):
    return watcher.job_is_fresh_enough({"posted": posted}, hours, **kw)


def iso(**delta):
    return (NOW - timedelta(**delta)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def ymd(days):
    return (NOW - timedelta(days=days)).strftime("%Y-%m-%d")


def long_date(days):
    return (NOW - timedelta(days=days)).strftime("%B %d, %Y")


# --- Workday: `postedOn` is always display text, never a timestamp -------------------
check("workday today", fresh("Posted Today"), True)
check("workday just posted", fresh("Just Posted"), True)
check("workday hours", fresh("Posted 6 Hours Ago"), True)
# Calendar-yesterday can be an hour old, and a board is only revisited every ~10-19h,
# so a day-granularity date must resolve to the most recent instant it could mean.
check("workday yesterday", fresh("Posted Yesterday"), True)
check("workday 1 day", fresh("Posted 1 Day Ago"), True)
check("workday 2 days", fresh("Posted 2 Days Ago"), False)
check("workday 30+ days", fresh("Posted 30+ Days Ago"), False)
check("workday 1 week", fresh("Posted 1 Week Ago"), False)
# Coarse units are NOT widened — "1 Month Ago" must not become "now".
check("workday 1 month", fresh("Posted 1 Month Ago"), False)

# --- Amazon: posted_date is "March 3, 2026" -----------------------------------------
check("amazon today", fresh(long_date(0)), True)
check("amazon yesterday", fresh(long_date(1)), True)
check("amazon 3 days", fresh(long_date(3)), False)
check("amazon abbrev", fresh((NOW - timedelta(days=5)).strftime("%b %d, %Y")), False)

# --- Date-only absolute (Oracle PostedDate, IBM dcdate, Greenhouse on some boards) ---
check("date-only today", fresh(ymd(0)), True)
check("date-only yesterday", fresh(ymd(1)), True)
check("date-only 2 days", fresh(ymd(2)), False)

# --- Full timestamps must stay EXACT (not widened by a day) -------------------------
check("iso 10h", fresh(iso(hours=10)), True)
check("iso 30h", fresh(iso(hours=30)), False)
check("iso 25h", fresh(iso(hours=25)), False)
check("lever epoch-ms", fresh(int((NOW - timedelta(hours=2)).timestamp() * 1000)), True)
check("eightfold ' UTC'", fresh((NOW - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M UTC")), True)

# --- Unparseable / absent: the policy switch, not a silent drop ----------------------
for blank in ("", None, "n/a", "Posted recently"):
    check(f"unknown keep {blank!r}", fresh(blank, unknown_ok=True), True)
    check(f"unknown drop {blank!r}", fresh(blank, unknown_ok=False), False)

# No freshness gate at all => everything passes regardless of date.
check("no gate", fresh("", hours=None), True)
check("no gate garbage", fresh("not a date", hours=None), True)

# --- Clamping: a resolved date must never be pushed into the future ------------------
resolved = watcher.parse_posted_datetime(ymd(0))
check("today clamped to now", resolved <= datetime.now(timezone.utc), True)
# A genuinely future-dated posting is left alone and counts as fresh.
check("future date passes", fresh((NOW + timedelta(days=5)).strftime("%Y-%m-%d")), True)

# --- Ashby normalizer must carry the date through ------------------------------------
ashby = watcher.normalize_ashby_job("Acme", "acme", {"id": "1", "title": "SWE", "publishedAt": iso(hours=3)})
check("ashby posted populated", bool(ashby["posted"]), True)
check("ashby fresh", watcher.job_is_fresh_enough(ashby, 24), True)
# Falls back to updatedAt, and stays empty (=> policy switch) when the schema has neither.
check("ashby updatedAt fallback", bool(watcher.normalize_ashby_job("A", "a", {"id": "1", "updatedAt": iso(hours=1)})["posted"]), True)
check("ashby no date field", watcher.normalize_ashby_job("A", "a", {"id": "1"})["posted"], "")


if FAILURES:
    print(f"FAILED ({len(FAILURES)}):")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("All freshness tests passed.")
