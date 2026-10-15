"""Publishing a report card keeps the complete API manifest in sync."""
import hashlib
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nfl_lab import publish


def test_report_card_publication_refreshes_all_api_metadata(monkeypatch, tmp_path):
    api = tmp_path / "public" / "api"
    output = tmp_path / "output"
    api.mkdir(parents=True)
    monkeypatch.setattr(publish, "PUBLIC_API", api)
    monkeypatch.setattr(publish, "OUTPUT_DIR", output)
    (api / "saved_weeks.json").write_text('{"weeks": [{"week": 5}]}\n')
    (api / "report_card.json").write_text('{"old": true}\n')
    (api / "freshness.json").write_text('{"generated_at": "old", "files": []}\n')
    now = datetime(2026, 10, 15, 14, tzinfo=ZoneInfo("America/Chicago"))
    report = {"generated_at": now.isoformat(), "spread": {"wins": 18}, "total": {"wins": 6}}

    publish.publish_report_card(report, now)

    assert json.loads((api / "report_card.json").read_text()) == report
    assert (api / "report_card.json").read_bytes() == (output / "report_card" / "2026_wk01_04.json").read_bytes()
    freshness = json.loads((api / "freshness.json").read_text())
    assert freshness["generated_at"] == now.isoformat()
    assert freshness["stale_after"] == (now + timedelta(hours=36)).isoformat()
    files = {entry["path"]: entry for entry in freshness["files"]}
    assert set(files) == {"api/saved_weeks.json", "api/report_card.json"}
    for name, entry in files.items():
        content = (api / name.removeprefix("api/")).read_bytes()
        assert entry["bytes"] == len(content)
        assert entry["sha256"] == hashlib.sha256(content).hexdigest()
        assert entry["updated_at"] == now.isoformat()
