import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from nfl_lab.config import LIVE_DIR, PUBLIC_API
from nfl_lab.odds_espn import MissingLineError
from nfl_lab.picks import (
    annotate_close_fallback,
    apply_pre_kickoff,
    closes_from_schedule,
    apply_unclear_starter_nopick,
    build_games,
    format_lock_label,
    grade_game,
    grade_spread,
    health_summary,
    label_line_sources,
    merge_card,
    nflverse_close_block,
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
    "We voided the 8 week 5 over/under picks on Oct 8. "
    "The totals formula had the defense sign flipped, which pushed them toward overs. "
    "The spread picks stand."
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
        "Week 5 picks, locked Mon Oct 5 6:42 PM CT, using the DraftKings lines at that moment"
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


def test_closes_from_schedule_keeps_the_home_margin_sign():
    slate = pd.DataFrame([{
        "game_id": "2026_05_PHI_JAX",
        "away_team": "PHI",
        "home_team": "JAX",
        "spread_line": 7.5,
        "total_line": 41.5,
    }])
    closes = closes_from_schedule(slate)
    assert closes["2026_05_PHI_JAX"]["home_margin"] == 7.5
    assert closes[("PHI", "JAX")]["total"] == 41.5


def test_kickoff_passed_stores_nflverse_and_does_not_call_it_clv():
    games = build_games(
        [_proj("g1", "TB", "DAL", 4, 50)],
        [_line("TB", "DAL", 10, 47)],
        "2026-10-05T12:00:00+00:00",
        2.0,
        3.0,
    )
    kick = datetime.fromisoformat(games[0]["kickoff_utc"])
    later = kick + timedelta(hours=3)
    # A late ESPN number must not be written into the missed pre-kickoff slot.
    late_espn = _line("TB", "DAL", 1, 40)
    apply_pre_kickoff(
        games,
        [late_espn],
        later.isoformat(),
        later,
        {"g1": {"home_margin": 7.5, "total": 44.0}},
    )
    pre = games[0]["pre_kickoff"]
    assert pre["source"] == "nflverse_close"
    assert pre["provider"] == "nflverse"
    assert pre["same_book"] is False
    assert pre["fallback"] is True
    assert pre["home_margin"] == 7.5
    assert pre["total"] == 44.0
    assert "different book" in pre["fallback_reason"]
    assert games[0]["pick_time"]["home_margin"] == 10
    grading = grade_game(games[0], 20, 17)
    assert grading["spread_outcome"] == "win"
    assert grading["spread_clv"] is None
    assert grading["spread_moved_toward"] is None
    assert grading["total_clv"] is None
    games[0]["grading"] = grading
    card = annotate_close_fallback({"games": games, "same_book_clv": "old"})
    assert "TB-DAL" in card["close_fallback_note"]
    assert "different sportsbook" in card["close_fallback_note"]
    assert "same-book line move" in card["close_fallback_note"]
    assert games[0]["selection"]["spread_pick"] == "TB"
    health = health_summary(games)
    assert health["clv_samples"] == 0
    assert health["wins"] == 1
    assert health["losses"] == 1


def test_nflverse_close_is_refused_before_kickoff():
    games = build_games(
        [_proj("g1", "CHI", "GB", 4, 50)],
        [_line("CHI", "GB", -3, 44)],
        "2026-10-05T12:00:00+00:00",
        2.0,
        3.0,
    )
    kick = datetime.fromisoformat(games[0]["kickoff_utc"])
    now = kick - timedelta(minutes=30)
    missing = _line("CHI", "GB", -3, 44)
    missing["missing"] = True
    missing["home_margin"] = None
    missing["total"] = None
    with pytest.raises(MissingLineError, match="ESPN DraftKings line is missing"):
        apply_pre_kickoff(
            games,
            [missing],
            now.isoformat(),
            now,
            {"g1": {"home_margin": 7.5, "total": 44.0}},
        )
    assert games[0]["pre_kickoff"] is None


def test_one_miss_does_not_drop_a_captured_sibling():
    games = build_games(
        [_proj("g1", "PHI", "JAX", 1, 40), _proj("g2", "CHI", "GB", 4, 50)],
        [_line("PHI", "JAX", 6.5, 42.5), _line("CHI", "GB", -3, 44)],
        "2026-10-05T12:00:00+00:00",
        2.0,
        3.0,
    )
    games[0]["kickoff_utc"] = "2026-10-11T13:30:00+00:00"
    games[1]["kickoff_utc"] = "2026-10-11T17:00:00+00:00"
    now = datetime(2026, 10, 11, 16, 15, tzinfo=timezone.utc)
    updated = _line("CHI", "GB", -2, 45)
    with pytest.raises(MissingLineError, match="PHI @ JAX"):
        apply_pre_kickoff(games, [updated], now.isoformat(), now, {})
    assert games[0]["pre_kickoff"] is None
    assert games[1]["pre_kickoff"]["source"] == "espn_scoreboard"
    assert games[1]["pre_kickoff"]["home_margin"] == -2
    assert games[1]["pre_kickoff"]["same_book"] is True
    assert games[1]["pick_time"]["home_margin"] == -3


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
    # The 13 Sunday games missed the ESPN snapshot. Their close is nflverse,
    # and that pair is not same-book CLV. TB-DAL stayed DraftKings. BUF-LA has
    # not kicked off, so it must not be filled from nflverse.
    fallback = {
        "2026_05_PHI_JAX": (7.5, 41.5),
        "2026_05_CHI_GB": (-1.5, 46.5),
        "2026_05_CIN_MIA": (-7.0, 44.5),
        "2026_05_CLE_NYJ": (2.5, 38.5),
        "2026_05_HOU_TEN": (-6.5, 37.5),
        "2026_05_IND_PIT": (3.0, 41.5),
        "2026_05_LV_NE": (3.5, 45.5),
        "2026_05_MIN_NO": (-2.5, 41.5),
        "2026_05_NYG_WAS": (3.5, 41.5),
        "2026_05_DEN_LAC": (-3.5, 42.5),
        "2026_05_DET_ARI": (-5.5, 55.5),
        "2026_05_SF_SEA": (3.0, 46.5),
        "2026_05_BAL_ATL": (3.5, 44.5),
    }
    assert live["close_fallback_note"]
    assert "different sportsbook" in live["close_fallback_note"]
    assert "same-book line move" in live["close_fallback_note"]
    assert "nflverse_close" in live["same_book_clv"]
    for game in live["games"]:
        pre = game.get("pre_kickoff")
        grading = game.get("grading") or {}
        assert grading.get("total_outcome") is None
        assert grading.get("total_clv") is None
        assert game["pick_time"]["line_source"] == "espn_draftkings"
        if game["game_id"] in fallback:
            margin, total = fallback[game["game_id"]]
            assert pre["source"] == "nflverse_close"
            assert pre["line_source"] == "nflverse_close"
            assert game["line_source"] == "nflverse_close"
            assert pre["provider"] == "nflverse"
            assert pre["same_book"] is False
            assert pre["fallback"] is True
            assert "different book" in pre["fallback_reason"]
            assert pre["home_margin"] == margin
            assert pre["total"] == total
            assert grading.get("spread_clv") is None
            if game["selection"]["spread_qualifies"]:
                assert grading.get("spread_outcome") in {"win", "loss", "push"}
        elif game["game_id"] == "2026_05_TB_DAL":
            assert pre["source"] == "espn_scoreboard"
            assert pre["line_source"] == "espn_draftkings"
            assert game["line_source"] == "espn_draftkings"
            assert pre["provider"] == "DraftKings"
            assert pre["home_margin"] == 9.5
            assert grading["spread_clv"] == -1.0
        else:
            assert game["game_id"] == "2026_05_BUF_LA"
            assert game.get("line_source") is None
            assert pre is None or pre.get("source") in {"espn_scoreboard", "espn_summary"}
    assert live["health"]["clv_samples"] == 1
    assert live["health"]["average_clv"] == -1.0
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


def test_nflverse_sign_matches_tb_at_dal_draftkings_lock():
    """TB @ DAL locked at DAL -8.5 on ESPN DraftKings (home_margin +8.5).

    nflverse spread_line is positive when the home team is favored, the same
    sign as home_margin, so +8.5 must stay +8.5 (DAL -8.5), never flip to TB.
    nflverse's actual close for 2026_05_TB_DAL is 9.5 / 49.5, still DAL favored.
    """
    card = json.loads((LIVE_DIR / "2026-week-05.json").read_text())
    game = next(g for g in card["games"] if g["game_id"] == "2026_05_TB_DAL")
    assert game["pick_time"]["home_margin"] == 8.5
    assert game["pick_time"]["spread_display"] == "DAL -8.5"
    assert game["pre_kickoff"]["home_margin"] == 9.5
    assert game["pre_kickoff"]["spread_display"] == "DAL -9.5"

    slate = pd.DataFrame([
        {"game_id": "2026_05_TB_DAL", "away_team": "TB", "home_team": "DAL",
         "spread_line": 8.5, "total_line": 49.5},
    ])
    close = closes_from_schedule(slate)["2026_05_TB_DAL"]
    assert close["home_margin"] == game["pick_time"]["home_margin"]

    actual = closes_from_schedule(slate.assign(spread_line=9.5))["2026_05_TB_DAL"]
    block = nflverse_close_block("2026-10-09T05:00:00+00:00", game, actual)
    assert block["home_margin"] == 9.5 > 0
    assert block["line_source"] == "nflverse_close"
    assert block["source"] == "nflverse_close"

    label_line_sources(card)
    for row in card["games"]:
        assert row["pick_time"]["line_source"] == "espn_draftkings"
        pre = row.get("pre_kickoff")
        expected_source = (
            "nflverse_close" if pre and pre.get("source") == "nflverse_close"
            else "espn_draftkings" if pre
            else None
        )
        assert row["line_source"] == expected_source
