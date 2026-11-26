"""
Regression tests for calculate_time_distance across daylight-saving clock
changes (GitHub issue #12).

Run with: venv/bin/python -m unittest test_time_distance -v
"""
import unittest
from datetime import datetime, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from mcp_simple_timeserver import core

# Madrid moves its clocks forward on 2026-03-29 (23-hour day) and back on
# 2026-10-25 (25-hour day).
MADRID = ZoneInfo("Europe/Madrid")

NOTICE = "Clock change notice"


def madrid(text: str) -> datetime:
    """
    Build a Madrid-local timezone-aware datetime from an ISO string.

    :param text: ISO 8601 datetime without an offset, e.g. "2026-03-28T12:00:00".
    :return: Datetime carrying the Europe/Madrid timezone.
    """
    return datetime.fromisoformat(text).replace(tzinfo=MADRID)


def distance(from_date: str, to_date: str, unit: str = "auto", tz: str = "Europe/Madrid") -> str:
    """
    Call the shared tool implementation the way both servers do.

    :param from_date: Start date string.
    :param to_date: End date string.
    :param unit: Output unit.
    :param tz: Timezone name (empty string means UTC).
    :return: The tool's result text.
    """
    return core.time_distance_result(from_date=from_date, to_date=to_date, unit=unit, tz=tz)


class RealElapsedTimeTests(unittest.TestCase):
    """The distance is always real elapsed time."""

    def test_issue_12_hours(self) -> None:
        """The exact call from the issue must say 23 hours."""
        result = distance("2026-03-28T12:00:00", "2026-03-29T12:00:00", "hours")
        self.assertIn("Distance: 23.00 hours", result)
        self.assertIn("2026-03-28 11:00:00 UTC", result)
        self.assertIn("2026-03-29 10:00:00 UTC", result)

    def test_days_are_elapsed_time_over_24_hours(self) -> None:
        """23 real hours is 0.96 days; the notice explains the calendar view."""
        result = distance("2026-03-28T12:00:00", "2026-03-29T12:00:00", "days")
        self.assertIn("Distance: 0.96 days", result)

    def test_auto_is_elapsed_time(self) -> None:
        """Auto mode reports the 23 real hours."""
        result = distance("2026-03-28T12:00:00", "2026-03-29T12:00:00")
        self.assertIn("Distance: 23 hours\n", result)

    def test_minutes_and_seconds(self) -> None:
        """The spring change gives 1380 minutes and 82800 seconds."""
        minutes = distance("2026-03-28T12:00:00", "2026-03-29T12:00:00", "minutes")
        seconds = distance("2026-03-28T12:00:00", "2026-03-29T12:00:00", "seconds")
        self.assertIn("Distance: 1380.00 minutes", minutes)
        self.assertIn("Distance: 82800 seconds", seconds)

    def test_fall_back_hours(self) -> None:
        """The October change gives 25 elapsed hours."""
        result = distance("2026-10-24T12:00:00", "2026-10-25T12:00:00", "hours")
        self.assertIn("Distance: 25.00 hours", result)

    def test_past_direction(self) -> None:
        """Reversed arguments give the same magnitude and direction past."""
        result = distance("2026-03-29T12:00:00", "2026-03-28T12:00:00", "hours")
        self.assertIn("Distance: 23.00 hours", result)
        self.assertIn("Direction: past", result)

    def test_now_in_repeated_hour_is_not_reported_as_same_parameters(self) -> None:
        """
        02:30 (first occurrence, 00:30 UTC) to "now" = 01:30 UTC (the second
        occurrence of 02:30) is one real hour, not "same parameters".
        """
        fake_now = datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc)
        with mock.patch.object(core, "get_ntp_datetime", return_value=(fake_now, True)):
            result = distance("2026-10-25T02:30:00", "now", "hours")
        self.assertIn("Distance: 1.00 hours", result)
        self.assertNotIn("same parameters", result)

    def test_existing_behaviour_utc_days_and_same_day_time(self) -> None:
        """Behaviour without a timezone is unchanged."""
        days = distance("2025-01-01", "2025-01-15", "days", tz="")
        same_day = distance("2025-01-01T09:00:00", "2025-01-01T17:30:00", tz="")
        self.assertIn("Distance: 14.00 days", days)
        self.assertIn("Distance: 8 hours, 30 minutes", same_day)

    def test_weeks(self) -> None:
        """23 real hours is 0.14 weeks."""
        result = distance("2026-03-28T12:00:00", "2026-03-29T12:00:00", "weeks")
        self.assertIn("Distance: 0.14 weeks", result)

    def test_date_only_inputs_across_the_spring_change(self) -> None:
        """Local midnights on 29 and 30 March are 23 real hours apart."""
        result = distance("2026-03-29", "2026-03-30", "hours")
        self.assertIn("Distance: 23.00 hours", result)

    def test_half_hour_transition(self) -> None:
        """Lord Howe moves its clocks forward by 30 minutes on 2026-10-04."""
        result = distance(
            "2026-10-03T12:00:00", "2026-10-04T12:00:00", "hours", tz="Australia/Lord_Howe"
        )
        self.assertIn("Distance: 23.50 hours", result)

    def test_same_instant_in_different_representations_is_same_parameters(self) -> None:
        """Noon in Madrid (CEST) and 10:00 UTC are the same moment."""
        result = distance("2026-03-29T12:00:00", "2026-03-29T10:00:00+00:00", "hours")
        self.assertIn("same parameters", result)


