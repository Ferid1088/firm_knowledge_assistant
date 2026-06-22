"""Tests for backend.tools.dates — date extraction and normalization."""
from __future__ import annotations

import pytest

from backend.tools.dates import (
    date_range,
    extract_and_normalize,
    extract_dates,
    normalize_date,
)


# ---------------------------------------------------------------------------
# normalize_date — individual pattern tests
# ---------------------------------------------------------------------------

class TestNormalizeDate:
    """Test normalize_date against every supported pattern."""

    def test_dd_dot_mm_dot_yyyy(self):
        assert normalize_date("15.06.2025") == "2025-06-15"

    def test_dd_dot_mm_dot_yy(self):
        assert normalize_date("15.06.25") == "2025-06-15"

    def test_dd_slash_mm_slash_yyyy(self):
        assert normalize_date("15/06/2025") == "2025-06-15"

    def test_iso_yyyy_mm_dd(self):
        assert normalize_date("2025-06-15") == "2025-06-15"

    def test_german_dd_monat_yyyy(self):
        assert normalize_date("15. Juni 2025") == "2025-06-15"

    def test_german_dd_monat_yy(self):
        assert normalize_date("15. Juni 25") == "2025-06-15"

    def test_german_monat_yyyy(self):
        assert normalize_date("Juni 2025") == "2025-06-01"

    def test_english_month_dd_comma_yyyy(self):
        assert normalize_date("June 15, 2025") == "2025-06-15"

    def test_english_month_yyyy(self):
        assert normalize_date("June 2025") == "2025-06-01"

    def test_quarter_q2(self):
        assert normalize_date("Q2 2025") == "2025-04-01"

    def test_quarter_q1(self):
        assert normalize_date("Q1 2025") == "2025-01-01"

    def test_quarter_q3(self):
        assert normalize_date("Q3 2025") == "2025-07-01"

    def test_quarter_q4(self):
        assert normalize_date("Q4 2025") == "2025-10-01"

    def test_kw_with_year(self):
        # KW 24 2025 -> Monday of ISO week 24, 2025 = 2025-06-09
        assert normalize_date("KW 24 2025") == "2025-06-09"

    def test_kw_without_year_returns_none(self):
        assert normalize_date("KW 24") is None

    def test_dd_dot_mm_dot_yyyy_with_time(self):
        assert normalize_date("15.06.2025 14:30") == "2025-06-15T14:30"

    def test_iso_datetime(self):
        assert normalize_date("2025-06-15T14:30") == "2025-06-15T14:30"

    def test_dd_dot_mm_without_year_returns_none(self):
        assert normalize_date("15.06.") is None

    def test_garbage_returns_none(self):
        assert normalize_date("not a date") is None

    def test_empty_string_returns_none(self):
        assert normalize_date("") is None

    def test_german_abbreviated_month(self):
        assert normalize_date("15. Mär 2025") == "2025-03-15"

    def test_english_abbreviated_month(self):
        assert normalize_date("Mar 15, 2025") == "2025-03-15"

    def test_german_januar(self):
        assert normalize_date("1. Januar 2024") == "2024-01-01"

    def test_german_dezember(self):
        assert normalize_date("31. Dezember 2025") == "2025-12-31"

    def test_english_december(self):
        assert normalize_date("December 31, 2025") == "2025-12-31"

    def test_ambiguous_slash_treated_as_dd_mm(self):
        # 06/15/2025 is ambiguous; we treat as DD/MM which would be invalid
        # (month=15), so it should return None or be handled gracefully
        # Actually: per spec, treat as DD/MM/YYYY — day=6, month=15 is invalid -> None
        result = normalize_date("06/15/2025")
        # Month 15 doesn't exist, so this should be None
        assert result is None

    def test_kw_1_2025(self):
        # ISO week 1 of 2025 -> Monday = 2024-12-30
        assert normalize_date("KW 1 2025") == "2024-12-30"

    def test_german_maerz_with_umlaut(self):
        assert normalize_date("15. März 2025") == "2025-03-15"

    def test_two_digit_year_90s(self):
        # 15.06.99 -> should map to 1999 (>= 70 -> 19xx)
        assert normalize_date("15.06.99") == "1999-06-15"


# ---------------------------------------------------------------------------
# extract_dates — pattern matching in running text
# ---------------------------------------------------------------------------

