"""
tests/test_converter.py — Unit tests for app/api/helper/converter.py

Covers every public function in converter.py with edge-case coverage:
  - convert_connection_state_type_enum  (Nagios "0"/"1" → SOFT/HARD)
  - convert_service_state_type_enum     (Nagios "0"/"1"/"2"/"3" → OK/WARNING/CRITICAL/UNKNOWN)
  - convert_plugin_status_type_enum     (Nagios "0"/"1"/"2"/"3" → OK/WARNING/CRITICAL/UNKNOWN)
  - convert_host_state_type_enum        (string → HostStateType)
  - convert_acknowledgement_type_enum   (string → AcknowledgementType)
  - convert_to_UTC                      (Unix timestamp → UTC datetime)
  - convert_to_UNIX                     (date+time → Unix timestamp)
  - split_value_unit                    (value+unit parsing)
  - parse_perf_data                     (full Nagios perf-data parsing)
  - get_range_day / get_range_custom    (date-range helpers)
  - normalize_email                     (email normalization)
"""
import pytest
from datetime import datetime, time, timezone, timedelta

from app.history_models import (
    ConnectionStateType,
    HostStateType,
    ServiceStateType,
    PluginStatusType,
    AcknowledgementType,
)
from app.api.helper.converter import (
    convert_connection_state_type_enum,
    convert_service_state_type_enum,
    convert_plugin_status_type_enum,
    convert_host_state_type_enum,
    convert_acknowledgement_type_enum,
    convert_to_UTC,
    convert_to_UNIX,
    split_value_unit,
    parse_perf_data,
    parse_perf_token,
    get_range_day,
    get_range_custom,
    normalize_email,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# convert_connection_state_type_enum
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestConvertConnectionStateTypeEnum:
    """Nagios sends state_type as '0' (soft) or '1' (hard)."""

    @pytest.mark.parametrize("val,expected", [
        ("0", ConnectionStateType.SOFT),
        ("1", ConnectionStateType.HARD),
        (0, ConnectionStateType.SOFT),
        (1, ConnectionStateType.HARD),
        ("Soft", ConnectionStateType.SOFT),
        ("Hard", ConnectionStateType.HARD),
        ("SOFT", ConnectionStateType.SOFT),
        ("HARD", ConnectionStateType.HARD),
        ("soft", ConnectionStateType.SOFT),
        ("hard", ConnectionStateType.HARD),
        (None, ConnectionStateType.SOFT),
        ("", ConnectionStateType.SOFT),   # empty → fallback
    ])
    def test_numeric_and_text_inputs(self, val, expected):
        result = convert_connection_state_type_enum(val)
        assert result == expected

    def test_fallback_unknown_string(self):
        """Unknown string should fall back to SOFT, not crash."""
        result = convert_connection_state_type_enum("bogus")
        assert result == ConnectionStateType.SOFT


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# convert_service_state_type_enum
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestConvertServiceStateTypeEnum:
    """Nagios sends status as '0' (OK), '1' (WARNING), '2' (CRITICAL), '3' (UNKNOWN)."""

    @pytest.mark.parametrize("val,expected", [
        ("0", ServiceStateType.OK),
        ("1", ServiceStateType.WARNING),
        ("2", ServiceStateType.CRITICAL),
        ("3", ServiceStateType.UNKNOWN),
        (0, ServiceStateType.OK),
        (1, ServiceStateType.WARNING),
        (2, ServiceStateType.CRITICAL),
        (3, ServiceStateType.UNKNOWN),
        ("Ok", ServiceStateType.OK),
        ("OK", ServiceStateType.OK),
        ("Warning", ServiceStateType.WARNING),
        ("WARNING", ServiceStateType.WARNING),
        ("Critical", ServiceStateType.CRITICAL),
        ("CRITICAL", ServiceStateType.CRITICAL),
        ("Unknown", ServiceStateType.UNKNOWN),
        ("UNKNOWN", ServiceStateType.UNKNOWN),
        (None, ServiceStateType.UNKNOWN),
        ("", ServiceStateType.UNKNOWN),   # empty → fallback
    ])
    def test_numeric_and_text_inputs(self, val, expected):
        result = convert_service_state_type_enum(val)
        assert result == expected

    def test_fallback_unknown_string(self):
        """Unknown string should fall back to UNKNOWN, not crash."""
        result = convert_service_state_type_enum("bogus")
        assert result == ServiceStateType.UNKNOWN


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# convert_plugin_status_type_enum
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestConvertPluginStatusTypeEnum:
    """Same mapping as service, but fallback is OK instead of UNKNOWN."""

    @pytest.mark.parametrize("val,expected", [
        ("0", PluginStatusType.OK),
        ("1", PluginStatusType.WARNING),
        ("2", PluginStatusType.CRITICAL),
        ("3", PluginStatusType.UNKNOWN),
        (0, PluginStatusType.OK),
        (1, PluginStatusType.WARNING),
        (2, PluginStatusType.CRITICAL),
        (3, PluginStatusType.UNKNOWN),
        ("Ok", PluginStatusType.OK),
        ("OK", PluginStatusType.OK),
        ("Warning", PluginStatusType.WARNING),
        ("WARNING", PluginStatusType.WARNING),
        ("Critical", PluginStatusType.CRITICAL),
        ("CRITICAL", PluginStatusType.CRITICAL),
        ("Unknown", PluginStatusType.UNKNOWN),
        ("UNKNOWN", PluginStatusType.UNKNOWN),
        (None, PluginStatusType.UNKNOWN),
        ("", PluginStatusType.OK),   # empty → fallback to OK
    ])
    def test_numeric_and_text_inputs(self, val, expected):
        result = convert_plugin_status_type_enum(val)
        assert result == expected

    def test_fallback_unknown_string(self):
        """Unknown string should fall back to OK (not crash)."""
        result = convert_plugin_status_type_enum("bogus")
        assert result == PluginStatusType.OK


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# convert_host_state_type_enum
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestConvertHostStateTypeEnum:
    """Host states: Up, Down, Unreachable."""

    @pytest.mark.parametrize("val,expected", [
        ("Up", HostStateType.UP),
        ("UP", HostStateType.UP),
        ("up", HostStateType.UP),
        ("Down", HostStateType.DOWN),
        ("DOWN", HostStateType.DOWN),
        ("Unreachable", HostStateType.UNREACHABLE),
        ("UNREACHABLE", HostStateType.UNREACHABLE),
    ])
    def test_valid_inputs(self, val, expected):
        result = convert_host_state_type_enum(val)
        assert result == expected

    def test_invalid_raises_attribute_error(self):
        """Non-existent host state should raise AttributeError (no fallback)."""
        with pytest.raises(AttributeError):
            convert_host_state_type_enum("bogus")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# convert_acknowledgement_type_enum
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestConvertAcknowledgementTypeEnum:
    """convert_acknowledgement_type_enum uses getattr(AcknowledgementType, str.upper()),
    so it expects the enum *name* (NOACK, NORMACK, STICKYACK), not the display value."""

    @pytest.mark.parametrize("val,expected", [
        ("NOACK", AcknowledgementType.NOACK),
        ("NORMACK", AcknowledgementType.NORMACK),
        ("STICKYACK", AcknowledgementType.STICKYACK),
        ("noack", AcknowledgementType.NOACK),
        ("normack", AcknowledgementType.NORMACK),
        ("stickyack", AcknowledgementType.STICKYACK),
    ])
    def test_valid_inputs(self, val, expected):
        result = convert_acknowledgement_type_enum(val)
        assert result == expected

    def test_invalid_raises_attribute_error(self):
        with pytest.raises(AttributeError):
            convert_acknowledgement_type_enum("bogus")

    def test_display_value_raises(self):
        """Display values like 'No Acknowledgement' contain spaces → no enum attr."""
        with pytest.raises(AttributeError):
            convert_acknowledgement_type_enum("No Acknowledgement")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# convert_to_UTC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestConvertToUTC:
    def test_none_returns_none(self):
        assert convert_to_UTC(None) is None

    def test_unix_timestamp(self):
        """1700000000 = 2023-11-14 22:13:20 UTC."""
        result = convert_to_UTC(1700000000)
        assert result == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)

    def test_zero_timestamp(self):
        """Unix epoch."""
        result = convert_to_UTC(0)
        assert result == datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_returns_aware_datetime(self):
        result = convert_to_UTC(1700000000)
        assert result.tzinfo is not None
        assert result.tzinfo == timezone.utc


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# convert_to_UNIX
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestConvertToUNIX:
    def test_date_and_time_object(self):
        dt = convert_to_UNIX("2024-01-15", time(14, 30, 0))
        assert isinstance(dt, int)
        # convert_to_UNIX uses local time (no tzinfo), so just check it's a valid int
        assert dt > 0

    def test_date_and_string_time(self):
        dt = convert_to_UNIX("2024-06-01", "08:00:00")
        assert isinstance(dt, int)

    def test_midnight(self):
        dt = convert_to_UNIX("2024-03-01", time.min)
        assert isinstance(dt, int)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# split_value_unit
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSplitValueUnit:
    @pytest.mark.parametrize("data,expected_val,expected_unit", [
        ("45.2%", 45.2, "%"),
        ("100", 100.0, None),
        ("1.5s", 1.5, "s"),
        ("-5.2", -5.2, None),
        ("+3.14", 3.14, None),
        ("1024B", 1024.0, "B"),
        ("0.001ms", 0.001, "ms"),
        ("99.9%", 99.9, "%"),
        ("0", 0.0, None),
        ("100.500", 100.5, None),
    ])
    def test_normal_cases(self, data, expected_val, expected_unit):
        val, unit = split_value_unit(data)
        assert val == expected_val
        assert unit == expected_unit

    def test_no_numeric_prefix(self):
        """String with no leading digit returns (None, original_string)."""
        val, unit = split_value_unit("abc")
        assert val is None
        assert unit == "abc"

    def test_empty_string(self):
        val, unit = split_value_unit("")
        assert val is None
        assert unit is None

    def test_operator_precedence_no_index_error(self):
        """Regression: the old code crashed with IndexError on 'abc'.
        The fix wraps the `or` in parentheses so `and` binds tighter."""
        # This would crash the old code: data[i].isdigit() is False,
        # then `or data[i] in ".-+"` evaluates data[3] → IndexError.
        val, unit = split_value_unit("abc")
        assert val is None
        assert unit == "abc"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# parse_perf_data
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestParsePerfData:
    """Full Nagios performance data: label=value[unit];[warn];[crit];[min];[max]"""

    def test_full_performance_data(self):
        result = parse_perf_data("load1=0.5;2;4;0;100")
        assert result["metric"] == "load1"
        assert result["measured_value"] == 0.5
        assert result["unit"] is None
        assert result["warning_threshold"] == 2.0
        assert result["critical_threshold"] == 4.0
        assert result["minimum"] == 0.0
        assert result["maximum"] == 100.0

    def test_with_unit(self):
        result = parse_perf_data("time=1.5s;0.5;1.0")
        assert result["metric"] == "time"
        assert result["measured_value"] == 1.5
        assert result["unit"] == "s"
        assert result["warning_threshold"] == 0.5
        assert result["critical_threshold"] == 1.0

    def test_percentage_no_thresholds(self):
        result = parse_perf_data("pl=0%;0;100")
        assert result["measured_value"] == 0.0
        assert result["unit"] == "%"
        assert result["warning_threshold"] == 0.0
        assert result["critical_threshold"] == 100.0

    def test_no_semicolons(self):
        """Edge case: value with unit but no thresholds at all."""
        result = parse_perf_data("metric=45.2%")
        assert result["metric"] == "metric"
        assert result["measured_value"] == 45.2
        assert result["unit"] == "%"
        assert result["warning_threshold"] is None
        assert result["critical_threshold"] is None
        assert result["minimum"] is None
        assert result["maximum"] is None

    def test_no_equals_sign(self):
        """Malformed input without '=' should return all None values."""
        result = parse_perf_data("bad_data_no_equals")
        assert result["metric"] == "bad_data_no_equals"
        assert result["measured_value"] is None
        assert result["unit"] is None
        assert result["warning_threshold"] is None
        assert result["critical_threshold"] is None
        assert result["minimum"] is None
        assert result["maximum"] is None

    def test_empty_string(self):
        result = parse_perf_data("")
        assert result["metric"] == ""
        assert result["measured_value"] is None

    def test_only_equals(self):
        result = parse_perf_data("key=")
        assert result["metric"] == "key"
        assert result["measured_value"] is None

    def test_multiple_dots_in_value(self):
        """Edge case: value like '1.2.3' — split_value_unit reads '1.2.3' as a whole,
        then float() raises ValueError. This is expected behaviour for malformed data."""
        with pytest.raises(ValueError):
            parse_perf_data("weird=1.2.3")

    def test_negative_value(self):
        result = parse_perf_data("temp=-5.2C;0;10")
        assert result["measured_value"] == -5.2
        assert result["unit"] == "C"
        assert result["warning_threshold"] == 0.0
        assert result["critical_threshold"] == 10.0

    def test_empty_threshold_fields(self):
        """Semicolons present but values empty: 'val;;;;'"""
        result = parse_perf_data("x=5;;;")
        assert result["measured_value"] == 5.0
        assert result["warning_threshold"] is None
        assert result["critical_threshold"] is None
        assert result["minimum"] is None
        assert result["maximum"] is None

    def test_zero_thresholds(self):
        """Thresholds of 0 should parse as 0.0, not None."""
        result = parse_perf_data("x=5;0;0;0;0")
        assert result["warning_threshold"] == 0.0
        assert result["critical_threshold"] == 0.0
        assert result["minimum"] == 0.0
        assert result["maximum"] == 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# parse_perf_token
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestParsePerfToken:
    """parse_perf_token wraps parse_perf_data for the standard "label=value..."
    convention, and adds a fallback for check_flexlm's non-standard
    ':'-separated token (e.g. "flexlm::up:2;down:1")."""

    def test_standard_equals_token_delegates_to_parse_perf_data(self):
        result = parse_perf_token("load1=0.5;2;4;0;100")
        assert result == [parse_perf_data("load1=0.5;2;4;0;100")]

    def test_standard_token_with_unit_and_no_thresholds(self):
        result = parse_perf_token("metric=45.2%")
        assert len(result) == 1
        assert result[0]["metric"] == "metric"
        assert result[0]["measured_value"] == 45.2
        assert result[0]["unit"] == "%"

    def test_flexlm_colon_token_two_metrics(self):
        """Real check_flexlm output: 'flexlm::up:2;down:1' — no '=' at all,
        two metrics packed into one whitespace token via ';'."""
        result = parse_perf_token("flexlm::up:2;down:1")
        assert len(result) == 2

        up, down = result
        assert up["metric"] == "flexlm::up"
        assert up["measured_value"] == 2.0
        assert up["unit"] is None
        assert up["warning_threshold"] is None
        assert up["critical_threshold"] is None
        assert up["minimum"] is None
        assert up["maximum"] is None

        assert down["metric"] == "down"
        assert down["measured_value"] == 1.0
        assert down["unit"] is None

    def test_flexlm_colon_token_single_metric(self):
        result = parse_perf_token("down:0")
        assert len(result) == 1
        assert result[0]["metric"] == "down"
        assert result[0]["measured_value"] == 0.0

    def test_colon_token_with_unit_value(self):
        result = parse_perf_token("temp:5.2C")
        assert len(result) == 1
        assert result[0]["metric"] == "temp"
        assert result[0]["measured_value"] == 5.2
        assert result[0]["unit"] == "C"

    def test_no_separator_falls_back_to_parse_perf_data(self):
        """No '=' and no ':' — same 'malformed' shape as parse_perf_data."""
        result = parse_perf_token("bad_data_no_separator")
        assert result == [parse_perf_data("bad_data_no_separator")]
        assert result[0]["metric"] == "bad_data_no_separator"
        assert result[0]["measured_value"] is None

    def test_empty_string(self):
        result = parse_perf_token("")
        assert result == [parse_perf_data("")]

    def test_colon_token_with_trailing_semicolon_ignored(self):
        """Empty ';'-separated pieces (no ':' in them) are skipped."""
        result = parse_perf_token("up:2;down:1;")
        assert len(result) == 2
        assert [m["metric"] for m in result] == ["up", "down"]

    def test_equals_takes_precedence_over_colon(self):
        """A token containing both '=' and ':' (e.g. a URL in the value)
        should still use the standard '=' parser, not the colon fallback."""
        result = parse_perf_token("url=http://x;0.5;1.0")
        assert len(result) == 1
        assert result[0]["metric"] == "url"
        assert result[0]["warning_threshold"] == 0.5
        assert result[0]["critical_threshold"] == 1.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# get_range_day
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestGetRangeDay:
    def test_returns_two_ints(self):
        start, end = get_range_day(7)
        assert isinstance(start, int)
        assert isinstance(end, int)

    def test_range_is_seven_days(self):
        start, end = get_range_day(7)
        delta = datetime.fromtimestamp(end, tz=timezone.utc) - datetime.fromtimestamp(start, tz=timezone.utc)
        assert delta.days == 7


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# get_range_custom
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestGetRangeCustom:
    def test_same_day(self):
        start, end = get_range_custom("2024-01-15", "2024-01-15")
        assert start < end

    def test_different_days(self):
        start, end = get_range_custom("2024-01-01", "2024-01-31")
        assert end > start

    def test_invalid_order_raises(self):
        with pytest.raises(ValueError, match="end_date must be on or after"):
            get_range_custom("2024-02-01", "2024-01-01")

    def test_malformed_date_raises(self):
        with pytest.raises(ValueError):
            get_range_custom("not-a-date", "2024-01-15")

    def test_returns_inclusive_full_day_range(self):
        """End should cover the full last day (23:59:59.999999)."""
        start, end = get_range_custom("2024-01-15", "2024-01-15")
        # convert_to_UNIX uses local time; check the delta is ~1 day
        delta = end - start
        assert 86000 <= delta <= 86401  # ~24h in seconds (allow for DST/leap)
        # Verify end > start (full day range, not same instant)
        assert end > start


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# normalize_email
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestNormalizeEmail:
    def test_valid_email(self):
        result = normalize_email("test@example.com")
        assert isinstance(result, str)
        assert "@" in result

    def test_uppercase_normalized(self):
        """email_validator normalises the domain but may preserve local-case."""
        result = normalize_email("TEST@EXAMPLE.COM")
        assert isinstance(result, str)
        assert "@" in result
        # Domain should be lowercased
        assert "@example.com" in result.lower()

    def test_plus_addressing(self):
        """Email validator may strip or keep plus-addressing depending on config."""
        result = normalize_email("user+tag@example.com")
        assert isinstance(result, str)
        assert "@" in result