class ClockChangeNoticeTests(unittest.TestCase):
    """The notice appears exactly when the endpoint UTC offsets differ."""

    def test_notice_for_spring_change(self) -> None:
        """The issue example carries a notice with both offsets and the calendar day count."""
        result = distance("2026-03-28T12:00:00", "2026-03-29T12:00:00", "hours")
        self.assertIn(NOTICE, result)
        self.assertIn("Europe/Madrid", result)
        self.assertIn("From: +01:00, To: +02:00", result)
        self.assertIn("UTC offset moved forward by 1 hour", result)
        self.assertIn("gives 1 day", result)
        self.assertIn("1 calendar day between the two dates", result)
        self.assertIn("use the clock-time difference or the calendar day count", result)

    def test_notice_for_autumn_change(self) -> None:
        """The October change reports the offsets in the opposite order."""
        result = distance("2026-10-24T12:00:00", "2026-10-25T12:00:00", "hours")
        self.assertIn(NOTICE, result)
        self.assertIn("From: +02:00, To: +01:00", result)
        self.assertIn("UTC offset moved back by 1 hour", result)

    def test_notice_for_past_direction(self) -> None:
        """Reversed arguments still describe the change chronologically (forward)."""
        result = distance("2026-03-29T12:00:00", "2026-03-28T12:00:00", "hours")
        self.assertIn(NOTICE, result)
        self.assertIn("From: +02:00, To: +01:00", result)
        self.assertIn("UTC offset moved forward by 1 hour", result)

    def test_notice_when_clock_readings_are_identical(self) -> None:
        """
        Identical printed clock times with different offsets are not "reversed".

        12:00 in Madrid (UTC+1) and 12:00+05:00 are 4 real hours apart although
        both clocks read 12:00, so the notice must say the readings are identical.
        """
        result = distance("2026-03-28T12:00:00", "2026-03-28T12:00:00+05:00", "hours")
        self.assertIn("Distance: 4.00 hours", result)
        self.assertIn(NOTICE, result)
        self.assertIn("are identical", result)
        self.assertNotIn("opposite order", result)
        self.assertIn("Direction: past", result)
        self.assertNotIn("use the clock-time difference", result)

    def test_notice_for_half_hour_transition(self) -> None:
        """A 30-minute shift is described as 30 minutes."""
        result = distance(
            "2026-10-03T12:00:00", "2026-10-04T12:00:00", "hours", tz="Australia/Lord_Howe"
        )
        self.assertIn("UTC offset moved forward by 30 minutes", result)

    def test_notice_when_clock_runs_backwards_in_repeated_hour(self) -> None:
        """
        02:30 first occurrence (00:30 UTC) to "now" = 01:00 UTC (02:00, second
        occurrence) is 30 real minutes, but the printed clock times run
        backwards. The notice must not claim a clock-time difference.
        """
        fake_now = datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc)
        with mock.patch.object(core, "get_ntp_datetime", return_value=(fake_now, True)):
            result = distance("2026-10-25T02:30:00", "now", "minutes")
        self.assertIn("Distance: 30.00 minutes", result)
        self.assertIn(NOTICE, result)
        self.assertIn("opposite order", result)
        self.assertIn("UTC offset moved back by 1 hour", result)
        self.assertNotIn("Subtracting the local clock times", result)
        self.assertNotIn("use the clock-time difference", result)

    def test_notice_does_not_name_a_zone_for_mixed_inputs(self) -> None:
        """An explicit +02:00 input mixed with a Madrid winter date proves no zone change."""
        result = distance("2026-01-10T12:00:00", "2026-01-11T12:00:00+02:00", "hours")
        self.assertIn("Distance: 23.00 hours", result)
        self.assertIn(NOTICE, result)
        self.assertIn("The UTC offset differs between these two moments", result)
        self.assertNotIn("Europe/Madrid changed", result)

    def test_no_notice_without_change(self) -> None:
        """Ordinary winter dates give 24 hours and no notice."""
        result = distance("2026-01-10T12:00:00", "2026-01-11T12:00:00", "hours")
        self.assertIn("Distance: 24.00 hours", result)
        self.assertNotIn(NOTICE, result)

    def test_no_notice_when_offsets_cancel_out(self) -> None:
        """March to November crosses two changes but has equal offsets at both ends."""
        result = distance("2026-03-01T12:00:00", "2026-11-01T12:00:00", "days")
        self.assertIn("Distance: 245.00 days", result)
        self.assertNotIn(NOTICE, result)

    def test_no_notice_for_fixed_offset_and_utc(self) -> None:
        """A fixed UTC offset and plain UTC never change."""
        fixed = distance("2026-03-28T12:00:00", "2026-03-29T12:00:00", "hours", tz="+05:30")
        plain = distance("2026-03-28T12:00:00", "2026-03-29T12:00:00", "hours", tz="")
        self.assertNotIn(NOTICE, fixed)
        self.assertNotIn(NOTICE, plain)

    def test_business_days_have_no_notice_and_direction_uses_utc_order(self) -> None:
        """
        02:30 first occurrence (00:30 UTC) to "now" = 01:00 UTC, which Madrid
        shows as 02:00 (second occurrence): earlier wall clock, later moment.
        Business-days mode ignores time of day, so there is no notice, and the
        direction must be future.
        """
        fake_now = datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc)
        with mock.patch.object(core, "get_ntp_datetime", return_value=(fake_now, True)):
            result = core.time_distance_result(
                from_date="2026-10-25T02:30:00",
                to_date="now",
                tz="Europe/Madrid",
                business_days=True,
            )
        self.assertIn("Direction: future", result)
        self.assertNotIn(NOTICE, result)

    def test_describe_clock_change_empty_when_offsets_equal(self) -> None:
        """The function returns an empty string when nothing changed."""
        self.assertEqual(
            core.describe_clock_change(
                madrid("2026-01-10T12:00:00"), madrid("2026-01-11T12:00:00")
            ),
            "",
        )

    def test_describe_clock_change_without_zone_name(self) -> None:
        """Fixed-offset datetimes with different offsets get a notice without a zone name."""
        start = datetime.fromisoformat("2026-03-28T12:00:00+01:00")
        end = datetime.fromisoformat("2026-03-29T12:00:00+02:00")
        text = core.describe_clock_change(start, end)
        self.assertTrue(text.startswith("Clock change notice: The UTC offset differs"))
        self.assertIn("From: +01:00, To: +02:00", text)
        self.assertIn("UTC offset moved forward by 1 hour", text)
        self.assertNotIn("changed its", text)


