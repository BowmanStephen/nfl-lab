"""The renderer must report connected markup, including dynamically inserted IDs."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RENDER = Path(__file__).with_name("render_site.mjs")
PUBLIC = RENDER.parent.parent / "public"


def _render(public: Path, page: str = "home") -> dict:
    assert shutil.which("node"), "node is required to render the published pages"
    proc = subprocess.run(
        ["node", str(RENDER), str(public), "2026-10-15T00:00:00Z", page],
        check=True, capture_output=True, text=True,
    )
    return json.loads(proc.stdout)[page]


def _fixture(tmp_path: Path, markup: str, script: str) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(markup)
    (tmp_path / "assets" / "site.js").write_text(script)
    return tmp_path


def test_lookup_does_not_fabricate_missing_elements(tmp_path):
    public = _fixture(tmp_path, '<main id="main"></main>', '''
        if (document.getElementById("missing-count") !== null) throw new Error("missing lookup must return null");
        if (document.getElementById("") !== null) throw new Error("empty ID must return null");
        const el = document.getElementById("missing-count");
        if (el) el.textContent = "Our picks (12)";
    ''')
    assert "missing-count" not in _render(public)


def test_only_connected_markup_ids_are_resolved(tmp_path):
    public = _fixture(tmp_path, '''<body><main id='main'>
        <!-- <p id="comment-count"></p> -->
        <script>const template = '<p id="script-count"></p>';</script>
        <p title='example id="attribute-count"' id=real-count hidden>Initial</p>
        <div id="slot"><span id="removed">Old</span></div>
    </main></body>''', '''
        for (const id of ["comment-count", "script-count", "attribute-count"])
          if (document.getElementById(id)) throw new Error("phantom: " + id);
        const real = document.getElementById("real-count");
        if (!real.hidden) throw new Error("hidden attribute lost");
        real.textContent = "Our picks (12)";
        const slot = document.getElementById("slot");
        slot.innerHTML = '<span id="inserted">New</span>';
        if (document.getElementById("removed")) throw new Error("detached node found");
        document.getElementById("inserted").textContent = "Inserted count";
        slot.innerHTML = '<span id="temporary">Temporary</span>';
        slot.textContent = "Replacement text";
        if (document.getElementById("temporary")) throw new Error("text left descendants");
        slot.innerHTML = '<span id="inserted">Inserted count</span>';
    ''')
    fields = _render(public)
    assert fields["real-count"]["text"] == "Our picks (12)"
    assert fields["real-count"]["hidden"] is True
    assert fields["inserted"]["text"] == "Inserted count"
    assert "removed" not in fields
    assert "temporary" not in fields
    assert not {"comment-count", "script-count", "attribute-count"} & fields.keys()


@pytest.mark.parametrize(("page", "filename", "markup", "element_id"), [
    ("home", "index.html", '<h2 id="picks-h">Our picks</h2>', "picks-h"),
    ("ledger", "ledger.html", '<p id="live-health">…</p>', "live-health"),
])
def test_removing_published_count_markup_cannot_be_masked(tmp_path, page, filename, markup, element_id):
    public = tmp_path / "public"
    shutil.copytree(PUBLIC, public)
    # Keep real site.js and API data. Removing markup must not let its
    # JavaScript assignment publish a field that no visitor can see.
    html = (public / filename).read_text()
    assert markup in html
    (public / filename).write_text(html.replace(markup, ""))
    fields = _render(public, page)
    assert element_id not in fields
    if page == "home":
        assert not any("Our picks (" in field["text"] for field in fields.values())
