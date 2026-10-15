"""Publishing a report card keeps the complete API manifest in sync."""
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from nfl_lab import publish


def test_report_card_publication_refreshes_all_api_metadata(monkeypatch, tmp_path):
    api = tmp_path / "public" / "api"
    output = tmp_path / "output"
    api.mkdir(parents=True)
    monkeypatch.setattr(publish, "PUBLIC_API", api)
    monkeypatch.setattr(publish, "OUTPUT_DIR", output)
    (api / "saved_weeks.json").write_text('{"weeks": [{"week": 5}]}\n')
    (api / "report_card.json").write_text('{"old": true}\n')
    now = datetime(2026, 10, 15, 14, tzinfo=ZoneInfo("America/Chicago"))
    old = now - timedelta(days=3)
    publish._refresh_freshness(old)
    report = {"generated_at": now.isoformat(), "spread": {"wins": 18}, "total": {"wins": 6}}

    publish.publish_report_card(report, now)

    assert json.loads((api / "report_card.json").read_text()) == report
    assert (api / "report_card.json").read_bytes() == (output / "report_card" / "2026_wk01_04.json").read_bytes()
    freshness = json.loads((api / "freshness.json").read_text())
    assert freshness["generated_at"] == old.isoformat()
    assert freshness["stale_after"] == (old + timedelta(hours=36)).isoformat()
    files = {entry["path"]: entry for entry in freshness["files"]}
    assert set(files) == {"api/saved_weeks.json", "api/report_card.json"}
    for name, entry in files.items():
        content = (api / name.removeprefix("api/")).read_bytes()
        assert entry["bytes"] == len(content)
        assert entry["sha256"] == hashlib.sha256(content).hexdigest()
        expected = now if name == "api/report_card.json" else old
        assert entry["updated_at"] == expected.isoformat()


@pytest.mark.parametrize("kind", ["report", "saved_weeks"])
def test_partial_publication_keeps_stale_live_data_stale(monkeypatch, tmp_path, kind):
    root = Path(__file__).resolve().parents[1]
    public = tmp_path / "public"
    shutil.copytree(root / "public", public)
    api = public / "api"
    monkeypatch.setattr(publish, "PUBLIC_API", api)
    monkeypatch.setattr(publish, "OUTPUT_DIR", tmp_path / "output")
    now = datetime(2026, 10, 15, 14, tzinfo=ZoneInfo("America/Chicago"))
    old = now - timedelta(days=3)
    publish._refresh_freshness(old)
    before = json.loads((api / "freshness.json").read_text())
    picks = (api / "picks.json").read_bytes()
    if kind == "report":
        report = json.loads((api / "report_card.json").read_text())
        report["generated_at"] = now.isoformat()
        publish.publish_report_card(report, now)
        changed = "api/report_card.json"
    else:
        card = json.loads(picks)
        card["games"][0]["grading"] = {"home_score": 24, "away_score": 17, "spread_outcome": "win"}
        monkeypatch.setattr(publish, "load_card", lambda season, week: card if week == card["week"] else None)
        publish.publish_saved_weeks(now)
        changed = "api/saved_weeks.json"

    after = json.loads((api / "freshness.json").read_text())
    assert after["generated_at"] == before["generated_at"]
    assert after["stale_after"] == before["stale_after"]
    assert (api / "picks.json").read_bytes() == picks
    files = {entry["path"]: entry for entry in after["files"]}
    for entry in before["files"]:
        if entry["path"] != changed:
            assert files[entry["path"]] == entry
    assert files[changed]["updated_at"] == now.isoformat()
    assert files[changed]["sha256"] == hashlib.sha256((public / changed).read_bytes()).hexdigest()

    for page in ["index.html", "freshness.html"]:
        proc = subprocess.run([
            "node", str(root / "tests" / "js" / "render_page.js"), str(public),
            page, str(api / "picks.json"), now.isoformat(),
        ], capture_output=True, text=True, check=True)
        rendered = json.loads(proc.stdout)
        if page == "index.html":
            assert "hasn't updated since" in rendered["notices"]["html"]
            assert "Mon 2:00 PM CT" in rendered["updated"]["text"]
        else:
            assert rendered["stale"]["hidden"] is False
            assert "out of date" in rendered["stale"]["text"]


def test_live_card_publication_advances_live_freshness(monkeypatch, tmp_path):
    monkeypatch.setattr(publish, "PUBLIC_API", tmp_path)
    monkeypatch.setattr(publish, "load_card", lambda *args: None)
    now = datetime(2026, 10, 15, 14, tzinfo=ZoneInfo("America/Chicago"))
    publish._refresh_freshness(now - timedelta(days=3))
    publish.publish_card({"week": 6, "health": {}, "games": []}, now)
    fresh = json.loads((tmp_path / "freshness.json").read_text())
    assert fresh["generated_at"] == now.isoformat()
    assert fresh["stale_after"] == (now + timedelta(hours=36)).isoformat()


@pytest.mark.parametrize("with_summary", [True, False])
def test_missing_manifest_does_not_invent_live_refresh(monkeypatch, tmp_path, with_summary):
    monkeypatch.setattr(publish, "PUBLIC_API", tmp_path)
    monkeypatch.setattr(publish, "load_card", lambda *args: None)
    now = datetime(2026, 10, 15, 14, tzinfo=ZoneInfo("America/Chicago"))
    old = now - timedelta(days=3)
    if with_summary:
        (tmp_path / "summary.json").write_text(json.dumps({"generated_at": old.isoformat()}))
    publish.publish_saved_weeks(now)
    fresh = json.loads((tmp_path / "freshness.json").read_text())
    assert fresh["generated_at"] == (old.isoformat() if with_summary else None)
    assert fresh["stale_after"] == ((old + timedelta(hours=36)).isoformat() if with_summary else None)