class TestExtractDates:
    """Test extraction of raw date strings from text."""

    def test_german_sentence(self):
        text = "Der Vertrag läuft bis zum 31.12.2025"
        dates = extract_dates(text)
        assert "31.12.2025" in dates

    def test_english_sentence(self):
        text = "Contract expires on December 31, 2025"
        dates = extract_dates(text)
        assert "December 31, 2025" in dates

    def test_mixed_dates(self):
        text = "Liefertermin: Q2 2025, Review am 15. März 2025"
        dates = extract_dates(text)
        assert "Q2 2025" in dates
        assert "15. März 2025" in dates

    def test_no_dates(self):
        text = "This text has no dates"
        dates = extract_dates(text)
        assert dates == []

    def test_multiple_dates(self):
        text = "Von 01.01.2025 bis 31.12.2025"
        dates = extract_dates(text)
        assert len(dates) == 2

    def test_date_at_start(self):
        text = "15.06.2025 ist der Termin"
        dates = extract_dates(text)
        assert "15.06.2025" in dates

    def test_date_at_end(self):
        text = "Deadline is June 15, 2025"
        dates = extract_dates(text)
        assert "June 15, 2025" in dates

    def test_iso_date_in_text(self):
        text = "Created on 2025-06-15 by admin"
        dates = extract_dates(text)
        assert "2025-06-15" in dates

    def test_kw_in_text(self):
        text = "Fertigstellung in KW 24 2025"
        dates = extract_dates(text)
        assert "KW 24 2025" in dates

    def test_kw_without_year_in_text(self):
        text = "Fertigstellung in KW 24"
        dates = extract_dates(text)
        # KW without year is still extracted as raw, but normalize will return None
        assert "KW 24" in dates

    def test_datetime_in_text(self):
        text = "Meeting am 15.06.2025 14:30 Uhr"
        dates = extract_dates(text)
        assert "15.06.2025 14:30" in dates

    def test_quarter_in_text(self):
        text = "Delivery expected Q3 2025"
        dates = extract_dates(text)
        assert "Q3 2025" in dates

    def test_german_month_year_only(self):
        text = "Veröffentlicht im Juni 2025"
        dates = extract_dates(text)
        assert "Juni 2025" in dates

    def test_dd_dot_mm_dot_yy_in_text(self):
        text = "Datum: 15.06.25"
        dates = extract_dates(text)
        assert "15.06.25" in dates


# ---------------------------------------------------------------------------
# extract_and_normalize — end-to-end
# ---------------------------------------------------------------------------

class TestExtractAndNormalize:
    """Test extraction + normalization pipeline."""

    def test_german_contract(self):
        text = "Der Vertrag läuft bis zum 31.12.2025"
        result = extract_and_normalize(text)
        assert result == ["2025-12-31"]

    def test_english_contract(self):
        text = "Contract expires on December 31, 2025"
        result = extract_and_normalize(text)
        assert result == ["2025-12-31"]

    def test_mixed_text(self):
        text = "Liefertermin: Q2 2025, Review am 15. März 2025"
        result = extract_and_normalize(text)
        assert "2025-03-15" in result
        assert "2025-04-01" in result

    def test_no_dates_empty_list(self):
        text = "This text has no dates"
        result = extract_and_normalize(text)
        assert result == []

    def test_sorted_output(self):
        text = "Von 31.12.2025 bis 01.01.2025"
        result = extract_and_normalize(text)
        assert result == ["2025-01-01", "2025-12-31"]

    def test_deduplication(self):
        text = "Date: 15.06.2025 and again 15.06.2025"
        result = extract_and_normalize(text)
        assert result == ["2025-06-15"]

    def test_kw_without_year_excluded(self):
        text = "In KW 24 passiert viel"
        result = extract_and_normalize(text)
        # KW without year normalizes to None, so excluded
        assert result == []

    def test_multiple_formats_mixed(self):
        text = "Start: 2025-01-15, Ende: 30. Juni 2025, Review Q3 2025"
        result = extract_and_normalize(text)
        assert "2025-01-15" in result
        assert "2025-06-30" in result
        assert "2025-07-01" in result

    def test_datetime_included(self):
        text = "Meeting am 15.06.2025 14:30"
        result = extract_and_normalize(text)
        assert "2025-06-15T14:30" in result


# ---------------------------------------------------------------------------
# date_range
# ---------------------------------------------------------------------------

class TestDateRange:
    """Test min/max date range computation."""

    def test_multiple_dates(self):
        dates = ["2025-06-15", "2025-01-01", "2025-12-31"]
        assert date_range(dates) == ("2025-01-01", "2025-12-31")

    def test_single_date(self):
        dates = ["2025-06-15"]
        assert date_range(dates) == ("2025-06-15", "2025-06-15")

    def test_empty_list(self):
        assert date_range([]) == (None, None)

    def test_with_datetimes(self):
        dates = ["2025-06-15T14:30", "2025-01-01", "2025-12-31"]
        assert date_range(dates) == ("2025-01-01", "2025-12-31")

    def test_same_dates(self):
        dates = ["2025-06-15", "2025-06-15"]
        assert date_range(dates) == ("2025-06-15", "2025-06-15")
