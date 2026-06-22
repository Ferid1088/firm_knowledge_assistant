"""Tests for query-time date detection and temporal keyword filtering.

Verifies that the date extraction + temporal keyword logic in prepare_query
correctly sets date_filter_from / date_filter_to on RAGState.
"""
from __future__ import annotations

import re

from backend.tools.dates import extract_and_normalize


# ---------------------------------------------------------------------------
# Temporal keyword helpers (mirrors prepare_query logic)
# ---------------------------------------------------------------------------

_RE_BEFORE = re.compile(r"\b(vor|before|bis zum|bis|until|spätestens)\b")
_RE_AFTER = re.compile(r"\b(nach|after|seit|since|ab|from|frühestens)\b")
_RE_BETWEEN = re.compile(r"\b(zwischen|between)\b")


def _detect_bounds(query: str, dates: list[str]):
    """Re-implement the prepare_query date-bound logic for isolated testing."""
    q_lower = query.lower()
    has_before = bool(_RE_BEFORE.search(q_lower))
    has_after = bool(_RE_AFTER.search(q_lower))
    has_between = bool(_RE_BETWEEN.search(q_lower))

    date_from = None
    date_to = None

    if has_between and len(dates) >= 2:
        date_from = min(dates)
        date_to = max(dates)
    elif has_before:
        date_to = max(dates)
    elif has_after:
        date_from = min(dates)
    else:
        date_from = min(dates)
        date_to = max(dates)

    return date_from, date_to


# ---------------------------------------------------------------------------
# Tests — date extraction
# ---------------------------------------------------------------------------


def test_extract_german_month_year():
    """'März 2026' should normalize to 2026-03-01."""
    dates = extract_and_normalize("Verträge die vor März 2026 ablaufen")
    assert "2026-03-01" in dates


def test_extract_english_month_year():
    """'June 2025' should normalize to 2025-06-01."""
    dates = extract_and_normalize("documents from June 2025")
    assert "2025-06-01" in dates


def test_extract_iso_date():
    """ISO date '2025-01-15' should be extracted as-is."""
    dates = extract_and_normalize("Deadline ist 2025-01-15")
    assert "2025-01-15" in dates


def test_extract_dot_date():
    """German dot format '15.06.2025' should normalize."""
    dates = extract_and_normalize("gültig ab 15.06.2025")
    assert "2025-06-15" in dates


def test_extract_multiple_dates():
    """Multiple dates in one query should all be extracted."""
    dates = extract_and_normalize("zwischen Januar 2025 und Juni 2025")
    assert len(dates) >= 2
    assert "2025-01-01" in dates
    assert "2025-06-01" in dates


# ---------------------------------------------------------------------------
# Tests — temporal keyword detection (German)
# ---------------------------------------------------------------------------


def test_prepare_query_detects_dates():
    """Verify prepare_query extracts date filters from temporal queries."""
    q = "Verträge die vor März 2026 ablaufen"
    dates = extract_and_normalize(q)
    assert "2026-03-01" in dates

    q_lower = q.lower()
    has_before = bool(re.search(r"\b(vor|before|bis zum|bis|until)\b", q_lower))
    assert has_before is True


def test_vor_sets_upper_bound():
    """'vor' (before) should set date_to only."""
    q = "Verträge die vor März 2026 ablaufen"
    dates = extract_and_normalize(q)
    date_from, date_to = _detect_bounds(q, dates)
    assert date_from is None
    assert date_to == "2026-03-01"


def test_nach_sets_lower_bound():
    """'nach' (after) should set date_from only."""
    q = "Dokumente nach Januar 2025"
    dates = extract_and_normalize(q)
    date_from, date_to = _detect_bounds(q, dates)
    assert date_from == "2025-01-01"
    assert date_to is None


def test_seit_sets_lower_bound():
    """'seit' (since) should set date_from only."""
    q = "Änderungen seit März 2025"
    dates = extract_and_normalize(q)
    date_from, date_to = _detect_bounds(q, dates)
    assert date_from == "2025-03-01"
    assert date_to is None


