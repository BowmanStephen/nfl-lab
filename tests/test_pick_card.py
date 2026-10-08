import json
from datetime import datetime, timedelta, timezone

import pytest

from nfl_lab.config import LIVE_DIR, PUBLIC_API
from nfl_lab.odds_espn import MissingLineError
from nfl_lab.picks import (
    apply_pre_kickoff,
    apply_unclear_starter_nopick,
    build_games,
    format_lock_label,
    grade_game,
    grade_spread,
    health_summary,
    merge_card,
    spread_clv,
    total_clv,
    total_is_active,
)
from nfl_lab.publish import model_game_from_card

VOID_REASON = (
    "Voided Thu Oct 8 by Stephen's decision: the totals formula had the defense sign flipped, "
    "biasing these toward overs."
)
VOID_NOTE = (
    "The 8 week-5 totals picks were voided Oct 8: the totals formula had the defense sign flipped, "
    "which biased them toward overs. The spread picks stand."
)
# game_id -> (total_pick, line total). These eight are the only voided markets.
VOIDED_TOTALS = {
    "2026_05_PHI_JAX": ("over", 42.5),
    "2026_05_CIN_MIA": ("over", 42.5),
    "2026_05_CLE_NYJ": ("over", 39.5),
    "2026_05_HOU_TEN": ("over", 39.5),
    "2026_05_MIN_NO": ("over", 41.5),
    "2026_05_DEN_LAC": ("over", 42.5),
    "2026_05_DET_ARI": ("under", 54.5),
    "2026_05_BUF_LA": ("under", 54.5),
}
# game_id -> (spread_pick, pick-time home margin, spread_qualifies)
LOCKED_SPREADS = {
    "2026_05_TB_DAL": ("TB", 8.5, True),
    "2026_05_PHI_JAX": ("PHI", 6.5, False),
    "2026_05_CHI_GB": ("GB", -3.0, False),
    "2026_05_CIN_MIA": ("MIA", -7.0, True),
    "2026_05_CLE_NYJ": ("CLE", 2.5, True),
    "2026_05_HOU_TEN": ("TEN", -7.0, True),
    "2026_05_IND_PIT": ("IND", 2.5, True),
    "2026_05_LV_NE": ("LV", 3.5, False),
    "2026_05_MIN_NO": ("MIN", -1.5, False),
    "2026_05_NYG_WAS": ("WAS", 3.0, False),
    "2026_05_DEN_LAC": ("LAC", -3.5, False),
    "2026_05_DET_ARI": ("ARI", -4.5, True),
    "2026_05_SF_SEA": ("SF", 2.5, True),
    "2026_05_BAL_ATL": ("ATL", -2.5, False),
    "2026_05_BUF_LA": ("LA", 2.5, False),
}


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


def test_voided_total_is_not_scored_and_the_spread_still_is():
    game = build_games(
        [_proj("g1", "TB", "DAL", 4, 50)],
        [_line("TB", "DAL", 10, 47)],
        "2026-10-05T12:00:00+00:00",
        2.0,
        3.0,
    )[0]
    sel = game["selection"]
    assert sel["spread_qualifies"] is True
    assert sel["total_qualifies"] is True
    assert sel["total_pick"] == "over"
    sel["total_voided"] = True
    sel["total_void_reason"] = VOID_REASON
    pre = dict(game["pick_time"])
    pre["total"] = 50
    game["pre_kickoff"] = pre
    grading = grade_game(game, 24, 10)
    assert grading["spread_outcome"] == "loss"
    assert grading["spread_clv"] == 0
    assert grading["total_outcome"] is None
    assert grading["total_clv"] is None
    assert grading["total_moved_toward"] is None
    assert sel["total_qualifies"] is True
    assert sel["total_pick"] == "over"
    game["grading"] = grading
    health = health_summary([game])
    assert health["wins"] == 0
    assert health["losses"] == 1
    assert health["pushes"] == 0
    assert health["settled_picks"] == 1
    assert health["clv_samples"] == 1
    assert total_is_active(sel) is False


