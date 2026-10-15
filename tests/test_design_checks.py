"""Keep homepage contrast regressions visible to the design detector."""
import fnmatch
import json
from pathlib import Path


def test_homepage_contrast_checks_are_not_broadly_suppressed():
    root = Path(__file__).resolve().parents[1]
    detector = json.loads((root / ".impeccable" / "config.json").read_text()).get("detector", {})
    home = "public/index.html"
    matches_home = lambda pattern: fnmatch.fnmatchcase(home, pattern.removeprefix("./"))

    assert not {"*", "low-contrast"}.intersection(detector.get("ignoreRules", []))
    assert not any(matches_home(pattern) for pattern in detector.get("ignoreFiles", []))
    for entry in detector.get("ignoreValues", []):
        if entry.get("rule") not in {"*", "low-contrast"} or entry.get("value") != "*":
            continue
        files = entry.get("files", [])
        assert files and not any(matches_home(pattern) for pattern in files), entry
