from datetime import datetime, timedelta, timezone

import pytest

from nfl_lab.odds_espn import MissingLineError
from nfl_lab.picks import (
    apply_pre_kickoff,
    apply_unclear_starter_nopick,
    build_games,
    format_lock_label,
    grade_game,
    grade_spread,
    merge_card,
    spread_clv,
    total_clv,
)


def _proj(game_id, away, home, margin, total):
    return {
        "game_id": game_id,
        "season": 2026,
        "week": 5,
        "gameday": "2026-10-11",
        "gametime": "13:00",
        "away_team": away,
        "home_team": home,
        "proj_margin": margin,
        "proj_margin_qb": margin,
        "proj_total": total,
        "qb_adj_points": 0,
        "away_qb_name": "A",
        "home_qb_name": "H",
        "qb_notes": [],
    }


def _line(away, home, margin, total):
    return {
        "away_team": away,
        "home_team": home,
        "home_margin": margin,
        "total": total,
        "spread_display": f"{home} {-margin}",
        "kickoff_utc": "2026-10-11T17:00:00+00:00",
        "espn_id": "1",
        "missing": False,
    }


def test_missing_line_fails_and_names_the_game():
    games = [
        _proj("g1", "TB", "DAL", 1, 45),
        _proj("g2", "CHI", "GB", 3, 44),
    ]
    lines = [_line("TB", "DAL", 10, 47.5)]
    with pytest.raises(MissingLineError, match="CHI @ GB"):
        build_games(games, lines, "2026-10-05T12:00:00+00:00", 2.0, 3.0)


def test_pick_time_line_is_not_replaced():
    first = build_games(
        [_proj("g1", "TB", "DAL", 4, 50)],
        [_line("TB", "DAL", 10, 47)],
        "2026-10-05T12:00:00+00:00",
        2.0,
        3.0,
    )
    card = {"season": 2026, "week": 5, "games": first}
    later_games = build_games(
        [_proj("g1", "TB", "DAL", 99, 10)],
        [_line("TB", "DAL", 1, 60)],
        "2026-10-08T12:00:00+00:00",
        2.0,
        3.0,
    )
    merged = merge_card(card, later_games)
    assert merged["games"][0]["pick_time"]["home_margin"] == 10
    assert merged["games"][0]["selection"]["model_margin"] == 4
    assert merged["games"][0]["selection"]["spread_pick"] == "TB"


def test_cover_and_same_book_clv_signs():
    assert grade_spread("DAL", "DAL", 7, 3) == "win"
    assert grade_spread("TB", "DAL", 7, 3) == "loss"
    assert grade_spread("DAL", "DAL", 3, 3) == "push"
    # Home margin falls from 10 to 7: the away side got the better number.
    assert spread_clv("TB", "DAL", 10, 7) > 0
    assert spread_clv("DAL", "DAL", 10, 7) < 0
    assert total_clv("over", 44, 47) > 0
    assert total_clv("under", 44, 47) < 0
    assert (spread_clv("DAL", "DAL", 10, 10) > 0) is False


def test_pre_kickoff_after_kick_fails_loud():
    games = build_games(
        [_proj("g1", "TB", "DAL", 4, 50)],
        [_line("TB", "DAL", 10, 47)],
        "2026-10-05T12:00:00+00:00",
        2.0,
        3.0,
    )
    later = datetime(2026, 10, 11, 18, 0, tzinfo=timezone.utc)
    with pytest.raises(MissingLineError, match="kickoff passed"):
        apply_pre_kickoff(games, [], "2026-10-11T18:00:00+00:00", later)


def test_zero_move_is_not_toward_us():
    game = build_games(
        [_proj("g1", "TB", "DAL", 4, 40)],
        [_line("TB", "DAL", 10, 47)],
        "2026-10-05T12:00:00+00:00",
        2.0,
        3.0,
    )[0]
    game["pre_kickoff"] = dict(game["pick_time"])
    grading = grade_game(game, None, None)
    assert grading["spread_moved_toward"] is False
    assert grading["spread_clv"] == 0


def test_lock_label_uses_central_time():
    label = format_lock_label(5, "2026-10-05T23:42:00+00:00")
    assert label == (
        "Official week-5 picks, locked Mon Oct 5 6:42 PM CT, DraftKings lines at lock"
    )


def test_unclear_starter_is_not_scored_when_the_rule_would_fire():
    games = build_games(
        [_proj("2026_05_NYG_WAS", "NYG", "WAS", -4, 44)],
        [_line("NYG", "WAS", 0.5, 43.5)],
        "2026-10-05T23:42:00+00:00",
        2.0,
        3.0,
    )
    noted = apply_unclear_starter_nopick(games, "2026_05_NYG_WAS")
    sel = noted["selection"]
    assert sel["model_margin"] == -4
    assert sel["spread_edge"] == -4.5
    assert sel["locked_rule_would_qualify"] == {"spread": True, "total": False}
    assert sel["spread_qualifies"] is False
    assert sel["total_qualifies"] is False
    assert "Washington's starter is unclear" in sel["no_pick_reason"]
    assert games[0]["pick_time"]["home_margin"] == 0.5


def test_unclear_starter_keeps_the_locked_rule_when_it_already_excludes():
    games = build_games(
        [
            _proj("2026_05_NYG_WAS", "NYG", "WAS", 1, 44),
            _proj("g2", "CHI", "GB", 1, 44),
        ],
        [_line("NYG", "WAS", 0.5, 43.5), _line("CHI", "GB", 1, 44)],
        "2026-10-05T23:42:00+00:00",
        2.0,
        3.0,
    )
    apply_unclear_starter_nopick(games, "2026_05_NYG_WAS")
    was = games[0]["selection"]
    assert was["spread_qualifies"] is False
    assert was["total_qualifies"] is False
    assert "locked rule" in was["no_pick_reason"]
    assert "Washington's starter is unclear" in was["no_pick_reason"]
    assert "locked_rule_would_qualify" not in was
    assert "no_pick_reason" not in games[1]["selection"]
    assert games[1]["selection"]["spread_qualifies"] is False


def test_window_captures_pre_kickoff():
    games = build_games(
        [_proj("g1", "TB", "DAL", 4, 50)],
        [_line("TB", "DAL", 10, 47)],
        "2026-10-05T12:00:00+00:00",
        2.0,
        3.0,
    )
    kick = datetime.fromisoformat(games[0]["kickoff_utc"])
    now = kick - timedelta(minutes=30)
    updated = dict(_line("TB", "DAL", 8, 48))
    apply_pre_kickoff(games, [updated], now.isoformat(), now)
    assert games[0]["pre_kickoff"]["home_margin"] == 8
    assert games[0]["pick_time"]["home_margin"] == 10
