"""The home page must not link to a previews page that is not in public/."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def _static_preview_hrefs(index_html: str) -> list[str]:
    hrefs = []
    for href in re.findall(r'href="([^"]*previews/[^"]+\.html)"', index_html):
        hrefs.append(href.removeprefix("../"))
    return hrefs


def test_home_does_not_link_to_a_missing_preview_page():
    index = (PUBLIC / "index.html").read_text()
    js = (PUBLIC / "assets" / "site.js").read_text()
    week = int(json.loads((PUBLIC / "api" / "picks.json").read_text())["week"])
    slot = re.search(r'<p class="next-link" id="previews-link">(.*?)</p>', index, re.S)
    assert slot is not None and slot.group(1).strip() == "", (
        "the home previews line must ship empty so a placeholder does not flash "
        "before site.js writes the link or the coming-soon text"
    )
    hrefs = _static_preview_hrefs(index)

    unconditional = 'prev.href = `previews/week${card.week}.html`'
    assert unconditional not in js, (
        f"home sets #previews-link to previews/week{week}.html "
        "without checking that the page exists"
    )
    missing = [href for href in hrefs if not (PUBLIC / href).is_file()]
    assert missing == [], f"home links to missing previews pages: {missing}"


@pytest.mark.parametrize("response", ["200", "404", "500", "403", "network", "pending"])
@pytest.mark.parametrize("no_spreads", [False, True])
def test_home_preview_rendering_and_initialization(response, no_spreads):
    node = shutil.which("node")
    assert node, "node is required for site.js rendering tests"
    result = subprocess.run(
        [node, str(ROOT / "tests/js/home_previews.js"), str(PUBLIC), response,
         "no-spreads" if no_spreads else "qualifying"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