def test_merge_keeps_a_voided_total():
    first = build_games(
        [_proj("g1", "TB", "DAL", 4, 50)],
        [_line("TB", "DAL", 10, 47)],
        "2026-10-05T12:00:00+00:00",
        2.0,
        3.0,
    )
    first[0]["selection"]["total_voided"] = True
    first[0]["selection"]["total_void_reason"] = VOID_REASON
    later = build_games(
        [_proj("g1", "TB", "DAL", 99, 10)],
        [_line("TB", "DAL", 1, 60)],
        "2026-10-08T12:00:00+00:00",
        2.0,
        3.0,
    )
    merged = merge_card({"season": 2026, "week": 5, "games": first}, later)
    sel = merged["games"][0]["selection"]
    assert sel["total_voided"] is True
    assert sel["total_void_reason"] == VOID_REASON
    assert sel["total_pick"] == "over"
    assert sel["total_qualifies"] is True
    assert sel["spread_pick"] == "TB"
    assert merged["games"][0]["pick_time"]["total"] == 47


def test_voided_total_drops_off_the_model_chart():
    both = build_games(
        [_proj("g1", "PHI", "JAX", 1, 46)],
        [_line("PHI", "JAX", 6.5, 42.5)],
        "2026-10-05T12:00:00+00:00",
        2.0,
        3.0,
    )[0]
    both["selection"]["total_voided"] = True
    row = model_game_from_card(both)
    assert row["spread_pick"] is not None
    assert row["total_pick"] is None
    assert row["is_pick"] is True
    assert row["market_total"] == 42.5

    only = build_games(
        [_proj("g2", "MIN", "NO", 6.0, 46)],
        [_line("MIN", "NO", 6.5, 42.5)],
        "2026-10-05T12:00:00+00:00",
        2.0,
        3.0,
    )[0]
    assert only["selection"]["spread_qualifies"] is False
    assert only["selection"]["total_qualifies"] is True
    only["selection"]["total_voided"] = True
    quiet = model_game_from_card(only)
    assert quiet["spread_pick"] is None
    assert quiet["total_pick"] is None
    assert quiet["is_pick"] is False


def test_week5_voids_only_the_eight_totals():
    live = json.loads((LIVE_DIR / "2026-week-05.json").read_text())
    published = json.loads((PUBLIC_API / "picks.json").read_text())
    assert published == live
    assert live["season"] == 2026
    assert live["week"] == 5
    assert live["official_lock"] is True
    assert live["created_at"] == "2026-10-05T23:38:47.012782+00:00"
    assert live["rule"] == {"spread_edge_min": 2.0, "total_edge_min": 3.0}
    assert live["totals_void_note"] == VOID_NOTE
    assert [g["game_id"] for g in live["games"]] == list(LOCKED_SPREADS)
    voided = []
    for game in live["games"]:
        sel = game["selection"]
        pick, margin, qualifies = LOCKED_SPREADS[game["game_id"]]
        assert sel["spread_pick"] == pick
        assert sel["spread_qualifies"] is qualifies
        assert game["pick_time"]["home_margin"] == margin
        assert "voided" not in sel
        if game["game_id"] in VOIDED_TOTALS:
            total_pick, total = VOIDED_TOTALS[game["game_id"]]
            assert sel["total_qualifies"] is True
            assert sel["total_pick"] == total_pick
            assert game["pick_time"]["total"] == total
            assert sel["total_voided"] is True
            assert sel["total_void_reason"] == VOID_REASON
            assert total_is_active(sel) is False
            voided.append(game["game_id"])
        else:
            assert sel["total_qualifies"] is False
            assert "total_voided" not in sel
            assert total_is_active(sel) is False
    assert voided == list(VOIDED_TOTALS)
    summary = json.loads((PUBLIC_API / "summary.json").read_text())
    assert summary["n_spread_picks"] == 7
    assert summary["n_total_picks"] == 0
    model = json.loads((PUBLIC_API / "model.json").read_text())
    by_game = {row["game"]: row for row in model["games"]}
    for game in live["games"]:
        row = by_game[f"{game['away_team']}@{game['home_team']}"]
        if game["game_id"] in VOIDED_TOTALS:
            assert row["total_pick"] is None
        assert row["is_pick"] is game["selection"]["spread_qualifies"]
