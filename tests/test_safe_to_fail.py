"""Routines fail without half-written files and stop on stale inputs."""
import json

import pandas as pd
import pytest

from nfl_lab import cli, safe_io
from nfl_lab.refresh import StaleSourceData, check_source_fresh


def test_atomic_write_keeps_old_file_when_encoding_fails(tmp_path):
    path = tmp_path / "picks.json"
    path.write_text('{"week": 5}\n')
    with pytest.raises(TypeError):
        safe_io.atomic_write_json(path, {"bad": object()})
    assert json.loads(path.read_text()) == {"week": 5}
    assert [p.name for p in tmp_path.iterdir()] == ["picks.json"]


def test_atomic_write_keeps_old_file_when_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "picks.json"
    path.write_text('{"week": 5}\n')

    def boom(src, dst):
        raise OSError("runner died")

    monkeypatch.setattr(safe_io.os, "replace", boom)
    with pytest.raises(OSError):
        safe_io.atomic_write_json(path, {"week": 6})
    assert json.loads(path.read_text()) == {"week": 5}
    assert [p.name for p in tmp_path.iterdir()] == ["picks.json"]


def test_atomic_write_replaces(tmp_path):
    path = tmp_path / "sub" / "a.json"
    safe_io.atomic_write_json(path, {"ok": 1})
    assert json.loads(path.read_text()) == {"ok": 1}


def test_validate_flags_truncated_empty_and_temp_files(tmp_path):
    (tmp_path / "good.json").write_text('{"a": 1}')
    (tmp_path / "cut.json").write_text('{"a": ')
    (tmp_path / "empty.json").write_text("{}")
    (tmp_path / ".picks.json.abc.tmp").write_text("x")
    problems = safe_io.validate_json_tree(tmp_path)
    joined = "\n".join(problems)
    assert len(problems) == 3
    assert "cut.json" in joined and "empty.json" in joined and ".tmp" in joined
    assert safe_io.main([str(tmp_path)]) == 1


def test_validate_passes_clean_tree(tmp_path):
    (tmp_path / "good.json").write_text('{"a": 1}')
    assert safe_io.main([str(tmp_path)]) == 0


def _sched(rows):
    return pd.DataFrame(rows, columns=["season", "week", "home_score"])


def test_stale_when_schedule_empty():
    with pytest.raises(StaleSourceData):
        check_source_fresh(_sched([]), pd.DataFrame(columns=["season", "week"]), season=2026)


def test_stale_when_scores_but_no_plays():
    sched = _sched([(2026, 1, 20)])
    with pytest.raises(StaleSourceData):
        check_source_fresh(sched, pd.DataFrame({"season": [2025], "week": [18]}), season=2026)


def test_stale_when_plays_lag_two_weeks():
    sched = _sched([(2026, 5, 20), (2026, 6, None)])
    with pytest.raises(StaleSourceData):
        check_source_fresh(sched, pd.DataFrame({"season": [2026], "week": [3]}), season=2026)


def test_one_week_of_lag_is_fine():
    sched = _sched([(2026, 5, 20), (2026, 6, None)])
    check_source_fresh(sched, pd.DataFrame({"season": [2026], "week": [4]}), season=2026)


def test_preseason_with_no_scores_is_fine():
    check_source_fresh(_sched([(2026, 1, None)]), pd.DataFrame(columns=["season", "week"]), season=2026)


def test_cli_exit_3_on_stale(monkeypatch):
    def stale(mode="refresh"):
        raise StaleSourceData("no rows")

    monkeypatch.setattr(cli, "run", stale)
    assert cli.main(["refresh"]) == 3
