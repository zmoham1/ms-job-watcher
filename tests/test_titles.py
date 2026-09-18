"""Regression tests for title classification under watcher.config.json.

Run: `python3 tests/test_titles.py` (no pytest, no deps — same as watcher.py).

These assert the CONFIGURED behavior, i.e. watcher.py's defaults as overridden by
watcher.config.json. The search is currently aimed at business-analyst and
project-coordinator roles, with software-engineering titles deliberately excluded.

Both "yes" and "maybe" are emailed — only "no" is dropped — so a title landing in
"maybe" is still a delivered alert, just ranked lower in the digest.

The trap this guards: HARD_EXCLUDE_PHRASES short-circuits in classify_title() BEFORE
any include is considered, so one over-broad exclude term silently kills a whole role
family no matter what is in the include list. "reporting" did exactly that to
"Business Analyst - Reporting"; it now lives in soft-exclude instead.
"""

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("watcher", os.path.join(_HERE, os.pardir, "watcher.py"))
watcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(watcher)

FAILURES = []


def check(title, expected):
    got = watcher.classify_title(title)
    if got != expected:
        FAILURES.append(f"{title!r}: got {got!r}, expected {expected!r}")


def emailed(title):
    """yes and maybe both reach the inbox; no does not."""
    got = watcher.classify_title(title)
    if got == "no":
        FAILURES.append(f"{title!r}: classified 'no' — would NOT be emailed")


# --- the config must actually be loaded; without it everything below is meaningless --
if not watcher.CONFIG:
    print("FAILED: watcher.config.json did not load")
    sys.exit(1)
check_cfg = [
    ("business analyst in strong-include", "business analyst" in watcher.STRONG_INCLUDE_PHRASES, True),
    ("business analyst NOT hard-excluded", "business analyst" in watcher.HARD_EXCLUDE_PHRASES, False),
    ("reporting NOT hard-excluded", "reporting" in watcher.HARD_EXCLUDE_PHRASES, False),
    ("reporting is soft-excluded", "reporting" in watcher.SOFT_EXCLUDE_PHRASES, True),
]
for label, got, want in check_cfg:
    if got != want:
        FAILURES.append(f"config {label}: got {got}, expected {want}")

# --- core business-analyst family must all be delivered ------------------------------
for t in [
    "Business Analyst",
    "Business Analyst I",
    "Business Analyst II",
    "Business Analyst (Remote)",
    "Associate Business Analyst",
    "IT Business Analyst",
    "Technical Business Analyst",
    "Business Systems Analyst",
    "Business Process Analyst",
    "Business Operations Analyst",
    "Business Intelligence Analyst",
    "Business Technology Analyst",
    "Business Data Analyst",
    "BI Analyst",
    "Systems Analyst",
    "Data Analyst",
    "Product Analyst",
    # Seniority downgrades these to "maybe", which is still emailed.
    "Sr. Business Analyst",
    "Senior Business Analyst",
    # The "reporting" hard-exclude used to drop these outright.
    "Business Analyst - Reporting",
    "Business Analyst, Reporting & Insights",
    # The other configured target role.
    "Project Coordinator",
]:
    emailed(t)

# --- and must stay out of the software-engineering roles the config excludes ---------
check("Software Engineer", "no")
check("Senior Backend Engineer", "no")
check("Full Stack Developer", "no")
check("QA Tester", "no")
check("Sales Manager", "no")
check("Site Reliability Engineer", "no")
# Internships stay excluded even when the role title otherwise matches.
check("Business Analyst Intern", "no")


if FAILURES:
    print(f"FAILED ({len(FAILURES)}):")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("All title classification tests passed.")