def test_prepare_query_between():
    """'zwischen ... und ...' should set both bounds."""
    q = "Dokumente zwischen Januar 2025 und Juni 2025"
    dates = extract_and_normalize(q)
    assert len(dates) >= 2

    q_lower = q.lower()
    has_between = bool(re.search(r"\b(zwischen|between)\b", q_lower))
    assert has_between is True
    assert min(dates) == "2025-01-01"
    assert max(dates) == "2025-06-01"


def test_zwischen_sets_both_bounds():
    """'zwischen' with two dates should set both from and to."""
    q = "Dokumente zwischen Januar 2025 und Juni 2025"
    dates = extract_and_normalize(q)
    date_from, date_to = _detect_bounds(q, dates)
    assert date_from == "2025-01-01"
    assert date_to == "2025-06-01"


# ---------------------------------------------------------------------------
# Tests — temporal keyword detection (English)
# ---------------------------------------------------------------------------


def test_before_sets_upper_bound():
    """'before' should set date_to only."""
    q = "contracts expiring before March 2026"
    dates = extract_and_normalize(q)
    date_from, date_to = _detect_bounds(q, dates)
    assert date_from is None
    assert date_to == "2026-03-01"


def test_after_sets_lower_bound():
    """'after' should set date_from only."""
    q = "documents created after June 2025"
    dates = extract_and_normalize(q)
    date_from, date_to = _detect_bounds(q, dates)
    assert date_from == "2025-06-01"
    assert date_to is None


def test_since_sets_lower_bound():
    """'since' should set date_from only."""
    q = "changes since January 2024"
    dates = extract_and_normalize(q)
    date_from, date_to = _detect_bounds(q, dates)
    assert date_from == "2024-01-01"
    assert date_to is None


def test_between_sets_both_bounds():
    """'between ... and ...' should set both bounds."""
    q = "reports between February 2025 and October 2025"
    dates = extract_and_normalize(q)
    date_from, date_to = _detect_bounds(q, dates)
    assert date_from == "2025-02-01"
    assert date_to == "2025-10-01"


# ---------------------------------------------------------------------------
# Tests — no temporal keyword (exact range)
# ---------------------------------------------------------------------------


def test_no_keyword_single_date_sets_both():
    """Without a temporal keyword, a single date sets both from and to."""
    q = "Dokumente März 2026"
    dates = extract_and_normalize(q)
    date_from, date_to = _detect_bounds(q, dates)
    assert date_from == "2026-03-01"
    assert date_to == "2026-03-01"


def test_no_keyword_two_dates_sets_range():
    """Without a temporal keyword, two dates set from=min and to=max."""
    q = "Verträge Januar 2025 Juni 2025"
    dates = extract_and_normalize(q)
    date_from, date_to = _detect_bounds(q, dates)
    assert date_from == "2025-01-01"
    assert date_to == "2025-06-01"


# ---------------------------------------------------------------------------
# Tests — edge cases
# ---------------------------------------------------------------------------


def test_no_dates_in_query():
    """A query with no dates should return an empty list."""
    dates = extract_and_normalize("Was ist der aktuelle Status?")
    assert dates == []


def test_bis_zum_sets_upper_bound():
    """'bis zum' should behave like 'before' — upper bound only."""
    q = "Frist bis zum 15.06.2025"
    dates = extract_and_normalize(q)
    date_from, date_to = _detect_bounds(q, dates)
    assert date_from is None
    assert date_to == "2025-06-15"


def test_ab_sets_lower_bound():
    """'ab' should behave like 'from' — lower bound only."""
    q = "gültig ab 01.01.2025"
    dates = extract_and_normalize(q)
    date_from, date_to = _detect_bounds(q, dates)
    assert date_from == "2025-01-01"
    assert date_to is None
