"""New pick cards do not lock over/under picks while totals are paused.

Already-locked cards keep what they wrote: merge_card never rewrites a selection.
"""
import json

from nfl_lab import picks
from nfl_lab.picks import build_games, merge_card, total_is_active


def _proj(game_id, away, home, margin, total):
    return {"game_id": game_id, "season": 2026, "week": 7, "gameday": "2026-10-25",
            "gametime": "13:00", "away_team": away, "home_team": home,
            "proj_margin": margin, "proj_margin_qb": margin, "proj_total": total,
            "qb_adj_points": 0}


def _line(away, home, margin, total):
    return {"away_team": away, "home_team": home, "home_margin": margin, "total": total,
            "spread_display": f"{home} {-margin}", "kickoff_utc": "2026-10-25T17:00:00+00:00",
            "espn_id": "1", "missing": False}


def test_totals_paused_by_default():
    assert picks.TOTALS_PAUSED is True


def test_new_card_does_not_lock_a_total_that_clears_the_rule():
    game = build_games([_proj("g1", "TB", "DAL", 10, 60)], [_line("TB", "DAL", 9, 45)],
                       "2026-10-20T12:00:00+00:00", 2.0, 3.0)[0]
    sel = game["selection"]
    assert sel["total_qualifies"] is False
    assert total_is_active(sel) is False
    assert sel["total_paused"] is True
    assert sel["total_rule_would_qualify"] is True
    assert sel["total_pick"] == "over"  # edge and side are still recorded
    assert sel["spread_qualifies"] is False  # spread rule unchanged (edge 1 < 2)


def test_spreads_still_lock_while_totals_paused():
    game = build_games([_proj("g1", "TB", "DAL", 10, 46)], [_line("TB", "DAL", 3, 45)],
                       "2026-10-20T12:00:00+00:00", 2.0, 3.0)[0]
    assert game["selection"]["spread_qualifies"] is True


def test_already_locked_total_survives_merge():
    locked = build_games([_proj("g1", "TB", "DAL", 4, 50)], [_line("TB", "DAL", 10, 47)],
                         "2026-10-05T12:00:00+00:00", 2.0, 3.0)
    locked[0]["selection"]["total_qualifies"] = True  # as written before the pause
    locked[0]["selection"].pop("total_paused")
    before = json.loads(json.dumps(locked[0]["selection"]))
    later = build_games([_proj("g1", "TB", "DAL", 4, 50)], [_line("TB", "DAL", 10, 47)],
                        "2026-10-06T12:00:00+00:00", 2.0, 3.0)
    merged = merge_card({"season": 2026, "week": 5, "games": locked}, later)
    assert merged["games"][0]["selection"] == before
