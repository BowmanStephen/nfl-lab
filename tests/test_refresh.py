"""Kickoff clock and week handoff. The data load must not outrun the slate."""
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from nfl_lab.odds_espn import MissingLineError
from nfl_lab.refresh import _capture_closes, run

UTC = timezone.utc
KICK = datetime(2026, 10, 13, 0, 15, tzinfo=UTC)


def _schedule_row(week, game_id, away, home, spread, total, kick_score=None):
    home_score, away_score = (None, None) if kick_score is None else kick_score
    return {
        "season": 2026,
        "week": week,
        "game_type": "REG",
        "game_id": game_id,
        "away_team": away,
        "home_team": home,
        "home_score": home_score,
        "away_score": away_score,
        "spread_line": spread,
        "total_line": total,
    }


def _buf_game(pre=None):
    return {
        "game_id": "2026_05_BUF_LA",
        "season": 2026,
        "week": 5,
        "away_team": "BUF",
        "home_team": "LA",
        "kickoff_utc": KICK.isoformat(),
        "pick_time": {
            "home_margin": 2.5,
            "total": 47.5,
            "source": "espn_scoreboard",
            "same_book": True,
        },
        "pre_kickoff": pre,
        "selection": {
            "spread_pick": "LA",
            "spread_qualifies": True,
            "total_pick": "over",
            "total_qualifies": False,
        },
        "grading": None,
    }


