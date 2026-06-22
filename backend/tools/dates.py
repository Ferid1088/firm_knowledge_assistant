"""Shared utility for extracting and normalizing dates from text to ISO-8601.

Supports German and English date patterns found in business/legal documents.
No external dependencies — uses only ``re`` and ``datetime`` from stdlib.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Month-name lookup (German + English, full + abbreviated)
# ---------------------------------------------------------------------------

_GERMAN_MONTHS: dict[str, int] = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3,
    "april": 4, "mai": 5, "juni": 6, "juli": 7,
    "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
    # abbreviated
    "jan": 1, "feb": 2, "mär": 3, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "okt": 10,
    "nov": 11, "dez": 12,
}

_ENGLISH_MONTHS: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    # abbreviated
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
    "nov": 11, "dec": 12,
}

# Merged lookup (lowercase key -> month number).  German wins on overlap but
# values are identical for shared abbreviations (Jan, Feb, etc.).
_ALL_MONTHS: dict[str, int] = {**_ENGLISH_MONTHS, **_GERMAN_MONTHS}

# Build a regex alternation of all month names, longest first so the engine
# prefers full names over abbreviations.
_MONTH_NAMES_RE = "|".join(
    sorted(_ALL_MONTHS.keys(), key=len, reverse=True)
)

# Quarter mapping: Q1..Q4 -> (month, day)
_QUARTER_START: dict[int, str] = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expand_year(yy: int) -> int:
    """Expand a 2-digit year: 0-69 -> 20xx, 70-99 -> 19xx."""
    if yy >= 100:
        return yy
    return 2000 + yy if yy < 70 else 1900 + yy


def _month_from_name(name: str) -> Optional[int]:
    """Return month number for a German or English month name (case-insensitive)."""
    return _ALL_MONTHS.get(name.lower().rstrip("."))


def _valid_date(year: int, month: int, day: int) -> bool:
    """Return True if the (year, month, day) triple is a valid calendar date."""
    try:
        date(year, month, day)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Extraction patterns — order matters: more specific first
# ---------------------------------------------------------------------------

# Each pattern is a tuple (compiled regex, handler_name).
# Handlers are methods on a small namespace below.

# DD.MM.YYYY HH:MM  (datetime variant, must come before DD.MM.YYYY)
_PAT_DOT_DATETIME = re.compile(
    r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})\b"
)

# DD.MM.YYYY
_PAT_DOT_DATE_4Y = re.compile(
    r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b"
)

# DD.MM.YY  (2-digit year, must NOT match DD.MM.YYYY consumed above)
_PAT_DOT_DATE_2Y = re.compile(
    r"\b(\d{1,2})\.(\d{1,2})\.(\d{2})\b"
)

# YYYY-MM-DDThh:mm  (ISO datetime, before ISO date)
_PAT_ISO_DATETIME = re.compile(
    r"\b(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})\b"
)

# YYYY-MM-DD
_PAT_ISO_DATE = re.compile(
    r"\b(\d{4})-(\d{2})-(\d{2})\b"
)

# DD/MM/YYYY  (European default)
_PAT_SLASH_DATE = re.compile(
    r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"
)

# DD. Monat YYYY or DD. Monat YY  (German: "15. Juni 2025")
_PAT_DE_DD_MONTH = re.compile(
    r"\b(\d{1,2})\.\s*(" + _MONTH_NAMES_RE + r")\s+(\d{2,4})\b",
    re.IGNORECASE,
)

# Month DD, YYYY  (English: "June 15, 2025")
_PAT_EN_MONTH_DD = re.compile(
    r"\b(" + _MONTH_NAMES_RE + r")\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)

# Monat YYYY / Month YYYY  (month + year only: "Juni 2025", "June 2025")
_PAT_MONTH_YEAR = re.compile(
    r"\b(" + _MONTH_NAMES_RE + r")\s+(\d{4})\b",
    re.IGNORECASE,
)

# QN YYYY
_PAT_QUARTER = re.compile(
    r"\bQ([1-4])\s+(\d{4})\b", re.IGNORECASE
)

# KW NN YYYY  (Kalenderwoche with year)
_PAT_KW_YEAR = re.compile(
    r"\bKW\s+(\d{1,2})\s+(\d{4})\b", re.IGNORECASE
)

# KW NN  (Kalenderwoche without year — extracted but not normalizable)
_PAT_KW_NO_YEAR = re.compile(
    r"\bKW\s+(\d{1,2})\b", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# normalize_date
# ---------------------------------------------------------------------------


def normalize_date(raw: str) -> Optional[str]:
    """Convert a raw date string to ISO-8601 (YYYY-MM-DD or YYYY-MM-DDThh:mm).

    Returns ``None`` if the string cannot be parsed or is ambiguous (e.g. KW
    without a year, DD.MM. without a year).
    """
    if not raw or not raw.strip():
        return None

    s = raw.strip()

    # DD.MM.YYYY HH:MM
    m = _PAT_DOT_DATETIME.fullmatch(s)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hour, minute = int(m.group(4)), int(m.group(5))
        if _valid_date(year, month, day) and 0 <= hour < 24 and 0 <= minute < 60:
            return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}"
        return None

    # YYYY-MM-DDThh:mm
    m = _PAT_ISO_DATETIME.fullmatch(s)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hour, minute = int(m.group(4)), int(m.group(5))
        if _valid_date(year, month, day) and 0 <= hour < 24 and 0 <= minute < 60:
            return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}"
        return None

    # DD.MM.YYYY
    m = _PAT_DOT_DATE_4Y.fullmatch(s)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_date(year, month, day):
            return f"{year:04d}-{month:02d}-{day:02d}"
        return None

    # DD.MM.YY
    m = _PAT_DOT_DATE_2Y.fullmatch(s)
    if m:
        day, month, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = _expand_year(yy)
        if _valid_date(year, month, day):
            return f"{year:04d}-{month:02d}-{day:02d}"
        return None

    # YYYY-MM-DD
    m = _PAT_ISO_DATE.fullmatch(s)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_date(year, month, day):
            return f"{year:04d}-{month:02d}-{day:02d}"
        return None

    # DD/MM/YYYY  (European default for ambiguous slash dates)
    m = _PAT_SLASH_DATE.fullmatch(s)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_date(year, month, day):
            return f"{year:04d}-{month:02d}-{day:02d}"
        return None

    # DD. Monat YYYY/YY  (German)
    m = _PAT_DE_DD_MONTH.fullmatch(s)
    if m:
        day = int(m.group(1))
        month = _month_from_name(m.group(2))
        yy = int(m.group(3))
        year = _expand_year(yy)
        if month and _valid_date(year, month, day):
            return f"{year:04d}-{month:02d}-{day:02d}"
        return None

    # Month DD, YYYY  (English)
    m = _PAT_EN_MONTH_DD.fullmatch(s)
    if m:
        month = _month_from_name(m.group(1))
        day = int(m.group(2))
        year = int(m.group(3))
        if month and _valid_date(year, month, day):
            return f"{year:04d}-{month:02d}-{day:02d}"
        return None

    # Monat YYYY / Month YYYY
    m = _PAT_MONTH_YEAR.fullmatch(s)
    if m:
        month = _month_from_name(m.group(1))
        year = int(m.group(2))
        if month and _valid_date(year, month, 1):
            return f"{year:04d}-{month:02d}-01"
        return None

    # QN YYYY
    m = _PAT_QUARTER.fullmatch(s)
    if m:
        q = int(m.group(1))
        year = int(m.group(2))
        return f"{year:04d}-{_QUARTER_START[q]}"

    # KW NN YYYY
    m = _PAT_KW_YEAR.fullmatch(s)
    if m:
        week, year = int(m.group(1)), int(m.group(2))
        try:
            d = date.fromisocalendar(year, week, 1)  # Monday
            return d.isoformat()
        except ValueError:
            return None

    # KW NN (no year) — ambiguous
    m = _PAT_KW_NO_YEAR.fullmatch(s)
    if m:
        return None

    return None


# ---------------------------------------------------------------------------
# extract_dates
# ---------------------------------------------------------------------------

# Ordered list of (pattern, group_count) for scanning running text.
# More specific patterns first to avoid partial matches.
_EXTRACTION_PATTERNS: list[re.Pattern] = [
    # datetime variants first
    _PAT_DOT_DATETIME,
    _PAT_ISO_DATETIME,
    # full date patterns
    _PAT_DOT_DATE_4Y,
    _PAT_DOT_DATE_2Y,
    _PAT_ISO_DATE,
    _PAT_SLASH_DATE,
    # named-month patterns
    _PAT_DE_DD_MONTH,
    _PAT_EN_MONTH_DD,
    _PAT_MONTH_YEAR,
    # special patterns
    _PAT_QUARTER,
    _PAT_KW_YEAR,
    _PAT_KW_NO_YEAR,
]


def extract_dates(text: str) -> List[str]:
    """Extract raw date strings from *text*.

    Returns a list of raw date substrings in the order they appear.  The same
    span is never returned twice.  Each raw string can be passed through
    :func:`normalize_date` independently.
    """
    if not text:
        return []

    # Collect (start, end, matched_text) tuples from all patterns, then
    # deduplicate overlapping spans keeping the longest / earliest match.
    candidates: list[tuple[int, int, str]] = []

    for pat in _EXTRACTION_PATTERNS:
        for m in pat.finditer(text):
            candidates.append((m.start(), m.end(), m.group(0)))

    if not candidates:
        return []

    # Sort by start position, then by descending length (prefer longer match).
    candidates.sort(key=lambda c: (c[0], -(c[1] - c[0])))

    # Greedily remove overlaps: keep the first (longest) match at each position.
    result: list[str] = []
    last_end = -1
    for start, end, matched in candidates:
        if start >= last_end:
            result.append(matched)
            last_end = end

    return result


# ---------------------------------------------------------------------------
# extract_and_normalize
# ---------------------------------------------------------------------------


def extract_and_normalize(text: str) -> List[str]:
    """Extract dates from *text*, normalize to ISO-8601, return sorted unique list.

    Unparseable / ambiguous raw dates are silently dropped.
    """
    raw_dates = extract_dates(text)
    normalized: set[str] = set()
    for raw in raw_dates:
        iso = normalize_date(raw)
        if iso is not None:
            normalized.add(iso)
    return sorted(normalized)


# ---------------------------------------------------------------------------
# date_range
# ---------------------------------------------------------------------------


def date_range(dates: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(min, max)`` from a list of ISO-8601 date strings.

    Dates may include timestamps (``YYYY-MM-DDThh:mm``); comparison is purely
    lexicographic which works correctly for ISO-8601.  Returns ``(None, None)``
    for an empty list.
    """
    if not dates:
        return (None, None)
    return (min(dates), max(dates))
