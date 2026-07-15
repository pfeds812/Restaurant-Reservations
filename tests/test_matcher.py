from datetime import date, datetime, time

from resywatch.matcher import find_matches, matches
from resywatch.models import Slot, Watch


def make_slot(hour, minute=0, table_type="Dining Room", party=2, day=date(2026, 7, 17)):
    return Slot(
        venue_id=1,
        venue_name="Test",
        day=day,
        start=datetime(day.year, day.month, day.day, hour, minute),
        table_type=table_type,
        party_size=party,
        config_token="tok",
    )


def base_watch(**kw):
    defaults = dict(
        name="w",
        venue_id=1,
        party_size=2,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 8, 1),
        earliest_time=time(18, 0),
        latest_time=time(21, 0),
    )
    defaults.update(kw)
    return Watch(**defaults)


def test_time_window_filters():
    w = base_watch()
    assert matches(w, make_slot(19)) is True
    assert matches(w, make_slot(17, 30)) is False  # before window
    assert matches(w, make_slot(21, 30)) is False  # after window


def test_party_size_must_match():
    w = base_watch()
    assert matches(w, make_slot(19, party=4)) is False


def test_table_type_filter_case_insensitive():
    w = base_watch(table_types=["patio"])
    assert matches(w, make_slot(19, table_type="Patio")) is True
    assert matches(w, make_slot(19, table_type="Dining Room")) is False


def test_days_of_week_filter():
    # 2026-07-17 is a Friday; 2026-07-19 is a Sunday.
    w = base_watch(days_of_week=["Fri"])
    assert matches(w, make_slot(19, day=date(2026, 7, 17))) is True
    assert matches(w, make_slot(19, day=date(2026, 7, 19))) is False


def test_ranking_prefers_closest_to_preferred_time():
    w = base_watch(preferred_time=time(19, 30))
    slots = [make_slot(18), make_slot(20), make_slot(19, 30), make_slot(19)]
    ranked = find_matches(w, slots)
    assert ranked[0].start.time() == time(19, 30)


def test_ranking_defaults_to_earliest():
    w = base_watch()
    slots = [make_slot(20), make_slot(18, 30), make_slot(19)]
    ranked = find_matches(w, slots)
    assert [s.start.time() for s in ranked] == [time(18, 30), time(19), time(20)]