def _install_loaders(monkeypatch, schedules, clock):
    monkeypatch.setattr("nfl_lab.refresh._clock", clock)
    monkeypatch.setattr("nfl_lab.refresh.load_schedules", lambda *args, **kwargs: schedules)
    monkeypatch.setattr("nfl_lab.refresh.load_pbp", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr("nfl_lab.refresh.load_depth_charts", lambda *args, **kwargs: None)
    monkeypatch.setattr("nfl_lab.refresh.load_injuries", lambda *args, **kwargs: None)
    # These fixtures have no play-by-play; the stale-data rule is tested in test_safe_to_fail.py.
    monkeypatch.setattr("nfl_lab.refresh.check_source_fresh", lambda *args, **kwargs: None)

    def project(schedules, pbp, depth, injuries, week):
        slate = schedules[schedules["week"] == week].copy()
        rows = []
        for rec in slate.to_dict(orient="records"):
            rows.append({
                "game_id": rec["game_id"],
                "season": 2026,
                "week": int(week),
                "gameday": "2026-10-16",
                "gametime": "20:15",
                "away_team": rec["away_team"],
                "home_team": rec["home_team"],
                "proj_margin": rec["spread_line"],
                "proj_margin_qb": rec["spread_line"],
                "proj_total": rec["total_line"],
                "qb_adj_points": 0.0,
            })
        return None, None, [], pd.DataFrame(rows), slate, int(week) - 1

    monkeypatch.setattr("nfl_lab.refresh._project", project)


def test_kickoff_passing_during_data_load_is_not_a_pre_kickoff_line(monkeypatch):
    """The run starts inside the window. The load finishes after kickoff.

    The ESPN number fetched on the late clock must not become the pre-kickoff
    line. The nflverse close is the fallback, and its sign stays home-favored.
    """
    schedules = pd.DataFrame([
        _schedule_row(5, "2026_05_BUF_LA", "BUF", "LA", 3.0, 48.5),
    ])
    loaded = {"done": False}

    def clock():
        if loaded["done"]:
            return KICK + timedelta(minutes=3)
        return KICK - timedelta(minutes=20)

    def load_schedules(*args, **kwargs):
        loaded["done"] = True
        return schedules

    _install_loaders(monkeypatch, schedules, clock)
    monkeypatch.setattr("nfl_lab.refresh.load_schedules", load_schedules)

    store = {"5": {
        "season": 2026,
        "week": 5,
        "created_at": "2026-10-05T23:38:47+00:00",
        "games": [_buf_game()],
    }}
    fetched = {}

    def load_card(season, week):
        raw = store.get(str(week))
        return json.loads(json.dumps(raw)) if raw else None

    def save_card(card):
        store[str(card["week"])] = json.loads(json.dumps(card))

    def fetch(season, week, now=None):
        fetched["now"] = now
        return [{
            "away_team": "BUF",
            "home_team": "LA",
            "home_margin": 7.0,
            "total": 51.0,
            "spread_display": "LA -7",
            "kickoff_utc": KICK.isoformat(),
            "espn_id": "1",
            "missing": False,
            "source": "espn_scoreboard",
        }]

    monkeypatch.setattr("nfl_lab.refresh.load_card", load_card)
    monkeypatch.setattr("nfl_lab.refresh.save_card", save_card)
    monkeypatch.setattr("nfl_lab.refresh.fetch_week_lines", fetch)
    monkeypatch.setattr(
        "nfl_lab.refresh.write_site",
        lambda *args, **kwargs: {"n_spread_picks": 1, "n_total_picks": 0, "n_games": 1},
    )

    run("refresh")

    pre = store["5"]["games"][0]["pre_kickoff"]
    assert fetched["now"] >= KICK
    assert pre["source"] == "nflverse_close"
    assert pre["line_source"] == "nflverse_close"
    assert pre["home_margin"] == 3.0
    assert pre["home_margin"] > 0
    assert store["5"]["games"][0]["pick_time"]["home_margin"] == 2.5


def test_new_card_is_refused_once_kickoff_has_passed(monkeypatch):
    schedules = pd.DataFrame([
        _schedule_row(5, "2026_05_BUF_LA", "BUF", "LA", 3.0, 48.5),
    ])
    loaded = {"done": False}

    def clock():
        if loaded["done"]:
            return KICK + timedelta(minutes=3)
        return KICK - timedelta(minutes=20)

    def load_schedules(*args, **kwargs):
        loaded["done"] = True
        return schedules

    _install_loaders(monkeypatch, schedules, clock)
    monkeypatch.setattr("nfl_lab.refresh.load_schedules", load_schedules)
    monkeypatch.setattr("nfl_lab.refresh.load_card", lambda season, week: None)
    saved = {"n": 0}
    monkeypatch.setattr("nfl_lab.refresh.save_card", lambda card: saved.__setitem__("n", saved["n"] + 1))
    monkeypatch.setattr(
        "nfl_lab.refresh.fetch_week_lines",
        lambda season, week, now=None: [{
            "away_team": "BUF",
            "home_team": "LA",
            "home_margin": 7.0,
            "total": 51.0,
            "spread_display": "LA -7",
            "kickoff_utc": KICK.isoformat(),
            "espn_id": "1",
            "missing": False,
            "source": "espn_scoreboard",
        }],
    )
    def write_site(*args, **kwargs):
        raise AssertionError("published")

    monkeypatch.setattr("nfl_lab.refresh.write_site", write_site)

    with pytest.raises(MissingLineError, match="kickoff passed before the pick card could be created"):
        run("refresh")
    assert saved["n"] == 0


def test_finished_week_is_graded_before_the_next_week_opens(monkeypatch):
    """Week 5 is complete, so live_week() would return 6 and skip the card."""
    schedules = pd.DataFrame([
        _schedule_row(5, "2026_05_BUF_LA", "BUF", "LA", 2.5, 47.5, kick_score=(30, 20)),
        _schedule_row(6, "2026_06_SEA_DEN", "SEA", "DEN", -3.0, 45.0),
    ])
    now = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
    _install_loaders(monkeypatch, schedules, lambda: now)

    store = {"5": {
        "season": 2026,
        "week": 5,
        "created_at": "2026-10-05T23:38:47+00:00",
        "games": [_buf_game(pre={
            "home_margin": 2.5,
            "total": 47.5,
            "source": "espn_scoreboard",
            "same_book": True,
            "captured_at": "2026-10-12T22:15:00+00:00",
        })],
    }}
    order = []

    def load_card(season, week):
        raw = store.get(str(week))
        return json.loads(json.dumps(raw)) if raw else None

    def save_card(card):
        order.append(int(card["week"]))
        store[str(card["week"])] = json.loads(json.dumps(card))

    monkeypatch.setattr("nfl_lab.refresh.load_card", load_card)
    monkeypatch.setattr("nfl_lab.refresh.save_card", save_card)
    monkeypatch.setattr(
        "nfl_lab.refresh.fetch_week_lines",
        lambda season, week, now=None: [{
            "away_team": "SEA",
            "home_team": "DEN",
            "home_margin": -3.0,
            "total": 45.0,
            "spread_display": "SEA -3",
            "kickoff_utc": "2026-10-16T00:15:00+00:00",
            "espn_id": "9",
            "missing": False,
            "source": "espn_scoreboard",
        }],
    )
    published = {}

    def write_site(card, *args, **kwargs):
        published["card"] = card
        return {"n_spread_picks": 0, "n_total_picks": 0, "n_games": len(card["games"])}

    monkeypatch.setattr("nfl_lab.refresh.write_site", write_site)

    run("refresh")

    graded = store["5"]["games"][0]
    assert graded["grading"]["spread_outcome"] == "win"
    assert graded["selection"]["spread_pick"] == "LA"
    assert graded["pick_time"]["home_margin"] == 2.5
    assert published["card"]["week"] == 6
    assert published["card"]["games"][0]["grading"] is None
    assert published["card"]["health"]["wins"] == 1
    assert published["card"]["health"]["losses"] == 0
    assert published["card"]["health"]["settled_picks"] == 1
    assert order[0] == 5


def test_espn_lines_stick_when_nflverse_reload_fails(monkeypatch):
    kick = datetime(2026, 10, 18, 17, 0, tzinfo=UTC)
    now = kick - timedelta(minutes=40)
    past_kick = kick - timedelta(hours=5)
    future = {
        "game_id": "g-future",
        "away_team": "SEA",
        "home_team": "DEN",
        "kickoff_utc": kick.isoformat(),
        "pre_kickoff": None,
        "pick_time": {"espn_id": "1"},
    }
    past = {
        "game_id": "g-past",
        "away_team": "BUF",
        "home_team": "LA",
        "kickoff_utc": past_kick.isoformat(),
        "pre_kickoff": None,
        "pick_time": {"espn_id": "2"},
    }

    def fetch(season, week, now=None):
        return [
            {
                "away_team": "SEA",
                "home_team": "DEN",
                "home_margin": -2.5,
                "total": 44.5,
                "spread_display": "DEN +2.5",
                "kickoff_utc": kick.isoformat(),
                "espn_id": "1",
                "missing": False,
                "source": "espn_scoreboard",
            },
            {
                "away_team": "BUF",
                "home_team": "LA",
                "home_margin": 3.0,
                "total": 49.0,
                "kickoff_utc": past_kick.isoformat(),
                "espn_id": "2",
                "missing": False,
                "source": "espn_scoreboard",
            },
        ]

    monkeypatch.setattr("nfl_lab.refresh.fetch_week_lines", fetch)

    def boom(season, week):
        raise RuntimeError("nflverse down")

    monkeypatch.setattr("nfl_lab.refresh._closes_for", boom)
    message = _capture_closes([future, past], "2026-10-18T16:20:00+00:00", now, 2026, 6)
    assert future["pre_kickoff"]["source"] == "espn_scoreboard"
    assert future["pre_kickoff"]["line_source"] == "espn_draftkings"
    assert future["pre_kickoff"]["home_margin"] == -2.5
    assert past["pre_kickoff"] is None
    assert message is not None and "kickoff passed" in message


def test_graded_week_is_kept_when_the_next_card_fails(monkeypatch, capsys):
    """Week 5 grades, week 6 has no line: grades saved, exit 2 commits, job still fails."""
    from nfl_lab import cli
    from nfl_lab.odds_espn import PartialSnapshot

    schedules = pd.DataFrame([
        _schedule_row(5, "2026_05_BUF_LA", "BUF", "LA", 2.5, 47.5, kick_score=(30, 20)),
        _schedule_row(6, "2026_06_SEA_DEN", "SEA", "DEN", -3.0, 45.0),
    ])
    now = datetime(2026, 10, 13, 11, 15, tzinfo=UTC)
    _install_loaders(monkeypatch, schedules, lambda: now)
    store = {"5": {
        "season": 2026, "week": 5, "created_at": "2026-10-05T23:38:47+00:00",
        "games": [_buf_game(pre={
            "home_margin": 2.5, "total": 47.5, "source": "espn_scoreboard",
            "same_book": True, "captured_at": "2026-10-12T23:45:00+00:00",
        })],
    }}
    ungraded = json.loads(json.dumps(store["5"]))
    monkeypatch.setattr("nfl_lab.refresh.load_card",
                        lambda season, week: json.loads(json.dumps(store[str(week)])) if str(week) in store else None)
    monkeypatch.setattr("nfl_lab.refresh.save_card",
                        lambda card: store.__setitem__(str(card["week"]), json.loads(json.dumps(card))))

    def no_line(season, week, now=None):
        raise MissingLineError("SEA @ DEN has no DraftKings spread")

    monkeypatch.setattr("nfl_lab.refresh.fetch_week_lines", no_line)
    monkeypatch.setattr("nfl_lab.refresh.write_site",
                        lambda *a, **k: pytest.fail("no site write without a next card"))

    with pytest.raises(PartialSnapshot) as err:
        run("refresh")
    assert "week(s) [5] saved" in str(err.value)
    assert isinstance(err.value.__cause__, MissingLineError)
    assert store["5"]["games"][0]["grading"]["spread_outcome"] == "win"
    assert "6" not in store  # no fabricated week 6 card or line

    # The CLI maps this to exit 2: nightly.yml commits, then fails the job.
    # Start from the ungraded card again; an unchanged re-grade is exit 1.
    store["5"] = ungraded
    monkeypatch.setattr("sys.argv", ["nfl-lab", "refresh"])
    assert cli.main() == 2
    assert "next pick card failed" in capsys.readouterr().err


def _week5_store(monkeypatch, pre):
    store = {"5": {
        "season": 2026, "week": 5, "created_at": "2026-10-05T23:38:47+00:00",
        "games": [_buf_game(pre=pre)],
    }}
    monkeypatch.setattr("nfl_lab.refresh.load_card",
                        lambda season, week: json.loads(json.dumps(store[str(week)])) if str(week) in store else None)
    monkeypatch.setattr("nfl_lab.refresh.save_card",
                        lambda card: store.__setitem__(str(card["week"]), json.loads(json.dumps(card))))
    monkeypatch.setattr("nfl_lab.refresh.write_site",
                        lambda *a, **k: pytest.fail("no site write without a next card"))
    return store


def _week5_done_week6_open(monkeypatch):
    schedules = pd.DataFrame([
        _schedule_row(5, "2026_05_BUF_LA", "BUF", "LA", 2.5, 47.5, kick_score=(30, 20)),
        _schedule_row(6, "2026_06_SEA_DEN", "SEA", "DEN", -3.0, 45.0),
    ])
    now = datetime(2026, 10, 13, 11, 15, tzinfo=UTC)
    _install_loaders(monkeypatch, schedules, lambda: now)

    def no_line(season, week, now=None):
        raise MissingLineError("SEA @ DEN has no DraftKings spread")

    monkeypatch.setattr("nfl_lab.refresh.fetch_week_lines", no_line)


_PRE = {"home_margin": 2.5, "total": 47.5, "source": "espn_scoreboard",
        "same_book": True, "captured_at": "2026-10-12T23:45:00+00:00"}


def test_unchanged_regrade_keeps_exit_1_when_the_next_card_fails(monkeypatch, capsys):
    """Week 5 was already graded on a prior run: re-grading changes nothing, so exit 1."""
    from nfl_lab import cli
    from nfl_lab.odds_espn import PartialSnapshot

    _week5_done_week6_open(monkeypatch)
    store = _week5_store(monkeypatch, _PRE)
    with pytest.raises(PartialSnapshot):
        run("refresh")  # first run grades week 5 (exit-2 path)
    settled = json.loads(json.dumps(store))

    monkeypatch.setattr("sys.argv", ["nfl-lab", "refresh"])
    assert cli.main() == 1
    assert store == settled  # nothing new to commit
    assert "next pick card failed" not in capsys.readouterr().err


def test_partial_snapshot_from_next_card_is_not_rewrapped(monkeypatch):
    from nfl_lab.odds_espn import PartialSnapshot

    _week5_done_week6_open(monkeypatch)
    _week5_store(monkeypatch, _PRE)
    inner = PartialSnapshot("SEA @ DEN close still missing")

    def boom(*a, **k):
        raise inner

    monkeypatch.setattr("nfl_lab.refresh._next_card", boom)
    with pytest.raises(PartialSnapshot) as err:
        run("refresh")
    assert err.value is inner
    assert err.value.__cause__ is None


def test_code_bug_exits_1_with_traceback_after_week_already_graded(monkeypatch, capsys):
    """A real bug in _project must stay exit 1 once week 5 is graded and unchanged."""
    from nfl_lab import cli

    schedules = pd.DataFrame([
        _schedule_row(5, "2026_05_BUF_LA", "BUF", "LA", 2.5, 47.5, kick_score=(30, 20)),
        _schedule_row(6, "2026_06_SEA_DEN", "SEA", "DEN", -3.0, 45.0, kick_score=(20, 17)),
        _schedule_row(7, "2026_07_KC_LV", "KC", "LV", -3.0, 45.0),
    ])
    now = datetime(2026, 10, 20, 11, 15, tzinfo=UTC)
    _install_loaders(monkeypatch, schedules, lambda: now)
    store = _week5_store(monkeypatch, _PRE)

    def boom(*a, **k):
        raise KeyError("typo_in_code")

    monkeypatch.setattr("nfl_lab.refresh._project", boom)
    monkeypatch.setattr("sys.argv", ["nfl-lab", "refresh"])
    cli.main()  # prior run: grades week 5 for the first time
    capsys.readouterr()
    settled = json.loads(json.dumps(store))

    assert cli.main() == 1
    err = capsys.readouterr().err
    assert "Traceback" in err and "typo_in_code" in err
    assert "next pick card failed" not in err
    assert store == settled
