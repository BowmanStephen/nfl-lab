import pandas as pd

from nfl_lab.qb_adjust import resolve_starter, upcoming_starters


def _chart():
    rows = [
        ("TB", "Baker Mayfield", "00-MAYf", 1),
        ("TB", "Jalon Daniels", "00-DAN", 2),
        ("CHI", "Caleb Williams", "00-WIL", 1),
        ("CHI", "Tyson Bagent", "00-BAG", 2),
        ("CHI", "Case Keenum", "00-KEE", 3),
        ("SEA", "Sam Darnold", "00-DAR", 1),
        ("SEA", "Drew Lock", "00-LOC", 2),
        ("WAS", "Jayden Daniels", "00-JAY", 1),
        ("WAS", "Marcus Mariota", "00-MAR", 2),
    ]
    frame = pd.DataFrame(rows, columns=["team", "player_name", "gsis_id", "pos_rank"])
    frame["pos_abb"] = "QB"
    frame["pos_slot"] = 9
    frame["dt"] = "2026-10-04T13:09:16Z"
    return frame


def _injuries():
    return pd.DataFrame([
        {"week": 4, "gsis_id": "00-MAYf", "report_status": "Out", "report_primary_injury": "Thumb"},
        {"week": 4, "gsis_id": "00-WIL", "report_status": "Out", "report_primary_injury": "Hamstring"},
        {"week": 4, "gsis_id": "00-JAY", "report_status": "Out", "report_primary_injury": "Elbow"},
    ])


def test_depth_plus_injury_prefers_the_first_available_qb_and_flags_the_schedule():
    chart = _chart()
    inj = _injuries()
    tb = resolve_starter("TB", "00-DAN", "Jalon Daniels", chart, inj, 4)
    assert tb["name"] == "Jalon Daniels"
    assert tb["differs_from_schedule"] is False
    assert any("Baker Mayfield" in note and "Out" in note for note in tb["notes"])

    chi = resolve_starter("CHI", "00-KEE", "Case Keenum", chart, inj, 4)
    assert chi["name"] == "Tyson Bagent"
    assert chi["differs_from_schedule"] is True
    assert any("Caleb Williams" in note for note in chi["notes"])

    sea = resolve_starter("SEA", "00-LOC", "Drew Lock", chart, inj, 4)
    assert sea["name"] == "Sam Darnold"
    assert sea["differs_from_schedule"] is True

    was = resolve_starter("WAS", "00-JAY", "Jayden Daniels", chart, inj, 4)
    assert was["name"] == "Marcus Mariota"
    assert any("Elbow" in note for note in was["notes"])


def test_upcoming_starters_replaces_schedule_ids():
    slate = pd.DataFrame([{
        "game_id": "2026_05_SF_SEA",
        "season": 2026,
        "week": 5,
        "away_team": "SF",
        "home_team": "SEA",
        "away_qb_id": "00-PUR",
        "away_qb_name": "Brock Purdy",
        "home_qb_id": "00-LOC",
        "home_qb_name": "Drew Lock",
    }])
    # Away side needs a chart row too.
    chart = _chart()
    extra = pd.DataFrame([{
        "team": "SF", "player_name": "Brock Purdy", "gsis_id": "00-PUR",
        "pos_rank": 1, "pos_abb": "QB", "pos_slot": 9, "dt": "2026-10-04T13:09:16Z",
    }])
    chart = pd.concat([chart, extra], ignore_index=True)
    out = upcoming_starters(slate, 2026, 5, depth=chart, injuries=_injuries())
    assert out.iloc[0]["home_qb_name"] == "Sam Darnold"
    assert out.iloc[0]["home_qb_id"] == "00-DAR"
    assert out.iloc[0]["away_qb_name"] == "Brock Purdy"
    assert any("Drew Lock" in note for note in out.iloc[0]["qb_notes"])