class NonexistentLocalTimeTests(unittest.TestCase):
    """Local times skipped by a spring-forward change are rejected with a message."""

    def test_find_returns_the_mapped_reading_for_a_skipped_time(self) -> None:
        """02:30 on the Madrid spring-forward night maps to 03:30."""
        mapped = core.find_nonexistent_local_time(madrid("2026-03-29T02:30:00"))
        self.assertIsNotNone(mapped)
        self.assertEqual(mapped.replace(tzinfo=None), datetime(2026, 3, 29, 3, 30))

    def test_find_returns_none_for_existing_times(self) -> None:
        """Ordinary times and both occurrences of a repeated hour exist."""
        samples = [
            madrid("2026-03-29T01:59:00"),
            madrid("2026-03-29T03:00:00"),
            madrid("2026-10-25T02:30:00"),
            madrid("2026-01-10T12:00:00"),
            datetime(2026, 10, 25, 2, 30, tzinfo=MADRID, fold=1),
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertIsNone(core.find_nonexistent_local_time(sample))

    def test_find_returns_none_for_fixed_offset(self) -> None:
        """A fixed offset never skips a time."""
        sample = datetime.fromisoformat("2026-03-29T02:30:00+01:00")
        self.assertIsNone(core.find_nonexistent_local_time(sample))

    def test_from_date_in_the_gap_returns_a_message(self) -> None:
        """A skipped from_date yields an explanation and no distance."""
        result = distance("2026-03-29T02:30:00", "2026-03-29T03:30:00", "hours")
        self.assertIn('from_date "2026-03-29 02:30:00" does not exist in Europe/Madrid', result)
        self.assertIn("jump forward by 1 hour", result)
        self.assertIn("for example 2026-03-29 03:30:00", result)
        self.assertNotIn("A date without a time", result)
        self.assertNotIn("Distance", result)

    def test_to_date_in_the_gap_returns_a_message(self) -> None:
        """A skipped to_date yields an explanation and no distance."""
        result = distance("2026-03-28T12:00:00", "2026-03-29T02:30:00", "hours")
        self.assertIn('to_date "2026-03-29 02:30:00" does not exist in Europe/Madrid', result)
        self.assertNotIn("Distance", result)

    def test_half_hour_gap(self) -> None:
        """Lord Howe skips 30 minutes; the message names the half-hour jump."""
        result = distance(
            "2026-10-04T02:15:00", "2026-10-04T12:00:00", "hours", tz="Australia/Lord_Howe"
        )
        self.assertIn("does not exist in Australia/Lord_Howe", result)
        self.assertIn("jump forward by 30 minutes", result)
        self.assertIn("for example 2026-10-04 02:45:00", result)

    def test_date_only_midnight_in_a_midnight_gap(self) -> None:
        """Havana skips midnight on 2026-03-08, so the date-only input does not exist."""
        result = distance("2026-03-08", "2026-03-09", "hours", tz="America/Havana")
        self.assertIn("does not exist in America/Havana", result)
        self.assertIn('from_date "2026-03-08 00:00:00"', result)
        self.assertIn("A date without a time is read as 00:00:00.", result)

    def test_times_next_to_the_gap_still_work(self) -> None:
        """One minute before the gap to the first minute after it is computed normally."""
        result = distance("2026-03-29T01:59:00", "2026-03-29T03:00:00", "minutes")
        self.assertIn("Distance: 1.00 minutes", result)
        self.assertNotIn("does not exist", result)

    def test_repeated_hour_is_still_computed(self) -> None:
        """Times in the repeated autumn hour exist and are computed."""
        result = distance("2026-10-25T02:30:00", "2026-10-25T03:30:00", "hours")
        self.assertIn("Distance: 2.00 hours", result)
        self.assertNotIn("does not exist", result)

    def test_business_days_mode_is_exempt(self) -> None:
        """Business-days mode ignores time of day, so no gap check applies."""
        result = core.time_distance_result(
            from_date="2026-03-29T02:30:00",
            to_date="2026-03-30",
            tz="Europe/Madrid",
            business_days=True,
        )
        self.assertNotIn("does not exist", result)
        self.assertIn("business days", result)

    def test_now_is_exempt(self) -> None:
        """The literal "now" always exists."""
        fake_now = datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc)
        with mock.patch.object(core, "get_ntp_datetime", return_value=(fake_now, True)):
            result = distance("2026-03-28T12:00:00", "now", "hours")
        self.assertNotIn("does not exist", result)
        self.assertIn("Distance:", result)


if __name__ == "__main__":
    unittest.main()
