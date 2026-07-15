from resywatch.config import _load_watches


def test_party_sizes_expands_to_multiple_watches():
    raw = {
        "name": "Torrisi",
        "venue_id": 123,
        "party_sizes": [2, 4],
        "date_from": "2026-07-15",
        "date_to": "2026-10-15",
        "days_of_week": ["Fri", "Sat"],
        "earliest_time": "17:30",
        "latest_time": "21:00",
    }
    watches = _load_watches(raw)
    assert len(watches) == 2
    assert {w.party_size for w in watches} == {2, 4}
    # names are disambiguated when there are multiple sizes
    assert all("party" in w.name for w in watches)
    assert watches[0].venue_id == 123


def test_single_party_size_keeps_original_name():
    raw = {
        "name": "Solo",
        "venue_id": 9,
        "party_size": 2,
        "date_from": "2026-07-15",
        "date_to": "2026-10-15",
    }
    watches = _load_watches(raw)
    assert len(watches) == 1
    assert watches[0].name == "Solo"


def test_null_venue_id_becomes_none():
    raw = {
        "name": "Placeholder",
        "venue_id": None,
        "party_sizes": [2],
        "date_from": "2026-07-15",
        "date_to": "2026-10-15",
    }
    watches = _load_watches(raw)
    assert watches[0].venue_id is None
